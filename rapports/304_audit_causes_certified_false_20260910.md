# Rapport 304 — Audit exhaustif : causes de CERTIFIED_100=false

**Date :** 2026-09-10  
**SHA origin/main au moment de l'audit :** `84d2c9228c4b7d73c1876e6e31764b541265a3e8`  
**Auteur :** Bob (agent local, session 304)  
**Méthode :** lecture exhaustive des rapports 285–303, code source, mesures live  
**Périmètre :** zéro modification — audit uniquement  

---

## Résumé exécutif

`CERTIFIED_100` reste **false** à cause de **7 causes distinctes et cumulatives**, réparties
en 3 catégories : transport réseau, consensus PBFT, et artefacts de preuve.
Aucune de ces causes n'est une panne : le livre mainnet tourne, 4 seeds répondent, 1133 blocs
valides. Ce sont des **lacunes de preuve**, pas des défaillances.

---

## Mesures live à l'instant de l'audit

| Nœud | URL | SHA (12 car) | Height | Chain valid |
|---|---|---|---|---|
| ovh-node-1 | https://artcb.me | `84d2c9228c4b` | 1133 | true |
| ovh-node-2 | https://n2.artcb.me | `84d2c9228c4b` | 1133 | true |
| aws-node-3 | https://n3.artcb.me | `852f0e24134c` ⚠️ | 1133 | true |
| ovh-node-4 | https://n4.artcb.me | `84d2c9228c4b` | 1133 | true |
| Mac :8001 | http://localhost:8001 | `84d2c9228c4b` | **6** | (livre local) |

**AWS3 est en retard d'un commit** (`852f0e2` vs `84d2c92`). SSH port 22 depuis ce LAN :
`connection refused` via middlebox `192.168.152.177` — pas un signe de panne VM.

---

## Cause 1 — Transport RFC1918 : le Mac ne peut pas rejoindre le réseau P2P

### Ce qui se passe
Le Mac tourne sur l'IP locale `10.234.49.2` (RFC1918 — adresse privée non routable).
Les 4 VMs cloud ont des IPs publiques. Depuis les VMs, `10.234.49.2` est **injoignable**
sans tunnel explicite (WireGuard, ngrok, etc.).

### Ce que ça bloque
- Les VMs ne peuvent pas envoyer de messages PBFT (PREPARE/COMMIT) au Mac
- Le Mac ne reçoit aucun bloc via P2P des seeds
- `replica_peer_allowed("10.234.49.2") = false`
- `rfc1918_requires_tunnel` flagué dans le code

### Preuve
```
/api/v1/consensus/status (Mac :8001) :
  "prepared_count": 0,
  "committed_count": 0,
  "certificate_count": 0
  
/api/v1/consensus/status (ovh-node-1 = artcb.me) :
  "pbft_primary": "ovh-node-4"  ← primaire N=4, pas rebindé N=5
  "pbft_finality.n": 5  ← membership JSON, pas un quorum actif
```

### Conséquence
Le Mac est dans la **membership JSON** (`official_pbft_replica_ids()` renvoie 5 IDs),
mais n'a jamais participé à un round PREPARE → COMMIT. N=5 dans le JSON ≠ quorum N=5 prouvé.

---

## Cause 2 — Primary non rebindé : l'époque N=4 est gelée

### Ce qui se passe
La view PBFT courante est **15**. Avec N=4 (ancienne membership), `15 % 4 = 3` = `ovh-node-4`.
Avec N=5 (membership actuelle), `15 % 5 = 0` = `ovh-node-1`.

Le champ `pbft_primary` stocké dans les seeds vaut encore `ovh-node-4` — celui de l'époque N=4.
Aucun VIEW-CHANGE N=5 n'a été exécuté depuis l'ajout du Mac dans la membership.

### Preuve
```
artcb.me /api/v1/consensus/status :
  "pbft_primary": "ovh-node-4"   ← calculé avec N=4
  "pbft_finality.primary": "ovh-node-1"  ← calculé avec N=5 (code 302)
  → deux valeurs différentes pour le même view 15
```

