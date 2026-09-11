# R316 — LOCAL_BOOK_ORIGIN_AUDIT + langage IA (parallèle) + ports

**UTC :** 2026-09-11T18:20:00Z  
**CERTIFIED_100 :** `false`  
**SHA attendu :** (ce commit) sur `main`

## 1. Pourquoi le Mac a un livre `private` 0..8 ? (avant quarantine)

**Hypothèse retenue :** `LOCAL_PRIVATE_SANDBOX_THEN_PRIVATE_MEMOS`

| Lignes | Timestamp | Kind |
|--------|-----------|------|
| index 0–4 | **2026-09-05T22:48Z** | `private_local_graph_bootstrap` (`g_*`, Bob / install locale) |
| index 5 | 2026-09-07 | `private_bob_agent_memo` (`bob_agent_235` / `pol_work`) |
| index 6–8×2 | 2026-09-10/11 | `private_ai_thought_memo` (`agent_thought_surfaced`) |

- Seed block0 : **2026-09-01** public `b8a7d5ef…` / `g_29b131e92c84`
- Mac block0 : **2026-09-05** private `8ee26e84…` / `g_38c95570b8f1`
- Labels `network_id` / `genesis_hash` identiques **≠** hash bloc 0
- Doublon **index 8** = deux mémos thinking concurrents (même `prev`, même seconde)

**Ce n’est pas** : corruption P2P, ni fork causé par Wi‑Fi.  
**C’est** : sandbox privée locale (Bob) devenue le `blocks.jsonl` principal du nœud, puis mémos private (thinking local `:8001`) empilés dessus.

**Gap architectural :** un seul livre sans gate `canonical_genesis_block_hash` avant écriture/sync.

**Quarantine :** dry-run seulement — **pas de GO auto**. Préserver forensique. Pas wipe seeds.

Script : `scripts/artcb_r316_local_book_origin_audit.py` → `logs/316_local_book_origin_latest.json`

## 2. Ports — clarification (audit 8000 vs 18444)

| Port | Rôle |
|------|------|
| **8000** | API HTTP FastAPI / sync hybride historique (`BOOTSTRAP_NODES` IPv4) |
| **18444** | P2P natif documenté (`chain_params.h`, `node_identity`) |
| **443** | HTTPS relay mesuré OK (R314) |

Doctor R316 renomme : `api_tcp_outbound_8000` + `p2p_native_tcp_18444` + `https_relay_outbound_443` + probe IPv6 AAAA.  
`BOOTSTRAP_NODES` : **ajoute** `https://artcb.me` / `n2|n3|n4` (sans supprimer IPv4:8000 — R299).

Cible transport : IPv6 → IPv4:18444 → overlay → HTTPS:443 → offline/resume — **pas** « tout = :8000 ».

## 3. Langage IA — travail en parallèle (pas 100 %)

| Mesure | Résultat |
|--------|----------|
| Pytest IR/GO-K/258 probes | **44 PASS** |
| Live FR/EN/ES probe (`Kc55d3ab…` ×3 ×4 seeds) | **PASS** overlap=1 |
| Live `voiture`/`car`/`coche` | **FAIL** (IDs distincts — pas convergence universelle) |
| Agent A→B sans texte | **NOT_PROVEN** |
| Ancre ledger ×4 | **NOT_PROVEN** |
| Campagne R253 native E2E | **NOT_PROVEN** |
| `langage_ia_final` | **false** |

Script : `scripts/artcb_langage_ia_live_matrix.py` → `logs/316_langage_ia_matrix_latest.json`

## 4. Inventaire tâches rapports 310–315 (non oubliées)

| Tâche | État tour |
|-------|-----------|
| R316 origin audit | **FAIT** |
| Quarantine / catch-up Mac | **ATTENTE GO** (après origin) |
| Langage IA 100 % | **NON** — matrix + units avancés |
| Thinking UI ≡ hook | **NOT_PROVEN_BY_ARCHITECTURE** |
| `swtpm` Cellar | **relancé brew** (libtpms OK) |
| Tunnel inbound Mac | **ouvert** |
| Tip×5 / PBFT Mac | **FAIL** tant que fork local |
| Multi-transport / overlay | **spec + doctor** ; overlay non déployé |

**CERTIFIED_100=false**
