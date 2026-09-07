# Rapport 239 — GO-A/C/F/G/H/N + Découvert ARTCB — 897 passed 0 fail

**Date** : 2026-09-07T17:48:45Z  
**Session Bob** : 239  
**SHA main** : `f26c3d6`  
**Commits session** : `85ac33c` → `6f8c098` → `20abf4b` → `a0a87e8` → `f26c3d6`

---

## Résultats tests

| Métrique | Session 235 | Session 239 |
|---|---|---|
| Tests passés | 857 | **897** (+40) |
| Tests skippés | 9 | **8** |
| Tests échoués | 0 | **0** ✅ |
| Durée | 446s | 431s |

---

## GOs implémentés cette session

### GO-N ✅ — Correction 3 mensonges documentés (commit `85ac33c`)
- `src/api/deps.py` : `delta_compression=None` (0.68 était heuristique non mesurée)
- `src/api/p2p_routes.py` : message corrigé — "pull public en clair" (pas "blocs publics chiffrés")
- `CAHIER_DES_CHARGES_ARTCB` : `compression_ratio=null` + note mesure IR réelle (3–28× expansion)

### GO-C ✅ — Merger PR #57 HOST ≠ CONSENSUS (commit `8544224` + `85ac33c`)
- `node_cert.py`, `node_roles.py`, `authz_routes.py`, `test_e2e236` mergés depuis PR #57
- Rôles : HOST_ONLY / REPLICA / CONSENSUS / GOVERNANCE

### GO-A ✅ — Chiffrement KEM au repos (commit `85ac33c`)
- `src/artcb/p2p/node_identity.py` : `kem_secret_key_hex` chiffré AES-256-GCM (HKDF-SHA256)
- Clé dérivée depuis `ARTCB_KEM_STORAGE_KEY` (Doppler) ou machine_id (fallback)
- Migration automatique : fichiers existants en clair → chiffré au premier load
- `_save()` n'écrit **jamais** `kem_secret_key_hex` en clair sur disque
- `ARTCB_KEM_STORAGE_KEY` ajouté dans Doppler dev

### GO-J ✅ (doc) — `ARTCB_NODE_PUBLIC_URL` OVH2/AWS3/OVH4
- `CONFIGURATION_ARTCB` : instructions pour configurer sur chaque nœud distant

### GO-F ✅ — KCG événements CONSULT/USE + UsageID (commit `6f8c098`) — 12 tests
- `src/artcb/kcg/events.py` : `KnowledgeEntry`, `ConsultEvent`, `UseEvent`, `knowledge_id`
- `src/artcb/kcg/store.py` : `KCGStore` (JSONL append-only) + `KCGIndex` (stats mémoire)
- `src/api/kcg_routes.py` : POST /publish /consult /use + GET /knowledge /stats
- Invariant GO-F : `fee_pending=False`, `fee_amount_satoshi=0`

### GO-G ✅ — Reasoning Fee transfert wallet→wallet (commit `20abf4b`) — 13 tests
- `src/artcb/kcg/fee.py` : `KCGFeeEngine`, `KCGLedger`, `FeeResult`
- `BaseAccessFee` au CONSULT + `UsageBonus` proportionnel au delta
- Invariant GO-G : `fee_type='transfer'`, jamais `'mint'`
- Supply conservée : somme balances identique avant/après

### GO-H ✅ — PoUC Challenge/Stake/Escrow (commit `a0a87e8`) — 9 tests
- `src/artcb/kcg/pouc.py` : `PoUCChallenge`, `PoUCStake`, `PoUCEscrow`, `PoUCEngine`
- PASS → stake retourné ; FAIL → pénalité partielle ; TIMEOUT → stake retourné
- Invariant GO-H : `fee_type='transfer_back'` ou `'penalty_partial'`, jamais `'mint'`

### Découvert ARTCB ✅ — Extension GO-G (commit `f26c3d6`) — 14 tests
**Idée propriétaire** : un wallet peut payer même si solde insuffisant
- `src/artcb/kcg/overdraft.py` : `OverdraftLedger`, `OverdraftAccount`
- `balance` peut devenir négatif jusqu'à `limit_overdraft_satoshi`
- Auto-repay automatique à chaque crédit entrant (récompense PoL → rembourse d'abord la dette)
- `ARTCB_OVERDRAFT_DEFAULT_LIMIT_SATOSHI` configurable Doppler
- Invariant : pas de mint — la dette est une obligation, pas une émission

---

## GOs restants

| GO | Statut | Note |
|---|---|---|
| GO-B | ⏳ À faire | Pull P2P chiffré + from_node_id |
| GO-D | ⏳ À faire | Réplication privée auto BODY |
| GO-I | ⏳ À faire | IR binaire natif + zstd |
| GO-E | ⏳ À faire | V-01-B producteur live (fork risk) |

---

## Architecture KCG complète (GO-L = F+G+H)

```
Producteur                    KCGIndex
    │                             │
    ├─ mine_pol_block()           │
    │       ↓                     │
    └─ /kcg/publish  ──────────→ KnowledgeEntry (K_xxx)
                                  │
Consultant                        │
    │                             │
    ├─ /kcg/consult ──────────→ ConsultEvent (C_xxx)
    │   [GO-G] BaseAccessFee      │   fee: transfert → producteur
    │   [Découvert] si 0 balance  │   auto-repay sur prochain crédit
    │                             │
    └─ /kcg/use ──────────────→ UseEvent (U_xxx)
        [GO-G] UsageBonus         │   fee: proportionnel delta_utility
        score_before/after        │   réputation K mise à jour
                                  │
PoUC Engine                       │
    ├─ issue_challenge() ──────→ PoUCChallenge (CH_xxx)
    │   stake en escrow           │
    └─ resolve(score) ─────────→ PASS/FAIL/TIMEOUT
```

---

## Fichiers créés cette session

```
src/artcb/kcg/__init__.py
src/artcb/kcg/events.py
src/artcb/kcg/store.py
src/artcb/kcg/fee.py
src/artcb/kcg/pouc.py
src/artcb/kcg/overdraft.py
src/api/kcg_routes.py
tests/test_e2e239_kcg_events.py        (12 tests)
tests/test_e2e240_kcg_reasoning_fee.py (13 tests)
tests/test_e2e241_pouc_challenge.py    (9 tests)
tests/test_e2e242_overdraft.py         (14 tests)
rapports/239_go_a_c_f_g_h_n_kcg_overdraft_20260907.md
```