### Conséquence
Sans VIEW-CHANGE, le réseau ne sait pas quel nœud est le primaire avec N=5.
Aucun round PBFT N=5 ne peut démarrer sans accord de view. Certification impossible.

---

## Cause 3 — Livre Mac désynchronisé : height 6 ≠ height 1133

### Ce qui se passe
Le Mac a un livre local de **6 blocs** (tip `01a5f743…`). Le livre officiel mainnet
en est à **1133 blocs** (tip `cc0bf8a1…`). Ces deux chaînes sont **incompatibles** :
tip différent, height différent.

### Pourquoi
- Le Mac n'a pas de connexion P2P entrant (cause 1)
- Pas de sync automatique de book depuis les seeds
- Le livre local date du bootstrap initial (6 blocs de test)

### Conséquence
Même si le tunnel était actif, le Mac devrait syncer 1127 blocs avant de pouvoir
voter sur le prochain bloc. Sans synchro, ses votes PBFT porteraient sur un état incorrect.

---

## Cause 4 — SHA désynchronisé sur aws-node-3

### Ce qui se passe
aws-node-3 (`n3.artcb.me`) est sur `852f0e24134c` au lieu de `84d2c9228c4b`.
C'est un retard d'**un commit** (le rapport 303 + wrapper Doppler).

### Pourquoi
SSH port 22 depuis ce LAN est filtré. Le follow-main SSH automatique échoue.
Les timers de mise à jour des VMs ne se sont pas encore déclenchés (ou SSH est
temporairement bloqué).

### Conséquence
3/4 seeds sur le même SHA ≠ 4/4. La certification exige que toutes les seeds
soient sur `origin/main`.

---

## Cause 5 — CI GitHub absente sur tous les commits récents

### Ce qui se passe
GitHub combined status sur `84d2c92` (et `852f0e2`) :
```
state=pending
statuses=[]
check-runs total=0
```
Aucun workflow CI n'a tourné sur ces commits. **Pas de CI verte** ≠ CI qui passe.

### Pourquoi
Les workflows GitHub Actions ne sont pas configurés pour déclencher sur `push` vers `main`,
ou les runners sont désactivés, ou le fichier `.github/workflows/` est absent/incomplet.

### Conséquence
`CERTIFIED_100` exige une CI verte documentée. `pending` avec 0 check-runs n'est pas
une CI verte.

---

## Cause 6 — Ingest 409 equivocation : ce prompt n'est pas on-chain

### Ce qui se passe
Chaque prompt-agent tente d'ingérer sa trace dans la blockchain via
`POST /api/v1/ingest`. Le résultat de ce tour :
```
HTTP 409 equivocation
ingest_skipped=true
```
L'enregistrement n'a **pas** été écrit on-chain. Le dernier mémo indexé est **1131**
(char 1096, sha256 `97b69d1e…`).

### Pourquoi
Le nœud détecte une équivocation : le même agent tente d'écrire un bloc déjà existant,
ou le WorkID/SettlementID entre en conflit avec un enregistrement précédent.
Bootstrap IPv4 `:8443` = URLError (filtre LAN), puis retry HTTPS `artcb.me` = 200 health,
mais 409 à l'ingest.

### Conséquence
La trace de ce tour n'est pas on-chain. Condition de certification non remplie.

---

## Cause 7 — Doppler `restricted` casse `doppler run` sur le Mac

### Ce qui se passe
Le secret `MAC_SUDO_PASSWORD` dans le projet Doppler `artcb-1/prd` est marqué
**restricted**. Un `doppler run` standard tente de lire **tous** les secrets,
y compris les restricted. Résultat : crash immédiat du service au kickstart.

### Symptôme observé (session 303)
```
launchctl kickstart -k → uvicorn arrêté
doppler run --project artcb-1 --config prd -- uvicorn  →  FAIL (restricted)
KeepAlive launchd → boucle d'échec
```

### Correctif appliqué (303)
`scripts/artcb_mac_doppler_run.sh` : `--only-names` pour lister, puis
`--only-secrets` avec exclusion de `MAC_SUDO_PASSWORD`. Jamais `--plain`.
Ce correctif est en production. Le service tourne.

