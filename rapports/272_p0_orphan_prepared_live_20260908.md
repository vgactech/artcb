# 272 — P0 orphan lock + prepared-set (live, pas certifié)

SHA moteur déployé et mesuré ×4 :

**`32869961950e5f9ec5b6d1f41652ceb03295cb20`** = `origin/main` du run.

Pas de wipe. Pas de HPC. AWS t3.small. **CERTIFIED_100 = false.** Pas d’overlay R270/R271 comme certification.

## Corrections moteur (ne pas supprimer `equivocation`)

1. **Même vue, digest distinct** → toujours **409 equivocation**.
2. **`enter_view(new_view)`** sur NEW-VIEW : jette `accepted[v:seq]` pour `v < new_view` (PRE-PREPARE non préparé).
3. **Prepared X autoritatif** : `_must_digest(seq)` depuis `must_repropose` **ou** certificat prepared non commité. Propose Y → `must_repropose_prepared`.
4. **`select-prepared` bind** + NEW-VIEW appelle `enter_view`.
5. **`accept_commit`** exige prepared correspondant.

pytest : `tests/test_e2e272_pbft_p0.py` (22 tests PBFT liés verts).

## Live sur ce SHA — P0 prouvé

JSON : `logs/272_p0_20260908T212134Z.json`

| Test | Mesure | Verdict |
|---|---|---|
| 10 rounds sains | **10/10** certifiés, height 1109→1119 | **PASS** |
| Orphelin même vue | propose 200 puis 409 `equivocation` ; VC + heal seq **1119** `f4079eef…` | **PASS** |
| B05 | `select_proof=true`, bind seq 1120 digest `3ced8e3a…`, Y **409 `must_repropose_prepared`**, X client-request 200 | **PASS** |

R271 avait Y **HTTP 200**. Ici Y est **refusé**. C’est la correction B05.

Le runner a ensuite appelé `run_round` (nouveau graph) pendant que X n’était pas commité → N03…X03 de **cette** passe sont **contaminés** par `must_repropose_prepared`. Ce n’est pas un FAIL réseau.

## Finalisation X + replay réseau (même SHA)

`logs/272_finish_prepared.json` : writes **4/4**, height **1121**, digest `3ced8e3a…`.

`logs/272_net_replay.json` ensuite :

| Test | Mesure | Verdict |
|---|---|---|
| Baseline | seq **1121** `0d84f39e…` | **PASS** |
| N03 asym 1→4 | round seq 1122 + heal 1123 ; safety | **PASS** |
| N04 1 % | seq **1124** | **PASS liveness** |
| N04 5 % | 1125 | **PASS** |
| N04 10 % | 1126 | **PASS** |
| N04 20 % | 1127 | **PASS** |
| N04 30 % | 1128 | **PASS** |
| N04 50 % | propose fail, snapshot `safety=false` | **FAIL** |
| N06 / N08 / C03 / A02 / X03 | après le 50 % (equivocation même vue) | **FAIL contaminés** — ne pas les lire comme preuve isolée |

N04 global = **FAIL** (la ligne exige 1–50 %). 1–30 % sont des rounds certifiés réels.

Restore : VC 14→15, seq **1129** `49dd849a…`, height **1130**, `chain_valid` ×4, netem/iptables 0. `logs/272_end_restore.json`.

## Ce qui n’est pas certifié

- 43/43 sur un SHA unique
- C04 milliers
- N04 à 50 % de perte
- N06/N08/C03/A02/X03 **propres** après un 50 % (à rejouer depuis vue saine)
- Production-ready

T-E60 [x] pour le correctif + mesures ci-dessus. **PBFT 100 % = NON.**
