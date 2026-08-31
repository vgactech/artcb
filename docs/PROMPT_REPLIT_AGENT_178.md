# PROMPT — Agent Replit ARTCB (178) — audit, PAS de wallet

Copie-colle **tout ce fichier**. Tu n’es **pas** autorisé à redéployer OVH1 (`152.228.144.34`).  
Tu n’es **pas** autorisé à appeler `POST /setup/init-node` dans cette phase (V-R05 bloqué).

Branche : `cursor/replit-sync-ready-16d8`  
Repo : `https://github.com/vgactech/artcb`

---

## Ce que l’expert a tranché

`pqc.available=true` dans `/health` = **liboqs chargée**.  
Ce n’est **pas** : « toutes les signatures critiques sont hybrid AND ».  
Ne réécris **pas** « il n’y a plus de fallback Ed25519 ». La politique D-032 autorise Ed25519 jusqu’au **2026-12-31T00:00:00Z**.

Git : **Architecture A** seulement. Fetch + checkout d’un **SHA épinglé**. Pas de `git reset --hard` sur le tip flottant de la branche.

---

## Étape 0 — Checkout déterministe

```bash
cd /home/runner/workspace
git config --global --add safe.directory "$(pwd)"
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/vgactech/artcb.git
git fetch origin cursor/replit-sync-ready-16d8
# Remplace PIN par le SHA que Cursor a publié pour 178 (git rev-parse origin/cursor/replit-sync-ready-16d8)
PIN="$(git rev-parse origin/cursor/replit-sync-ready-16d8)"
echo "$PIN"
git checkout --detach "$PIN"
git rev-parse HEAD
```

Secrets Replit (🔒, **ne pas coller** dans le chat) :

- `ARTCB_REPLIT_PIN_SHA` = le SHA ci-dessus (40 hex)
- `ARTCB_REPLIT_BRANCH` = `cursor/replit-sync-ready-16d8`
- **Pas** de création de `ARTCB_NODE_WALLET_ADDRESS` maintenant

Redeploy Autoscale **après** le checkout + le secret PIN.

---

## Étape 1 — V-R01 (commit réellement servi)

Attends que `/live` ne dise plus `phase=replit_shim` (sinon uvicorn n’a pas pris le port).

```bash
curl -sS https://artcb--vgac42.replit.app/live
curl -sS https://artcb--vgac42.replit.app/ready ; echo
curl -sS https://artcb--vgac42.replit.app/api/v1/health | python3 -m json.tool
```

**PASS V-R01 public :**

| Champ | Attendu |
|-------|---------|
| `/live` | 200 `{status:alive}` **sans** `phase=replit_shim` |
| `/api/v1/health` | 200 FastAPI : `git_sha` = PIN, `release_integrity` = `ok` |
| `/ready` | **503** (`bootstrap_mode` ou `not_ready`) — **pas** 200 |

Si `/health` est encore `{status:alive, phase:replit_shim}` : uvicorn n’est pas lié. Copie `logs/startup_*.log` `step=uvicorn` (pas de secrets). Section « CE QUE CURSOR DOIT FAIRE ».

---

## Étape 2 — V-R02 / V-R03 (disponibilité ≠ enforcement)

Dans le JSON `/health` :

```text
pqc.available                         # true/false mesuré
pqc.availability_is_not_enforcement   # doit être true
pqc.high_value_hybrid_enforced        # doit être false
pqc.ed25519_only_still_accepted       # true tant que fenêtre D-032
```

Ne conclus **pas** « PQC obligatoire partout ». Dis : « ML-DSA-65 **détecté** » ou « **non détecté** ».

---

## Étape 3 — V-R04 (bootstrap, pas de seed)

```bash
curl -sS -o /tmp/w.json -w "%{http_code}" https://artcb--vgac42.replit.app/api/v1/wallet/list ; echo
python3 -m json.tool /tmp/w.json
# status=bootstrap_required
# wallet_initialized=false
# reason=wallet_initialization_required
```

Interdit : créer un wallet, afficher une seed, écrire une passphrase dans le rapport.

Vérifie qu’aucun fichier `*seed*` n’existe sous `data/` **avant** init.

---

## Étape 4 — Rapport

Écris `rapports/REPLIT_178_RETOUR.md` (ou colle à Cursor) :

```text
1. git rev-parse HEAD vs git_sha /health vs PIN secret (le SHA seulement)
2. phase shim ou FastAPI ?
3. Tableau /live /ready /health + codes
4. pqc.available + les 3 champs enforcement
5. JSON 503 wallet/list (sans secrets)
6. Si FAIL : CE QUE CURSOR DOIT FAIRE
```

### Si ce n’est pas réglé

| Symptôme | Cursor doit |
|----------|-------------|
| Toujours shim sur l’URL publique | Uvicorn ne bind pas ; logs `step=uvicorn` ; possible shim orphelin sur :5000 |
| `git_sha` ≠ PIN | `release.py` / ordre env vs fichier |
| `release_integrity=pin_mismatch` | Secret PIN ≠ code servi |
| `/ready` 200 en bootstrap | Régression 178 |
| Rapport qui dit « plus de fallback Ed25519 » | Cursor corrige le texte ; le code D-032 n’a pas changé |
| Tentation d’init-node | **Refuser** — attendre GO V-R05 |

**Interdit :** Doppler, seeds, mots de passe, SSH OVH1, « DV-04 PASS ».
