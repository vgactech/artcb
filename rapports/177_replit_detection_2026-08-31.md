# Rapport 177 — pourquoi Replit « ne détecte pas » le déploiement

**OVH1 non redéployé** (`5b4b24ae`). D-036 + **D-038** : Replit prend le *rôle* d’OVH1 pour les tests 174.

URL : `https://artcb--vgac42.replit.app`  
Branche à tirer : `cursor/replit-sync-ready-16d8`  
Prompt agent : `docs/PROMPT_REPLIT_AGENT_177.md`

---

## En une phrase

Le healthcheck Autoscale sonne à la porte **pendant que le script déballe encore les cartons**, et `git_sync` **ne tirait pas GitHub** — donc SHA=None et code figé.

---

## Pourquoi ce n’est pas « magiquement détecté »

**Détecté**, c’est-à-dire : Replit Autoscale considère le déploiement **vivant** si `GET /` rend **200** assez vite.

Or le log du 31 août :

```text
21:30:37  public_url ok
21:30:37  healthcheck / → 500   (répété ~30 s)
21:30:37  git_sync begin → end   (RIEN au milieu)
21:31:07  GET / → 200
```

Comparaison : tu ouvres un restaurant ; l’inspecteur arrive **pendant que tu installes les fourneaux**. Il note « fermé / 500 ». Une demi-heure plus tard les clients mangent. L’inspecteur a déjà écrit « déploiement raté ».

**Quatre étages** (l’expert a raison) :

| Étage | Sens | Replit 31/08 |
|-------|------|----------------|
| Process alive | le script tourne | oui |
| Server listening | un port répond | parfois un vieux 500 |
| Application ready | FastAPI + deps | ~30 s plus tard |
| Blockchain ready | identité + chaîne + PQC | **non** (bootstrap + Ed25519 only) |

---

## Cause n°1 — `git_sync` no-op (le vrai « pas détecté côté code »)

Ancien test :

```bash
if [ -d .git ] && git remote -v | grep -q github; then git pull …
```

Sur Autoscale : souvent **pas de `.git`**, ou un remote Replit **sans** le mot `github`.  
La condition est fausse → **aucune ligne « Pull GitHub »** → STEP begin/end vides → `release.py` ne trouve ni env ni git → **`sha=None`**.

Ce n’est pas que GitHub n’a pas reçu le push. C’est que **la chambre Replit n’est pas allée chercher le nouveau carton**.

Correctif : clone si pas de `.git` ; sinon `fetch` + `reset --hard` sur `ARTCB_REPLIT_BRANCH` ; écrire `.artcb_release`.

---

## Cause n°2 — healthcheck trop tôt

Correctif : `scripts/replit_live_shim.py` répond **200** sur `/` et `/live` **avant** pip. Puis uvicorn prend le port 5000.  
`GET /live` = « je respire ».  
`GET /ready` = « je peux vraiment travailler ».

---

## Les autres points du log (déjà expliqués, maintenant câblés)

| Log | Sens | Correctif 177 |
|-----|------|----------------|
| liboqs 0.13 ≠ python 0.16 | cadenas natif trop vieux, ML-DSA-65 OFF | compiler **0.16.0** dans `$HOME/_oqs` |
| « package absent » | mensonge : pip a le binding | message honnête |
| bootstrap_localhost | pas encore de wallet nœud | init-node (prompt) |
| chain/wallet/pol 503 | routes coupées en bootstrap | normal ; pas un 500 |
| `/api/v1/chain/verify` 404 | route listée mais **jamais montée** ; catchall 404 | route bootstrap **200** + JSON |
| TenSEAL simulé | calcul homomorphe jouet | rester honnête |
| FAISS AVX2 puis OK | plan B processeur | PASS |

---

## Ce que Cursor a poussé (à tirer par Replit)

- `scripts/replit_start.sh` — vrai git_sync + shim + liboqs 0.16
- `/live` `/ready` + `chain/verify` bootstrap
- Pairs **https** + `advertised_base_url` (sinon Replit devient `http://host:443`)
- Prompt : `docs/PROMPT_REPLIT_AGENT_177.md`

**Pas de certification mainnet. Pas de DV-04 PASS.**  
Si Replit devient 174 + hybride AND + tip aligné, on aura **4** protocol-compatibles **sans** toucher OVH1 (option B de l’expert, avec Replit = NODE-R).
