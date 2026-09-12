# CERTIFICATION_MATRIX_ARTCB — registre maître (2026-09-12T20:10:00Z)

**Règle R330 :** un nouveau chantier **s’ajoute** ; il ne remplace jamais un FAIL/GAP/NOT_PROVEN historique.  
**PASS = PASS sur SHA X, conditions Y, artefacts Z** — jamais « pour toujours ».  
**CERTIFIED_100 = false** tant que les branches critiques ci-dessous ne sont pas toutes `PASS_LIVE` sur le même `origin/main`.

Issues GitHub (état API 2026-09-12) : **#77 OPEN** (R273) · **#86 OPEN** (R328/R329/R330).

| ID | Domaine | Dernier état | Correction code | Déployé SHA | Preuve attendue | Code | Test | Live | Notes |
|----|---------|--------------|-----------------|-------------|-----------------|------|------|------|-------|
| R273/#77 | NodeID↔clé / NEW-VIEW / N04 | OPEN / FAIL partiel | partiel historique | rejouer sur SHA courant | 409 binding, Q VC, adversarial | ? | ? | NOT_PROVEN_current_SHA | Ne pas fermer via R328 |
| R328/#86 A–B | Construct + import public tip | PASS_LIVE | `7069405`+ | `0e177b6`/`ed9259f` | tip public vs private | PASS | PASS | PASS | not_extending fermé sur chemin mesuré |
| R328/#86 C | Auto VIEW-CHANGE | NOT_PROVEN | watchdog présent | — | timeout→NV→PREPARE→COMMIT | PARTIAL | — | NOT_PROVEN | Hypothèse b souvent |
| R328/#86 D–E | Tip×4 + métriques split | PASS_LIVE | split_v1 | `ed9259f` | status×4 | PASS | PASS | PASS | ovh1 suffixe ≠ peers |
| R328/#86 F | Restart/catch-up live | NOT_PROVEN | restart unitaire PASS | — | restart process seed | PASS_unit | PASS | NOT_PROVEN | SSH :22 timeout |
| R329 | Audit 4 couches vocabulaire | PASS_AUDIT | docs+tests | `ed9259f` | matrix+isolation | PASS | PASS | PARTIAL | ORG≠visibility chaîne |
| R330-A | ORG body multi-node | NOT_PROVEN | — | — | export/import hash | — | — | OPEN | authorized≠copied |
| R330-B | GROUP isolation distribuée | PARTIAL | tests locaux | — | A≠B live | PASS_local | PASS | OPEN | |
| R330-C | PRIVATE ACL exhaustive | PARTIAL | e2e216… | — | 403+no side-effect | PARTIAL | PARTIAL | OPEN | |
| R330-D | Pollution croisée ΔPUBLIC | PARTIAL | test_r329 | — | 10k private → tip stable | PASS_local | PASS | OPEN | |
| R330-E | Tous appels `height()` | IN_PROGRESS | tip_attest+client-req | R330 | audit json | — | — | — | voir logs/R330 |
| R330-F | Auto VC live | = R328 C | — | — | — | — | — | NOT_PROVEN | parallèle |
| PUBLIC consensus tip | — | PASS_LIVE 1142+ | R328 | live | tip égal ×4 | PASS | PASS | PASS | |
| ORG domain | — | CODE+local | domains/anchor | — | réplication body | PASS | PARTIAL | NOT_PROVEN | |
| GROUP | — | private book | R328 map | — | 3ᵉ ledger N/A | PASS | PARTIAL | NOT_PROVEN | |
| PRIVATE | — | never_p2p matrix | — | — | — | PASS | PARTIAL | PARTIAL | |
| PUBLIC↔ORG anchor | — | PASS_local | anchor.py | — | commitment sans body | PASS | PASS | OPEN_live_create | |
| TPM/hardware | — | NOT_PROVEN/PARTIAL | R281–284 | — | quote | — | — | PARTIAL | profil |
| CERTIFIED_100 | — | **FALSE** | — | — | tous PASS_LIVE critiques | — | — | FALSE | |

