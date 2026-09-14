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

## R333 append (2026-09-12T23:50:00Z) — ReasoningID + parallèle

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| R333/R-01 | CanonicalReasoning / ReasoningID | PASS_PARTIAL | T1/T3/T4 ; texte≠identité ; ancre 1158 |
| R333 #77 | rejoué SHA `598e43a` | PASS partiel | N04/TPM/C04 ouverts |
| R333 #86 | tip/VC/restart/pollution | PASS | ORG body ACL ouvert |
| R333 langage | matrix + C2-D | PASS partiel | fan-out 401 |
| CERTIFIED_100 | — | **false** | — |


## R334b append (2026-09-13T17:41:26Z) — keys/SSH/wake + fanout PASS_LIVE

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| R334-C fanout | replica peer-ingest ×3 | **PASS_LIVE** | n2/n3/n4 HTTP 200; `peers_ok=3`; SHA `25faa42102a4` |
| R334 C2-D | `c2d_five_store_fanout_pass` | **PASS_LIVE** | via `/concepts/fanout` not per-node Bearer |
| R334-A ReasoningID v2 | anchor | **PASS_LIVE** | block 1167 |
| R334-D ORG ACL export | closed path | **PASS_LIVE** | 403 `controller_mismatch` / 401 no auth |
| Doppler n2/n3/n4 | `ARTCB_API_KEY` | **PROVISIONED** | was EMPTY; set in `artcb-2`/`artcb3`/`artcb-4` prd+dev; VM reload needs process restart (SSH:22 CLOSED) |
| Direct publish n2–n4 | Bearer env key | still **401** until VM `doppler run` reload | expected; not a protocol FAIL for C2-D anymore |
| SSH :22 LAN | artcb IPs + github | **CLOSED** | HTTPS :443 OPEN — GitHub/Doppler/Cursor/Chrome use :443 |
| Mac wake | en0 IP | **CHANGED** | was `10.234.49.2` → now `10.5.21.208`; local health `127.0.0.1:8001` OK |
| swtpm brew macOS12 | install | **FAIL** | gobject-introspection pip break; guest swtpm ≠ NitroTPM |
| CERTIFIED_100 | — | **false** | N04/TPM/C04/hole716 still open |

Progress estimate (matrix-weighted, honest): **~58%** of declared P0 rows live-pass or pass-partial; **CERTIFIED_100 = 0%**.

## R336 append (2026-09-13T18:39:35Z) — HTTPS restart + key honesty

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| Ports LAN | :22 vs :443 | mesuré | OPEN only 80/443 ×4 ; pas de port admin alternatif |
| Doppler n2–n4 | ARTCB_API_KEY | provisionné + prd=dev | VM inject encore NOT_PROVEN (401 direct) |
| R336 ops | peer-restart HTTPS | CODE | déployer puis mesurer fanout-restart |
| Révocation anciennes clés | — | **BLOQUÉ** | attendre match fingerprint post-restart |
| CERTIFIED_100 | — | **false** | — |

### R336b live (2026-09-13T18:47:23Z)
- fingerprint match ×3 + **direct publish OK** n2/n3/n4 (clés Doppler `dev` synchronisées)
- peer-restart HTTPS fonctionne (cercle :22 cassé pour reload)
- révocation anciennes : N/A (projets étaient vides) ; `artcb-blockchain` intact

## R337 append (2026-09-13T19:05:16Z) — Rule Telemetry + Anti-Sybil baseline

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| R337 telemetry | registry+usage+badge | **CODE+local tests** | ~~NOT_STARTED~~ → moteur v1 ; thinking≠applied_confirmed |
| R337 Anti-Sybil | campagne statistique | **BASELINE** | sample_count=25 <50 ; campaign_certified=false |
| R337 C2-D/langage | remesure | PASS | fanout+matrix |
| R337 #77 N04 | chaos SSH | not_proven | :22 CLOSED |
| CERTIFIED_100 | — | **false** | — |

## R338 append (2026-09-13T20:01:44Z) — capability-first C04 + #87

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| R338 C04 Mac | capability discovery | **UNSUPPORTED_HARDWARE** | MacBookAir7,1 ; pas de fake TPM |
| R338 policy | CAPABILITY_FIRST | CODE | stop before workaround |
| #87 | master execution | OPEN | GitHub issue open |
| #86 remesure | tip/VC/pollution | PASS partiel | org_body_multinode NOT_PROVEN_acl |
| #77 N04 | SSH netem | not_proven | :22 CLOSED |
| CERTIFIED_100 | — | **false** | — |

## R339 append (2026-09-13T20:55:00Z) — Hardware Identity v2 + remesures

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| R339 Mac inventory | H0–H4 enrollment | **H1** | MacBookAir7,1 ; C04 UNSUPPORTED_HARDWARE |
| R339 NodeKey | Ed25519 challenge | CODE+local | ≠ attestation matérielle |
| R339 public tip | ×4 HTTPS | PASS equal | index 1177 ; SHA `9724811…` |
| R339 C2-D | fanout | PASS | remesure |
| R339 #86 org body | ACL multi-node | NOT_PROVEN_acl_session | tips_equal / auto_vc PASS partiel |
| R339 Anti-Sybil | sample | BASELINE | sample_count=45 <50 ; not certified |
| #77 N04 | SSH | not_proven | :22 CLOSED |
| CERTIFIED_100 | — | **false** | — |

## R340 append (2026-09-14T07:55:00Z) — corpus map + measure validity

| ID | Domaine | Live | Notes |
|----|---------|------|-------|
| R340 labels | registry vs corpus | CODE | registered_rules=18 (v4) ≠ corpus ; markers_sum≈174 |
| R340 sync | live-node R339/R340 | PASS | gap R338-only fermé |
| R340 DNS poll | MATCH0 | **INVALID_NO_SAMPLE** | ne pas compter |
| R340 SHA live | `/health` ×4 | **d4afd60… = origin/main** | dns_fix |
| CERTIFIED_100 | — | **false** | cartographie PARTIAL ; tokenomics/consensus encore hors registry |
