# R346 — Live proofs (R344 ingest + R345 matrix)

**UTC:** 2026-09-14T17:40:00Z  
**main:** `11bb42c…` ×4 seeds  
**CERTIFIED_100:** false · **UNIQUE_HUMAN:** false

## Wallet test autorisé

- name `vgactech` · address `artcb1ku7fmezezn2rwpl4dxuzas8cnffu3wypyn6ewn`
- seed **uniquement** `/tmp/artcb_r346_test_wallet.env` mode 0600 — **jamais** git / mémo / chat re-affiché
- Session seed+challenge : **HTTP 200** live

Ce wallet **aurait dû être bloqué** sous une vraie HumanIdentity ; il prouve `face_camera` sans `unique_human_proven`.

## R344 — 5 preuves

| Preuve | Résultat |
|---|---|
| Payload 13660 + sha `dc014df3…` | **MATCH** dans `graph.source_text` (`ai_memo_df04a126781d`) |
| Ingest HTTP 200 | **OK** (bootstrap) |
| GET `/ai/memo/1191` | **404** — index non lisible tel quel |
| Contenu PHASE 12 / AUDIT | **présent** dans le graphe apex |
| Réplica n2–n4 `/graph/…` | **404** — distribution graphe **NOT_PROVEN** |

**Verdict R344 contenu : PARTIAL** (apex OK ; index API + peers incomplets).

## R345 — matrice live

### Avant push (`e302532`)

- Create classique → toujours `device_wallet_limit` / `cursor-cloud-agent` / FP serveur `a6fce8a864ecee5c…`
- `X-ARTCB-Device-Id` **ignoré**

### Après push (`11bb42c` ×4)

| Test | Résultat |
|---|---|
| Device A 1er wallet | **200** |
| Device A 2e wallet | **409** `binding_scope=client` |
| Device B autre id | **200** |
| Password login `vgactech` | **401** (bio vault) |
| `unique_human_proven` | **false** |
| Seed session | **200** |

**R345 device-binding client : LIVE PASS**  
**HumanIdentity / UNIQUE_HUMAN : NON**

Artefacts : `logs/R346/live_matrix_pre_r345.json`, `live_matrix_post_r345.json`, `r344_ingest_verify.json`