## R331 append (2026-09-12T20:55:00Z) — exécution ouverte, pas liste d’attente

| ID | Domaine | Dernier état | Correction code | Déployé SHA | Preuve attendue | Code | Test | Live | Notes |
|----|---------|--------------|-----------------|-------------|-----------------|------|------|------|-------|
| R331/#77 | audit-sign HTTPS forge | IN_PROGRESS | `POST /pbft/audit-sign` | pending push | A3/A7 409 binding sans SSH | PASS | PASS | pending_deploy | SSH :22 filtré LAN |
| R331/#86 C | auto VC reachable | PASS_LIVE partiel | `next_reachable_view` | pending | VC→NV skip Mac | PASS | PASS | PASS view 20→21 | Mac reste membership |
| R331/#86 F | Mac restart live | IN_PROGRESS | kickstart+wait health | local | public tip preserved | — | — | remeasure | |
| R331 P2P tip | public_sync_cursor | CODE+TEST | `sync.py` | pending | RISK_CONSENSUS→PASS | PASS | PASS | pending_deploy | private suffix ignoré |
| R331 R330-D | pollution live | PASS_LIVE | — | `c4ca2ed` tip 1147 | private≠public tip | — | PASS | PASS | logs/R331 |
| R331 R330-A | ORG body multi-nœud | OPEN ACL | probe export | — | session controller | PASS_unit | PASS | NOT_PROVEN_acl | |

~~Ne pas s’arrêter pour lister l’ouvert~~ — exécuter, pousser, follow-main, rejouer live277.

## Méthode obligatoire (chaque tour)

1. Mise à jour `origin/main` + SHA health ×4  
2. Relire cette matrice (ne pas oublier #77 / #86)  
3. Nouveau problème **ajoute** une ligne  
4. Rejouer les PASS sensibles après changement ChainManager/PBFT  
5. Séparer `PASS_CODE` / `PASS_TEST` / `PASS_LIVE` / `FAIL` / `GAP` / `NOT_PROVEN`  
6. Ne jamais clôturer #86/#77 sans preuves A–F / critères #77

## Artefacts liés

- `logs/R328/measurement.json` · `logs/R329/measurement.json` · `logs/R330/`  
- `rapports/328_*` · `329_*` · `330_*`

## R331b live measure (2026-09-12T21:35:00Z) — SHA `6627d05` → push suivant

| ID | Live | Notes |
|----|------|-------|
| #77 A3/A7 | **PASS_LIVE** | 409 `invalid_replica_key_binding` ×3 via HTTPS audit-sign |
| #77 NV Q | **PASS_LIVE** | nv0..nv_same + combo PASS; `new_view_live_pass=true` |
| #77 N04 50% | FAIL | SSH netem unreachable — not recast PASS |
| #86 auto VC | **PASS_LIVE** | view→22 reachable; Mac restart live PASS public 716 preserved |
| R330-D pollution | **PASS_LIVE** | tip public 1149×4 |
| R330-A ORG body | NOT_PROVEN_acl | export 403 controller_mismatch |
| P2P tip RISK | fixed code | height_audit risk_count→0 attendu après push |
| CERTIFIED_100 | **false** | N04/TPM/C04/ORG body ouverts |

Artefacts: `logs/277_issue77_20260912T212653Z.json`, `logs/R331/measurement.json`.

## R332 append (2026-09-12T22:50:00Z) — langage IA + ingest sélectif

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| R332 ingest | répété vs nouveau | POLICY | full bootstrap + memo `new_only` ; script `artcb_ingest_new_only.py` |
| R332 langage | probe/universal/agent_ab/anchor | PASS | tip 1153×4 ; `logs/332_langage_ia_matrix_latest.json` |
| R332 C2-D WAN | resolve ×5 | PASS | `c2d_multihote_pass=true` |
| R332 C2-D fanout | write n2–n4 | OPEN | 401 token invalide Doppler nœud |
| R332 Rule Telemetry | compteurs règles | NOT_STARTED | design ChatGPT — pas moteur |
| CERTIFIED_100 | — | **false** | langage_ia_final=false |

