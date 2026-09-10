# R310 — Thinking → fichier ; tour → public/org/group/private ; CI 7 FAIL

**UTC :** 2026-09-10T19:35:00Z  
**CERTIFIED_100 :** `false`

## Où passent les thinking du chat ?

1. **CoT privé** du modèle (backend Cursor) : **pas** sur le disque Mac, **pas** récupérable à 100 %.
2. **Thinking surfacé** (hook `afterAgentThought`) :
   - `data/trace/agent_thoughts.jsonl`
   - **`data/trace/thinking/<ts_ns>.md` + `latest.md`** (nouveau, toujours)
3. Si `ARTCB_INGEST_THINKING=1` + clé API : mémo chaîne **`visibility=private`** + notif.
4. Notification : `data/trace/LAST_ARTCB_SEND.md` + `artcb_send_notifications.jsonl`.

## Fin de tour automatique (bundle)

`scripts/artcb_turn_bundle_ingest.py` :

| Scope | Contenu |
|-------|---------|
| public | prompt tour (`/ai/memo`) |
| organization | git status + diffstat (`/ai/ingest-batch`) |
| group | pointeur CI |
| private | thinking surfacé fichier |

Mesure live ce tour : org **1145**, group **1146**, private **1147**, thinking hook **1148**.

## CI 7 FAIL — correctifs (audit opérateur retenu)

| FAIL | Correctif |
|------|-----------|
| Auth 503 | Pas de skip ; `create_app()` frais + env ; **eager `app=create_app()` désactivé sous pytest** |
| Expired key | Exige 401 |
| P2P chain | mock `blocks_path` writable `/tmp/.../chain/blocks.jsonl` |
| PBFT primary | déjà N=5 `primary_of(4)=mac` |
| independent_safety | déjà Mac dans snapshot |
| TPM | `device_kind=HARDWARE_TPM` + `BARE_METAL_PROVEN` |
| Symbols | contrat mint_original |

Local : **7 passed**.

## Ce qui reste à toi

1. Exporter `ARTCB_INGEST_THINKING=1` dans l’env agent/launchd pour auto-mémo thinking.
2. Lancer `PYTHONPATH=src python3 scripts/artcb_turn_bundle_ingest.py` en fin de tour (à brancher hook stop si dispo).
3. SSH Mac→IPv4 / tunnel Mac (inchangé).
4. Ne pas lever `CERTIFIED_100`.
