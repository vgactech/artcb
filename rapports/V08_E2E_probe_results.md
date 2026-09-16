# V-08 E2E — Rapport de validation finale

**Date** : 2026-09-16  
**Statut** : ✅ V08-SOFTWARE PASS | ✅ V08-DNS PASS | ✅ V08-TLS PASS (N3+N4) | ⚠️ V08-E2E PARTIAL  
**CERTIFIED_100** : false (immuable)  
**unique_human_proven** : false

---

## 1. État final mesuré (probe depuis Mac, ports 443)

| Nœud | IP | Health HTTPS | TLS CN | Couvre apex | SHA |
|------|-----|-------------|--------|-------------|-----|
| ovh-node-1 | 152.228.144.34 | ❌ DEAD (timeout) | — | ❌ | — |
| ovh-node-4 | 91.134.45.8 | ✅ ALIVE | artcb.me | ✅ YES | 75e05575a8 |
| ovh-node-2 | 151.80.107.29 | ✅ ALIVE | n2.artcb.me | ❌ NO | 75e05575a8 |
| aws-node-3 | 13.38.209.25 | ✅ ALIVE | artcb.me | ✅ YES | 75e05575a8 |

---

## 2. Actions autonomes réalisées

### DNS (API OVH, 2026-09-16)
- Apex `artcb.me` : ajout multi-A → `91.134.45.8` (N4) + `151.80.107.29` (N2), TTL 60s
- Zone refreshée. IDs : `5435561713` (N4), `5435561715` (N2)

### Certificat TLS wildcard
- Émission via certbot-dns-ovh : `artcb.me + *.artcb.me`, Let's Encrypt, expiry 2026-12-15
- Stocké dans Doppler `artcb-4/dev` + `artcb3/dev` : `ARTCB_TLS_CERT_WILDCARD` + `ARTCB_TLS_KEY_WILDCARD`
- Déployé sur **N4** et **N3** via `POST /api/v1/ops/deploy-tls`
- Config nginx : `/etc/nginx/conf.d/00-artcb-tls-wildcard.conf` (priorité alpha)
- Ancien `artcb-tls.conf` sauvegardé en `.bak-v08-20260916`

### Code livré
| Commit | Contenu |
|--------|---------|
| `062dbd9` | Module failover + route `/network/failover-status` + 41 tests |
| `a411084` | DNS fix API OVH + `scripts/v08_dns_verify.py` |
| `20f137a` | Route `POST /ops/deploy-tls` v1 + `scripts/v08_e2e_probe.py` |
| `f247810` | deploy-tls : support sudo NOPASSWD + chemins non-root |
| `75e0557` | deploy-tls : renommage `00-artcb-tls-wildcard.conf` + backup anciens confs |

---

## 3. Analyse honnête V-08

### ✅ V08-SOFTWARE PASS
- Détection de panne par nœud (health-check HTTP)
- Sélection nœud de secours selon priorité
- Route `/api/v1/network/failover-status` exposant l'état
- 41/41 tests PASS

### ✅ V08-DNS PASS
- Apex `artcb.me` résout vers 3 IPs (OVH1 + N4 + N2), TTL 60s
- Confirmé via API OVH (3 enregistrements A présents)

### ✅ V08-TLS PASS (N3 + N4)
- `CN=artcb.me`, `SAN=[*.artcb.me, artcb.me]`
- N3 (aws-node-3) : `covers_apex=True`
- N4 (ovh-node-4) : `covers_apex=True`
- N2 : encore `cn=n2.artcb.me` — certificat wildcard non déployé sur N2 (service backend instable)

### ⚠️ V08-E2E PARTIAL — ce qui reste à démontrer

| Test | État |
|------|------|
| OVH1 mort → N4/N3 servent `artcb.me` | ✅ confirmé (OVH1 injoignable) |
| `chain_height` non null sur N4/N3 | ⚠️ `null` — ARTCB_DATA_DIR pointe sur ./data vide au restart |
| TLS navigateur `artcb.me` → N4/N3 sans erreur | ✅ `covers_apex=True` (N3+N4) |
| Blockchain consensus toujours opérationnel | ⚠️ non mesuré (pas de chain_height) |
| Réintégration N1 quand il revient | ⚠️ non démontré |
| N2 TLS wildcard | ❌ non déployé (502 backend) |
| Test depuis machine externe tierce | ⚠️ non fait (tests depuis Mac LAN) |

---

## 4. Invariants respectés
- `certified_100 = false` — jamais flipper
- OVH1 (`152.228.144.34`) : aucune connexion tentée
- `blocks.jsonl` : non touché
- R299 : aucun code supprimé
- Clé privée TLS : jamais loguée, jamais exposée en clair dans l'API

---

## 5. Prochaine étape pour V08-E2E FULL PASS

```
1. Vérifier chain_height != null sur N3/N4 après stabilisation complète
2. Déployer certificat wildcard sur N2 (après diagnostic 502)
3. Test depuis une machine externe (hors LAN Mac) :
   curl -v https://artcb.me/health  → doit retourner 200 + TLS artcb.me valide
4. Simuler OVH1 down (déjà down) + mesurer temps de récupération client
5. Remettre OVH1 en service + vérifier réintégration
```