### Conséquence résiduelle
Ce bug peut réapparaître si un nouveau secret restricted est ajouté à `artcb-1/prd`
sans mettre à jour la liste d'exclusion du script. Il est actuellement corrigé,
mais la fragilité structurelle subsiste.

---

## Tableau récapitulatif

| # | Cause | Catégorie | Bloque certification | Corrigé ? |
|---|---|---|---|---|
| 1 | RFC1918 — Mac injoignable depuis VMs (pas de tunnel) | Transport | ✅ Oui | ❌ Non — tunnel absent |
| 2 | Primary PBFT non rebindé (view 15, N=4→N=5 sans VIEW-CHANGE) | Consensus | ✅ Oui | ❌ Non |
| 3 | Livre Mac height 6 ≠ livre mainnet 1133 | Consensus | ✅ Oui | ❌ Non — pas de P2P sync |
| 4 | aws-node-3 en retard d'un SHA (`852f0e2` vs `84d2c92`) | Déploiement | ✅ Oui | ❌ Non — SSH filtré |
| 5 | CI GitHub absente (0 check-runs, state=pending) | Artefact | ✅ Oui | ❌ Non |
| 6 | Ingest 409 equivocation — prompt pas on-chain | Artefact | ✅ Oui | ❌ Non — structurel |
| 7 | Doppler restricted `MAC_SUDO_PASSWORD` casse `doppler run` | Infrastructure | ⚠️ Indirect | ✅ Oui (script 303) |

---

## Ce qui fonctionne correctement (ne pas confondre avec la certification)

| Élément | État |
|---|---|
| Livre mainnet | ✅ 1133 blocs, `chain_valid=true` ×4 seeds |
| SHA seeds OVH1/OVH2/OVH4 | ✅ `84d2c92` = `origin/main` |
| PBFT finality (4 seeds) | ✅ `committed_count=45`, `certificate_count=45` |
| Mac health HTTP | ✅ 200, `git_sha=84d2c92`, `n=5` en JSON |
| GO-B/D/I/E/K/M tests | ✅ 98 passed / 2 skipped |
| Doppler service Mac | ✅ UP (après correctif 303) |
| Follow-main OVH1/OVH2/OVH4 | ✅ SHA correct |

---

## Ce qu'il faudrait pour lever CERTIFIED_100

1. **Tunnel public** pour le Mac (WireGuard/ngrok) → VMs peuvent joindre `mac-node-local`
2. **VIEW-CHANGE N=5** : après tunnel actif, un round de view-change pour rebinder le primary
3. **Sync livre Mac** : pull des 1127 blocs manquants via P2P
4. **Follow-main aws-node-3** : SSH ou timer de déploiement
5. **CI GitHub** : activer `.github/workflows/` sur `push` → `main`
6. **Ingest sans 409** : résoudre l'équivocation (WorkID/SettlementID conflit)

Ces 6 points sont **tous** nécessaires simultanément. En résoudre 5/6 ne suffit pas.

---

## Couches SHA (résumé pour référence)

| Couche | SHA | Ce que ça prouve |
|---|---|---|
| Rapport GitHub 302b | `07ed590…` | Follow-main des 4 seeds **à cet instant** |
| Commit GitHub 302b | `852f0e2…` | Le document de ce follow-main |
| Runtime après 302b (log local) | `852f0e2…` ×5 | Nouvel état post-302b — **non prouvé par 302b** |
| Seeds HTTPS ce tour | `84d2c92…` ×3 + `852f0e2` aws3 | État actuel |
| `origin/main` actuel | `84d2c9228c4b…` | Rapport 303 + wrapper Doppler |
| Mac `:8001` | `84d2c9228c4b` | Clone local = HEAD, **pas** quorum P2P |

`84d2c92` = HEAD local = OVH1/OVH2/OVH4. `852f0e2` = aws3 (retard 1 commit).
`git_sha` dans `/health` = `git rev-parse HEAD` — ce n'est pas le code **chargé en mémoire**
si le process n'a pas été redémarré après le pull.

---

*Aucun fichier modifié. Audit seul. `CERTIFIED_100=false`.*
