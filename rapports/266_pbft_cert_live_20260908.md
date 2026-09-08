# 266 — PBFT exclusive + V-01…V-07 live (2026-09-08)

Mesure sur SHA `78cd8d61e08c1dee99d83bf24ae7aba0bdf3f007` = `origin/main` ×4.
Traces `pbft_*` présentes. Wipe = false. Processus restorés. iptables `artcb266` = 0.

## Verdict

`PBFT_LIVE_E2E_PASS` **après retries V-01/V-02**. Le premier `run_live266_pbft_cert.py` a marqué V-01/V-02 FAIL (mémo hors-primary → `client_request_failed` ; python système sans nacl/passphrase). Les retries sur le même SHA ont PASS.

`certified_distributed_mainnet` n’est pas levé ici (gate DV distinct ; `/health` le lisait déjà true via RESULT.json 208).

## V-01…V-07

| ID | Résultat | Preuve |
|---|---|---|
| V-07 | PASS | `78cd8d6…` ×4 |
| V-01 | PASS (retry) | mémo public seq **1094** digest `5688fb3cc37cccce…` cert Q=3 ×4 ; height **1095** tip identique |
| V-02 | PASS (retry) | PRE-PREPARE signés X=`293693fb…` Y=`5cfd14b7…` view 5 seq 1095 ; split 2-2 ; **aucune** double finalité ; height reste 1095 |
| V-03 | PASS | POST cert `ee*32` seq 1094 → HTTP 409 ; digest tenu `5688fb3c…` ×4 |
| V-04 | PASS | `systemctl stop` primary ovh-node-4 ; view **3→4** ; primary ovh-node-1 ; seq 1093 digest `4006c38b…` ×4 ; process relancé |
| V-05 | PASS | partition 2-2 `artcb266` ; left_ok=false right_ok=false ; dual_finality=false ; restore ; height 1094 à ce moment |
| V-06 | PASS | restart ovh-node-4 ; view 4 et height/hash conservés sur ce run |
| DV-02 probe | PASS | 16×4 GET /health 200 ; unauth 405 ; pas de SYN |

JSON bruts : `logs/266_pbft_cert_20260908T155024Z.json` (run auto), `logs/266_v01_retry.json`, `logs/266_v02_retry.json`, `logs/266_v03_retry.json`.

## État live en fin de mesure

- height **1095**
- tip `5688fb3cc37cccce720a40bf1baa6d3da44dd3190a2358c9ee77084dea65c774`
- view **5** primary `ovh-node-2`
- exclusive_public_from_seq **1087**
