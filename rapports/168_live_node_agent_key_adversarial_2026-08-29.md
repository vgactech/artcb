# Rapport 168 — Clé API agent + nœud live automatique + replay adversarial

**Horodatage UTC :** 2026-08-29T19:52:00Z  
**Branche :** `cursor/live-node-agent-key-475d`  
**Base :** `origin/main` = `4dfc154` (merge PR #36 / Simulation 167)  
**Commit :** `a5fa64380f907b672a0b75be5678dbbd55841467`  
**Ne jamais écraser** 160–167. Run 167 191605 **conservé**.

**Aucun token `artcb_…` n’est reproduit ici.**

---

## 0. Mission

Rendre le nœud OVH **utilisable à chaque prompt** sans rappel : créer une clé API réelle, l’intégrer (Doppler + fichier nœud + bootstrap agent), et attaquer le SettlementID (replay) comme le demandait l’audit post-167.

Expertises : auth wallet/session, secrets Doppler (métadonnées), SSH, SDK/MCP, invariants de settlement.

---

## 1. Pourquoi ça ne marchait pas tout seul

| Élément | État avant 168 |
|---------|----------------|
| Cursor secrets | `ARTCB_API_KEY` **absent** |
| Doppler | pas de `ARTCB_API_KEY` |
| Nœud live | 0 wallet, 0 clé (`/api-keys/list` count=0) |
| `POST /api-keys/generate` | exige `sess_…` (login wallet) |
| Agents | parlaient à `localhost:8000` par défaut |

Donc : **pas de clé à inventer dans le chat**, et pas d’activation magique sans provisionnement.

---

## 2. Solution retenue (automatique)

```
Cursor prompt
    ↓
scripts/artcb_live_bootstrap.py     ← AUTO_PROMPT + .cursor/rules
    ↓
ARTCB_API_KEY depuis, dans l’ordre :
    1. secret Cursor
    2. Doppler ARTCB_API_KEY
    3. ~/.artcb/cursor_agent.env
    4. SSH ubuntu@152.228.144.34:~/.artcb/cursor_agent.env
    ↓
GET /health + GET /api-keys/me
    ↓
SDK / MCP / HTTP utilisent le nœud live
```

Nœud : `http://152.228.144.34:8000`  
Wallet créé sur le nœud : `cursor-cloud-agent`  
Adresse (publique) : `artcb1cnclv0ulcrhjg3zcg0tw24ldtt74tdcgnsxs4p`  
`key_id` : `kid_abad2468682059ef`  
Scopes : `read`, `write`, `mining` — **pas** admin  
Preview : `artcb_c769d4…af65`

Fichier nœud (600, jamais git) : `/home/ubuntu/.artcb/cursor_agent.env`

---

## 3. Exécution réelle (pas inventée)

### Provision

`scripts/provision_live_agent_key.py` → wallet créé, clé générée via login localhost sur le nœud, `/api-keys/me` **200**.

### Doppler

- Premier essai `PUT` : HTTP 404 (mauvaise méthode).
- `POST /v3/configs/config/secrets` : **success=true**.
- Relu : `ARTCB_API_KEY` présent (len=70, préfixe `artcb_`), `ARTCB_API_URL` = live, `ARTCB_AGENT_KEY_ID` = `kid_abad2468682059ef`.

Le token Doppler Cursor est un **service token** `artcb-node-1` (lecture + cette écriture a réussi). Toujours **un token par usage** (L-036) : cette écriture n’en crée pas un nouveau.

### Bootstrap

`scripts/artcb_live_bootstrap.py` exit 0 :

- health 200, PQC ML-DSA-65
- economics 200, protocol/status 200, `h_adult=0`
- `git_sha=084f32eb…` branche **`cursor/ovh-deploy-stripe-secrets-475d`** (166)

**Le nœud live n’est pas encore sur `main` 167.** 168 n’a **pas** redéployé (pas d’ordre).

### Preuve d’usage réel de la techno

`POST /api/v1/ai/memo` (Bearer agent) → **HTTP 200**

| Champ | Valeur lue |
|-------|------------|
| block_index | 0 |
| pol_score | 0.75 |
| block_hash | `8d542e496f58485d…53be8308` |
| message | Observation gravée en bloc #0 — immuable ML-DSA-65 |

### Simulation 168

`simulations/20260829T195130Z_e2e168_adversarial_live/`  
`18_summary.json` : `failures=[]`, `invented=false`

| Invariant | Résultat |
|-----------|----------|
| WorkID-X consommé 1 fois | true |
| Tous les replays rejetés | true |
| WorkID-Y unique | true |
| Live health + clé | true (`me_http=200`) |

Ce n’est **pas** BFT réseau, ni sync de blocs, ni certification mainnet.

---

## 4. Ce que vous devez faire une fois (Cursor UI)

Pour que **chaque** agent Cloud reçoive la clé **sans SSH** :

1. Doppler → projet `artcb-blockchain` / config `dev` → copier `ARTCB_API_KEY` (déjà écrit).
2. Cursor → Environment secrets → ajouter **`ARTCB_API_KEY`** (et optionnel `ARTCB_API_URL=http://152.228.144.34:8000`).

Sans cette copie UI, les agents qui ont déjà `DOPPLER_TOKEN` s’en sortent : le bootstrap **lit Doppler**. C’est le chemin automatique de cette session.

Ne pas coller la clé dans le chat.

---

## 5. Fichiers

- `src/artcb/live.py` — résolution URL/clé
- `scripts/provision_live_agent_key.py` / `scripts/artcb_live_bootstrap.py`
- `scripts/run_sim168_adversarial_live.py`
- `.cursor/rules/artcb-live-node.mdc` (`alwaysApply`)
- SDK / MCP : `ARTCB_API_URL` + Bearer

---

## 6. Pytest

Log : `logs/20260829_pytest_rapport168.txt`

**618 passed / 8 skipped / 0 fail** (env live isolé : `ARTCB_API_URL` / `ARTCB_API_KEY` retirés du process pytest).

Échec transitoire avant isolation : MCP default URL = nœud live. Tests localhost isolés ensuite.

---

## 7. Orange / pas fait

- Nœud toujours en **166** (`084f32e`), pas `4dfc154`
- Pas de déploiement `main`
- Replay 168 = ledger local + probe live, pas 4 nœuds libp2p
- V-01…V-07 toujours ouverts
- Token Doppler Cursor = encore le token nœud (rotation dédiée toujours recommandée)

---

## 8. Avancement

| Couche | % |
|--------|---|
| Clé live + bootstrap auto | **~95 %** (manque secret Cursor UI) |
| Replay SettlementID | **fait en sim** |
| Nœud = `main` 167 | **0 %** (non déployé) |
| Protocole global | **~97.5 %** |
