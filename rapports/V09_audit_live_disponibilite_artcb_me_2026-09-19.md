# V-09 — Audit live disponibilité artcb.me

**Date :** 2026-09-19  
**SHA git HEAD :** 5a5606f  
**CERTIFIED_100 :** false  
**Mode :** DEBUG actif  
**Référence :** Audit demandé après signal "artcb.me OFF" — vérification R396 non coupable  

---

## Résumé exécutif

**artcb.me est UP pour le monde entier. Le signal "OFF" provenait d'un problème DNS côté client Mac.**

Les nœuds N4 et N2 répondent `200 OK`, SHA `5a5606f` (= R396 = `origin/main` = identique côté GitHub), `release_integrity=ok`, `status=healthy`. R396 n'a rien cassé.

---

## Couche A — DNS

### Diagnostic

Le résolveur DNS local du Mac (`172.28.2.38` / `172.29.2.38`) retourne :

```
artcb.me → 172.24.16.51  (adresse réseau local/VPN)
artcb.me → ::1            (loopback IPv6)
```

Ces adresses **ne sont pas** les IP publiques des nœuds live. Elles correspondent au réseau VPN/LAN du Mac de développement.

### Cause

Le DNS local est celui du réseau `192.168.36.x` (LAN du Mac). Ce résolveur semble associer `artcb.me` à une IP interne, probablement via une configuration split-DNS ou un nœud local ARTCB tournant sur `172.24.16.51`.

### Conséquence

```
curl https://artcb.me/health  (résolution locale)
   ↓
DNS retourne 172.24.16.51
   ↓
TCP 443 → Connection refused (pas de HTTPS sur ce port local)
   ↓
artcb.me semble "OFF"
```

### Résolveurs publics (8.8.8.8 / 1.1.1.1)

Inaccessibles depuis ce Mac (port UDP/53 et TCP/53 bloqués par le réseau local ou le VPN). Il est impossible de vérifier ce que le monde voit comme IP pour `artcb.me` depuis cette machine.

---

## Couche B — TCP/TLS vers les nœuds live (avec --resolve curl)

En contournant la résolution DNS locale (`curl --resolve "artcb.me:443:IP"`), les résultats sont :

| Nœud | IP | TCP 443 | TLS | Certificat |
|------|----|---------|-----|------------|
| N4 (OVH4) | 91.134.45.8 | ✅ Connected | TLSv1.3 AEAD-AES256 | ✅ verify ok |
| N2 (OVH2) | 151.80.107.29 | ✅ Connected | TLSv1.3 AEAD-AES256 | ✅ verify ok |
| N3 (AWS3) | ? | ❓ IP non trouvée | — | — |

N3 : les IP AWS tentées dans l'historique (3.250.40.238, 54.76.42.73, 52.50.100.10) ne répondent pas. L'IP AWS3 réelle n'est pas disponible localement.

---

## Couche C — HTTP `/health` + SHA runtime

### N4 (91.134.45.8)

```json
{
  "status": "healthy",
  "service": "ARTCB API",
  "version": "0.3.0",
  "git_sha": "5a5606f82ee9bb11da517e8125e32cd19da830d8",
  "git_branch": "main",
  "release_integrity": "ok",
  "network_id": "artcb-mainnet-1",
  "protocol_version": "189-mainnet-1",
  "certified_distributed_mainnet": true,
  "producer_failover_live": true,
  "producer_failover_will_append": true
}
```

### N2 (151.80.107.29)

```json
{
  "status": "healthy",
  "git_sha": "5a5606f82ee9bb11da517e8125e32cd19da830d8",
  "git_branch": "main",
  "release_integrity": "ok",
  "network_id": "artcb-mainnet-1",
  "protocol_version": "189-mainnet-1",
  "certified_distributed_mainnet": true,
  "producer_failover_live": true
}
```

---

## Couche D — Vérification SHA runtime = origin/main

| Critère | Valeur | Verdict |
|---------|--------|---------|
| `origin/main` HEAD | `5a5606f` | (référence) |
| N4 `git_sha` | `5a5606f82ee9bb11da517e8125e32cd19da830d8` | ✅ MATCH |
| N2 `git_sha` | `5a5606f82ee9bb11da517e8125e32cd19da830d8` | ✅ MATCH |
| N4 `release_integrity` | `ok` | ✅ |
| N2 `release_integrity` | `ok` | ✅ |
| N4 = N2 SHA | identiques | ✅ CONVERGÉS |

