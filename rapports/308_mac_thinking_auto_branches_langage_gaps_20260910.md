# R308 — Réponses mesurées : Mac, thinking, auto-protocole, branches, langage IA, gaps

**UTC :** 2026-09-10T16:25:00Z  
**CERTIFIED_100 :** `false`  
**SHA live mesuré ×5 :** `c8fa132a4d37778e042c8085255e1b392fbb5e5b` = `origin/main`  
**Seeds tip :** height **1136** / `9b887495dab8963b…` (commun ×4)  
**Ingest ce tour (prompt correct) :** HTTP 200, block **1135**, hash `9b887495…` (puis tip 1136 après second mémo) ; `includes_thinking=false`

## 1. Mac = nœud fonctionnel ? → **NON** (PBFT opérationnel)

| Critère | Mesure |
|---------|--------|
| Process local `:8001` health 200 | **OUI** |
| Même SHA que `origin/main` | **OUI** (`c8fa132…`) |
| Dans membership JSON `n=5` | **OUI** (`mac-node-local`) |
| Dans seeds IPv4 `OFFICIAL_COMPUTE_NODE_IDS` | **NON** |
| Même tip que seeds (1136 / `9b887495…`) | **NON** (height **6** / `01a5f743…`) |
| Même view que seeds (17 / aws-node-3) | **NON** (view **0**) |
| Tunnel public / fan-out P2P | **NON** (`ARTCB_MAC_TUNNEL_*=unset`, ngrok absent) |
| PREPARE/COMMIT 307 | **NON** (seeds ×4 seulement) |

**Verdict :** Mac = process + membership **identité**, **pas** replica PBFT fonctionnel sur le livre officiel.

## 2. Accord audit GitHub PREPARE/COMMIT Q=3

- PASS seeds **4/4** PREPARE/COMMIT + writes (artefact `logs/307_p0_prepare_commit_probe.json`) : **retenu**.
- **`CERTIFIED_100=false`** : **retenu** — ne pas lever.
- Correction importante : membership live = **N=5, F=1, Q=3** (Mac inclus en JSON). Le PASS 307 = quorum sur **4 seeds**, pas « N=5 certifié ». Formule historique `n_f_q(4)` ≠ membership actuelle.

## 3. Thinking → ARTCB ?

| Couche | État |
|--------|------|
| Hook `afterAgentThought` → `data/trace/agent_thoughts.jsonl` | **OUI** local (510 lignes) |
| `artcb_bound=true` | **0 / 510** |
| Note journal | `local_only_not_artcb` |
| Ingest memo `includes_thinking` | **false** (obligatoire) |
| CoT privé modèle → disque / ARTCB | **NON** (pas accessible) |

**Verdict : NON** — thinking **intercepté localement** (surfacé), **volontairement pas transmis** à ARTCB (règles 17/40/44).

## 4. Toutes fonctionnalités ARTCB auto chaque tour ?

**NON pas à 100 %.** Adapter Cursor + bootstrap + hooks existent ; l’agent peut encore omettre une relecture / un follow-main SSH (LAN filtré). Ce tour : ingest OK, live ×5 mesuré, Mac UP. Pas d’automation magique « tout ARTCB » sans discipline.

## 5. Toutes les branches finalisées ?

**NON.** `main` = défaut. Remotes : **~109** branches ; **~19** `--no-merged` vers `origin/main` (ex. nombreuses `cursor/*`). Local : `main` + `pr57` + branches cursor. `gh` absent sur ce PATH → issues/PR GitHub non listées ici.

## 6. Langage IA complètement finalisé ?

**NON.** i18n UI 7 langues ≠ langage IA ConceptID/IR natif. Rapports 238/252–256 : IR ≠ langage IA final ; test ConceptID bout-en-bout **non clos**. T-071-11 i18n checklist encore `[ ]` dans LISTE (doc historique).

## 7. Gaps encore ouverts (inventaire honnête — pas CERTIFIED_100)

| Domaine | État |
|---------|------|
| Mac tip×5 / tunnel / PREPARE Mac | **FAIL / NOT_PROVEN** |
| Chaos L/M/N (SSH IPv4) | **NOT_RUN** (Connection refused) |
| N04 50 % | **FAIL last** (historique T-E60…T-E68) |
| C04 thousands | **NOT_PROVEN / FAIL** historique |
| CI GitHub combined | souvent `statuses=[]` |
| T-071-03…13 checkboxes | encore `[ ]` (plusieurs endpoints AI live 200 aujourd’hui : status/context/search/bootstrap) |
| Q-E04/E10/fee-oracle/HBP ancres | ⏳ dans QUESTIONS_OUVERTES |
| TPM L4 / OVH L3 | NOT_APPLICABLE / NOT_REACHABLE |
| Wipe | **jamais** |

## 8. Oublis à préciser (ajoutés)

1. **Seeds ≠ membership** (N=4 fan-out vs N=5 JSON).  
2. **Hauteur égale ≠ même tip** — ici tip seeds commun mesuré ×4.  
3. **Health 200 ≠ replica PBFT.**  
4. **Thinking local ≠ on-chain** (volontaire).  
5. **Ingest prompt ≠ thinking / system / tokens.**  
6. **PASS Q=3 seeds ≠ tip×5 ≠ chaos ≠ CERTIFIED_100.**  
7. Branches mortes `cursor/*` ≠ « finalisé » tant que non mergées/archivées.  
8. Langage IA natif ≠ i18n frontend.

## Suite prioritaire (ordre P0)

1. Tunnel public Mac → sync tip / PREPARE-COMMIT observable.  
2. Chaos seulement après Mac + primary stables.  
3. Ne pas lever `CERTIFIED_100`.
