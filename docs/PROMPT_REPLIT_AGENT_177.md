# PROMPT — Agent Replit ARTCB (177)

Copie-colle **tout ce fichier** dans l’agent Replit.

Tu n’es **pas** autorisé à redéployer OVH1 (`152.228.144.34`).  
Replit **remplace le rôle** d’OVH1 pour les tests 174-devnet-1 (témoin / 4ᵉ participant **après** init).  
OVH1 reste volontairement en ancien code (`5b4b24ae`, décision D-036).

---

## Qui tu es, en français simple

Tu es l’agent qui habite **https://artcb--vgac42.replit.app**.

**Replit Autoscale**, c’est-à-dire un hôtel qui démarre ta chambre (conteneur) quand quelqu’un sonne, et qui **ping** la porte (`GET /`) tout de suite. Si personne n’ouvre avec un sourire (HTTP 200) pendant ~30 s, l’hôtel croit que le déploiement a **échoué** — même si tu es encore en train de déballer tes valises (pip, cmake).

**Git sync**, c’est-à-dire « aller chercher le code sur GitHub ». Avant la correction 177, cette étape se terminait **vide** : pas de dossier `.git`, ou un remote Replit **sans** le mot `github`. Résultat : tu tournais un **vieux cliché** de fichiers, et `git_sha=None` (impossible de dire quel code s’exécute).

---

## Étape 0 — Pull le correctif GitHub

Branche obligatoire :

```text
cursor/replit-sync-ready-16d8
```

Repo : `https://github.com/vgactech/artcb`

```bash
cd /home/runner/workspace   # ou le répertoire du Repl
git config --global --add safe.directory "$(pwd)"
git remote -v
# Si origin n'est pas GitHub :
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/vgactech/artcb.git
git fetch origin cursor/replit-sync-ready-16d8
git checkout -B cursor/replit-sync-ready-16d8 origin/cursor/replit-sync-ready-16d8
git reset --hard origin/cursor/replit-sync-ready-16d8
git rev-parse HEAD
git rev-parse --abbrev-ref HEAD
# Doit afficher un SHA (pas vide) et la branche ci-dessus.
```

Si `git` n’existe pas dans le déploiement Autoscale (snapshot sans `.git`) :

```bash
export ARTCB_REPLIT_BRANCH=cursor/replit-sync-ready-16d8
bash scripts/replit_start.sh
# Le script clone GitHub tout seul et écrit .artcb_release
```

Secrets Replit (panneau 🔒), **sans les coller dans le chat** :

- `ARTCB_REPLIT_BRANCH` = `cursor/replit-sync-ready-16d8`
- `ARTCB_WALLET_PASSPHRASE` = mot de passe fort (32+ caractères), **pas** un secret cloud OVH
- `DOPPLER_TOKEN` seulement si déjà présent (projet `artcb-blockchain`) — **ne pas** y mettre Stripe
- `ARTCB_CORS_ORIGINS` = `https://artcb--vgac42.replit.app`

Redémarre le Repl / Redeploy Autoscale **après** le checkout.

---

## Étape 1 — Vérifier que le déploiement est « détecté »

Attends que le shim ou uvicorn réponde.

```bash
curl -sS https://artcb--vgac42.replit.app/live
curl -sS https://artcb--vgac42.replit.app/health
curl -sS https://artcb--vgac42.replit.app/api/v1/health
curl -sS -o /dev/null -w "%{http_code}" https://artcb--vgac42.replit.app/api/v1/chain/verify
```

**PASS minimum (détection) :**

| Route | Attendu |
|-------|---------|
| `/live` | **200** `{status:alive}` même pendant le bootstrap |
| `/` | **200** (page ou JSON bootstrap) |
| `/health` et `/api/v1/health` | **200**, `git_sha` **non null**, `git_branch` = `cursor/replit-sync-ready-16d8` |
| `/api/v1/chain/verify` | **200** (en bootstrap : `valid=false`, `bootstrap_mode=true`) — **plus jamais 404** |

Si `git_sha` est encore `null` : lis `logs/startup_*.log` et cherche `step=git_sync`. Copie les lignes `STEP begin` → `STEP end` dans ton rapport (pas de secrets).

---

## Étape 2 — Cryptographie (PQC)

Les nœuds OVH2 / AWS3 / OVH4 signent en **Ed25519 ET ML-DSA-65** (les deux cadenas + tampon).  
Un Replit en **Ed25519 seul** n’est **pas** le même protocole crypto.

```bash
curl -sS https://artcb--vgac42.replit.app/health | python3 -m json.tool
# pqc.available doit devenir true
# pqc.algorithm = ML-DSA-65
# pqc.policy.hybrid_verify_mode = AND  (quand le nœud n'est plus bootstrap)
```

Le script compile **liboqs natif 0.16.0** dans `$HOME/_oqs` (plus le mélange 0.16 Python + 0.13 natif).

Si après un redémarrage `pqc.available=false` :

```bash
export OQS_INSTALL_PATH="$HOME/_oqs"
export LD_LIBRARY_PATH="$OQS_INSTALL_PATH/lib:$OQS_INSTALL_PATH/lib64:$LD_LIBRARY_PATH"
bash scripts/install_native_liboqs_replit.sh
ls -l "$HOME/_oqs/lib"/liboqs.so*
"$HOME/venv/bin/python3" - <<'PY'
import os
os.environ.setdefault("OQS_INSTALL_PATH", os.path.expanduser("~/_oqs"))
from src.artcb.crypto.pqc import pqc_available
print("pqc_available", pqc_available())
import oqs
print("oqs pkg ok, mechs sample", [m for m in oqs.get_enabled_sig_mechanisms() if "ML-DSA" in m or "Dilithium" in m][:8])
PY
```

