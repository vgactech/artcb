# R317 — Autonomie : quarantine + catch-up Mac (sans attendre GO)

**UTC :** 2026-09-11T18:30:00Z  
**CERTIFIED_100 :** `false`  
**Rappel opérateur :** GO général = **100 % autonome** — ne jamais bloquer sur un GO sauf demande explicite « attendre ».

## Exécuté

1. **Quarantine locale** (forensique, pas wipe)  
   `data/quarantine/divergent_book_20260911T181528Z/blocks.jsonl` (10 lignes private Bob/thinking)

2. **Mac vide** → HTTPS P2P sync → **717 blocs publics** importés

3. **Preuve continuité**  
   - Mac block0 = seed `b8a7d5ef…` (**equal**)  
   - Mac tip index **716** hash `f79f6a1a71896e61…` = seed block 716 (**equal**)  
   - `public_blocks_local=717`, height **717**

4. **Au-delà de 716 :** **aucun** bloc seed (× artcb.me) n’a `prev_hash = tip_716`. Indices 717+ absents / livre seed discontinu (health : index gaps ; tip OVH1 ~1336 ≠ chaîne prolongeable depuis 716).  
   → Catch-up Mac **maximal honnête** atteint. Forcer plus = fabriquer une continuité = **interdit**.

5. Nœud Mac **UP** `:8001` SHA `bbd5ce0…`, livre aligné préfixe public canonique.

## Scripts

- `scripts/artcb_r317_mac_catchup_from_seed.py` (import `require_public=False` hors process)
- quarantine déjà en place (R315)

## Parallèle

| Tâche | État |
|-------|------|
| Langage IA probe FR/EN/ES | PASS |
| `voiture/car/coche` | FAIL |
| R253 E2E natif | NOT_PROVEN |
| tip×5 vs tip seed ~1336 | **FAIL** (trou seed, pas fork Mac) |
| swtpm / brew macOS12 | **BLOQUÉ** Homebrew |
| Tunnel inbound | ouvert |

## Verdict

| Avant | Après |
|-------|-------|
| FORK_AT_BLOCK0 private tip 8 | **SAME_CHAIN prefix 0..716** |
| imported=0 | **imported=717** |
| wrong book | quarantine préservée |

**CERTIFIED_100=false** — tip×5 / PBFT Mac / langage final / swtpm toujours non certifiés.
