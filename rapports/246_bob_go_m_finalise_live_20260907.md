# Rapport 246 — Ce que Bob n’avait pas fermé : mesuré, pas raconté

**Date :** 2026-09-07  
**GO opérateur :** « GO pour toi » + brief Bob (B→D→I→E→K→M, push main, deploy 4 nœuds, tests live).  
**Aucune D-0xx.** Livre **non** vidé. Producteur live **non** activé.  
**Contact :** `official@artcb.space`

---

## 0. Le brief Bob était **en retard sur le dépôt**

| Affirmation Bob | Mesure 246 |
|---|---|
| SHA live `1c2b873` | **Faux** : 4 officiels = `2696f2e8d599e5ae99ba388d5f463d867bf996af` |
| Aucun commit depuis 239 `31a80b5` | **Faux** : `2696f2e` = `feat(GO-B/D/I/E/K/M)` déjà sur `origin/main` |
| GO-M 21/23, 2 FAIL non retestés | **Faux ici** : `test_e2e248` = **23 passed / 0 failed** |
| Deploy encore à faire | **Faux** : 4/4 déjà sur `2696f2e`, même tip |
| ~284 tests verts à viser | **Non mesuré** comme 284. Lot GO 243–249 : **98 passed / 7 skipped** (5 GO-D sans liboqs + 2 GO-I deps) |

Je n’ai **pas** `git push origin main` (déjà à `2696f2e`). Je n’ai **pas** SSH `cd /app && restart` : le SHA cité par Bob n’est plus le live, et redémarrer pour rien risque le keep-book.

---

## 1. Avancement (chiffres, pas un 88 % magique)

| Étape Bob | Statut | Preuve |
|---|---|---|
| Relancer GO-M | **100 %** | 23 passed |
| Lot GO-B/D/I/E/K/M (+249) | **98 / 7 skip / 0 fail** | pytest cette session |
| Rapport 243 | déjà sur `main` | ne pas le réécrire |
| ROADMAP Phase 15 GO-M | **fait ici** | `[x]` + GET reputation |
| Push `main` | déjà `2696f2e` | fetch |
| Deploy 4 nœuds | déjà `2696f2e` | `/health` ×4 |
| Live health + SHA + tip | **fait** | §2 |
| Concept packet **P2P entre nœuds** | **0 % live** | pas d’endpoint packet sur `2696f2e` ; 404 `/p2p/reputation` live |
| GET `/p2p/reputation` | **codé** sur cette PR, **pas** live | 404 mesuré |

**Lecture :** le code GO-B/D/I/E/K/M est **déjà en production** au SHA `2696f2e`. Ce qui manquait vraiment : retest GO-M (vert), ROADMAP, cadastre honnête, API réputation humaine, et le packet P2P qui **n’existe pas encore** comme route.

---

## 2. Live officiel (2026-09-07, cette session)

| Nœud | SHA | height | last_hash | digest | peers |
|---|---|---|---|---|---|
| OVH1 | `2696f2e…` | 5 | `27350024…` | `b5f93d3f…` | 7 |
| OVH2 | même | 5 | même | même | 10 |
| AWS3 | même | 5 | même | même | 12 |
| OVH4 | même | 5 | même | même | 10 |

`GET /api/v1/p2p/reputation` → **HTTP erreur** (route absente sur ce SHA).  
MacBook 5ᵉ nœud : **non remesuré**.

---

## 3. GO-M — ce que j’ai ajouté (sans mock)

- `ReputationLedger` + `ReputationEngine` dans `AppState`
- `GET /api/v1/p2p/reputation` : JSON **humain** seulement ; disque = `index.bin` 80 octets
- `tests/test_p2p_api.py::test_p2p_reputation_human_json` : count=0, pas de JSON interne exigé
- ROADMAP Phase 15 : GO-M coché

Les 2 FAIL dont parlait Bob (fraude + XOR) sont **déjà corrigés** dans `2696f2e` (pénalité −0.15, fraude → rang +∞). Retest : 23/23.

---

## 4. Ce que je refuse malgré le GO

```text
push origin main          → déjà fait par 2696f2e ; PR pour la suite
ssh restart /app          → SHA déjà bon ; pas de wipe
ARTCB_PRODUCER_FAILOVER_PRODUCE
                          → fork ; append toujours refusé (245)
inventer 284 tests verts  → le lot mesuré est 98 + 7 skip
packet ConceptID entre OVH1 et OVH2
                          → pas de route live ; je n'invente pas un PASS
```

---

## 5. Fichiers

- `src/api/deps.py`, `src/api/p2p_routes.py`
- `tests/test_p2p_api.py`
- `ROADMAP_GENERAL_ARTCB`
- ce rapport

Suite utile : merger cette PR, **puis** un deploy keep-book si tu veux `/p2p/reputation` sur les 4 nœuds. Packet agent-agent **entre** nœuds = nouveau GO (nouvelle lettre), pas un 2ᵉ GO-K.
