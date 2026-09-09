# 293 — Audit capture : 4 couches (2026-09-09)

Chat visible ≠ fichier VM ≠ ARTCB. `CERTIFIED_100=false`. PR #84 encore draft. Live SHA `05d703022a949a61849516e1c8ed20a4e715d9a7` height **1133**.

## Mesure (cette VM, hashes only)

Live `AR-293-20260909T194104Z` SHA ×4 `05d703022a949a61849516e1c8ed20a4e715d9a7` height **1133** tip `cc0bf8a1053c7ae75c3c00b0a4ebf72da311efbf1f13e3164a95f159fc7d71b3`.

| Couche | Observation | Verdict |
|---|---|---|
| 1 modèle / ingest hook | `ARTCB_INGEST_THINKING_FILE` unset | **NOT_PROVEN** |
| 2 interface Cursor | transcript MCP 30650605 B sha256 `bacd8b4f43b786a01f46b9e7fa7429808d807a7cb1fb402e57fea96e93deb70b` ; 14248 messages ; **2500** champs `thinking` (assistant) 1807778 chars | **OBSERVED_VIA_MCP** — ≠ ingest hook |
| 3 VM | `AGENT_TRANSCRIPTS` set, répertoire **absent** ; socket `/run/cursor/api.sock` existe | **PARTIAL** |
| 4 ARTCB | `posted_to_artcb=false` (secret-like dans le transcript) | **NOT_STORED** ; `thinking_recorded=false` |

`thinking_recorded` reste false : pas de store privé + égalité SHA256 raw/payload/received/stored sur ARTCB.

Le transcript MCP n’est **pas** commité. Corps thinking / clés jamais imprimés.