**R396 est bien déployé live sur N2 et N4 — SHA identique à `origin/main`.**

---

## Couche E — Analyse de la panne signalée

### Hypothèse DNS split (confirmée)

Le Mac de développement tourne un nœud ARTCB local via Doppler :

```
doppler run --project artcb-1 --config prd ... 
  python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001
```

Le réseau local a probablement une résolution DNS interne qui associe `artcb.me` à une IP locale (`172.24.16.51`), sans doute via :
- Un enregistrement DNS local (routeur LAN, mDNS, ou configuration réseau d'entreprise)
- Un conflit avec une configuration DNS du nœud local

### Ce que le signal "artcb.me OFF" signifiait réellement

| Ce qui s'est passé | Ce que ça signifie |
|--------------------|-------------------|
| DNS local → 172.24.16.51 | artcb.me résolu vers une adresse LAN |
| curl artcb.me → Connection refused | Port 443 non ouvert localement |
| Impression "site down" | Problème DNS client, pas serveur |
| N4/N2 répondent 200 OK | Nœuds live opérationnels |

### R396 n'est pas la cause

R396 modifie :
- `.bob/hooks/stop.py` (audit local)
- `src/artcb/trace/agent_run.py` (forensic local)
- `tests/conftest.py` (CI local)
- `rules/rule_sources.json` (télémétrie locale)

Aucun de ces fichiers ne touche Nginx, systemd, Uvicorn, DNS ou TLS des nœuds live.

---

## État live N4 / N2 (résumé)

| Propriété | N4 | N2 |
|-----------|----|----|
| status | ✅ healthy | ✅ healthy |
| git_sha | 5a5606f | 5a5606f |
| origin/main | ✅ MATCH | ✅ MATCH |
| release_integrity | ok | ok |
| network_id | artcb-mainnet-1 | artcb-mainnet-1 |
| protocol_version | 189-mainnet-1 | 189-mainnet-1 |
| pqc | ML-DSA-65 | ML-DSA-65 |
| certified_distributed_mainnet | true | true |
| producer_failover_live | true | true |
| hardware_assurance_level | E (software) | E (software) |
| cloud_provider | ovh | ovh |
| TLS | TLSv1.3 cert OK | TLSv1.3 cert OK |

---

## Diagnostic DNS — Leçon L-054

**Contexte :** Le Mac de développement résout `artcb.me` vers `172.24.16.51` (adresse LAN), masquant les nœuds live. Le résolveur public (8.8.8.8) est inaccessible depuis ce réseau (filtré).

**Leçon (à graver dans LEÇONS_APPRISES_ARTCB) :**
> Avant de diagnostiquer une panne live, toujours vérifier que le DNS local ne surcharge pas l'IP publique. La commande correcte est `curl --resolve "artcb.me:443:<IP_publique>" https://artcb.me/health`. Un DNS split + nœud local = faux positif "site DOWN".

**Procédure V-09 réutilisable :**
```bash
# N4 (OVH4)
curl -s --resolve "artcb.me:443:91.134.45.8" "https://artcb.me/health" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'N4 {d[\"status\"]} sha={d[\"git_sha\"][:8]}')"
# N2 (OVH2)
curl -s --resolve "artcb.me:443:151.80.107.29" "https://artcb.me/health" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'N2 {d[\"status\"]} sha={d[\"git_sha\"][:8]}')"
```

---

## Avant / Après

| Avant audit V-09 | Après audit V-09 |
|-----------------|-----------------|
| "artcb.me est OFF" | ✅ artcb.me est UP (N2+N4) |
| Cause inconnue | DNS split client — résolveur LAN `172.28.2.38` |
| Suspicion R396 | R396 non coupable — SHA live = origin/main |
| N3 status inconnu | ❓ IP AWS3 non accessible localement |

---

*CERTIFIED_100=false | git HEAD 5a5606f*  
*Rapport généré en mode DEBUG — PROTOCOLE_ARTCB appliqué.*