Ne dis **pas** « package absent » si `pip show liboqs-python` réussit. Dis : **binding Python OK, backend natif incompatible / trop vieux**.

---

## Étape 3 — Identité persistante (sortir du bootstrap)

Les 503 sur `/api/v1/chain`, `/wallet/list`, `/pol/score` veulent dire : **le nœud n’a pas encore de wallet**. C’est normal **avant** init. Ce n’est pas un crash.

Quand PQC est `available=true` (ou si tu dois init quand même, note-le) :

```bash
# password = la valeur Replit ARTCB_WALLET_PASSPHRASE (ne l'affiche pas)
curl -sS -X POST https://artcb--vgac42.replit.app/setup/init-node \
  -H 'Content-Type: application/json' \
  -d '{"node_name":"replit-node-1","password":"***","public_url":"https://artcb--vgac42.replit.app"}'
```

Sauvegarde `seed_hex` dans un fichier **local Replit** chmod 600. **Ne l’imprime pas** dans le rapport. Redémarre. Vérifie :

- `/health` → `bootstrap_mode: false`
- `/ready` → 200 si SHA + PQC OK
- `p2p_node_id` commence par `artcb1…` (plus `bootstrap_localhost`)

---

## Étape 4 — S’annoncer aux trois nœuds 174 (pas OVH1)

```text
OVH2  http://151.80.107.29:8000
AWS3  http://51.44.222.232:8000
OVH4  http://91.134.45.8:8000
Replit https://artcb--vgac42.replit.app
```

Depuis Replit (et inversement) :

```bash
for T in http://151.80.107.29:8000 http://51.44.222.232:8000 http://91.134.45.8:8000; do
  curl -sS -X POST "$T/api/v1/p2p/register-public" \
    -H 'Content-Type: application/json' \
    -d '{"node_public_url":"https://artcb--vgac42.replit.app","device_fingerprint":"replit-node-1-177","node_label":"replit-node-1","network_id":"artcb-devnet-1"}'
  echo
done
curl -sS -X POST https://artcb--vgac42.replit.app/api/v1/p2p/register-public \
  -H 'Content-Type: application/json' \
  -d '{"node_public_url":"http://151.80.107.29:8000","device_fingerprint":"replit-to-ovh2","node_label":"ovh2","network_id":"artcb-devnet-1"}'
```

Vérifie que le pair Replit stocké ailleurs a `scheme=https` / `base_url` commençant par `https://` (pas `http://…:443`).

**Ne pas** enregistrer Replit comme s’il était OVH1. **Ne pas** étendre la chaîne legacy OVH1.

---

## Étape 5 — Ton rapport (obligatoire)

Écris `rapports/REPLIT_177_RETOUR.md` **dans le Repl** (et pousse-le seulement si tu as le droit GitHub ; sinon colle le markdown à l’agent Cursor).

Structure :

```text
1. SHA exécuté (git rev-parse HEAD) + git_sha de /health
2. git_sync : extraits de log (pas de secrets)
3. Tableau routes : /live /ready /health /chain/verify + codes HTTP
4. pqc.available, versions liboqs native vs liboqs-python, ML-DSA-65 oui/non
5. bootstrap_mode avant/après init-node (sans seed)
6. register-public : HTTP + kem_public_bytes (longueur seulement)
7. Si FAIL : section « CE QUE CURSOR DOIT FAIRE »
```

### Si le problème n’est **pas** réglé — quoi demander à Cursor

Selon le symptôme :

| Symptôme | Cursor doit |
|----------|-------------|
| `git_sync` toujours vide, SHA=None | Corriger encore `replit_start.sh` ; vérifier que Autoscale exécute bien ce script ; éventuellement forcer un `run` qui clone avant tout |
| `/` encore 500 les 30 premières secondes | Vérifier que `replit_live_shim.py` est lancé **en premier** ; que rien d’autre ne vole le port 5000 avec un 500 |
| `/api/v1/chain/verify` encore 404 | Le snapshot n’a pas le `main.py` 177 — le pull n’a pas eu lieu |
| `pqc.available=false` + warning 0.13 vs 0.16 | Le `.so` 0.16 n’est pas en tête de `LD_LIBRARY_PATH` ; Cursor doit durcir le chemin Nix / retirer le 0.13 du cache pip |
| init-node échoue | Coller le JSON d’erreur **sans** password/seed |
| register-public 500 / `http://host:443` | Bug scheme encore présent sur le nœud **cible** (OVH2/AWS3/OVH4 pas hotfix 177) — Cursor hotfix ces nœuds **sauf OVH1** |
| `/ready` 503 après init + PQC OK | Cursor assouplit `/ready` (trop strict) |

**Interdit dans ton rapport :** jetons Doppler, seeds, mots de passe, clés OVH.

---

## Ce que tu ne fais pas

- Pas de `git push` vers `152.228.144.34` / pas de SSH OVH1
- Pas de certification mainnet
- Pas de « DV-04 PASS » : même si Replit rejoint le triangle, DV-04 C veut **4** nœuds **174** ; Replit compte seulement **après** `/ready` 200 + hybride AND + sync tip
- Pas de mélange tokenomics (V-01…V-07) avec ce rapport

Quand c’est vert : dis clairement « Replit = nœud 174 de substitution, OVH1 toujours témoin legacy ».
