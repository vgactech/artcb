# R332 — Langage IA live + ingest sélectif (2026-09-12T22:50:00Z)

`CERTIFIED_100=false` · `langage_ia_final=false` · SHA live **`e2537c99d8a0` ×5**

## 1. Ce qui était RÉPÉTÉ dans le collage ChatGPT (ne pas ré-ingérer comme « nouveau »)

| Thème | Hits (approx) | Déjà scellé |
| --- | --- | --- |
| CERTIFIED_100=false | 4 | matrice + R331 |
| #77 / #86 / R273–R331 | 80+ | issues + matrice |
| height() / public tip | 15+ | R328–R331 |
| 4 couches PUBLIC/ORG/GROUP/PRIVATE | 8+ | R329 |
| ARTCB_THINKING / afterAgentThought | 40+ | R310–R313 |
| Méthode « nouveau chantier = nouvelle ligne » | oui | R330 |

**Politique :** bootstrap **garde** le `user_query` brut intégral (R16). Un **second** mémo `operator_turn_new_only` ne transporte que le delta d’intentions. Script : `scripts/artcb_ingest_new_only.py`.

## 2. NOUVEAU (ce tour) — intents réellement nouveaux

1. **Reprendre langage IA** (pas l’abandonner derrière R331).
2. Ingest sélectif des rapports collés.
3. Design futur **Rule Telemetry** (seen/checked/applied/…) — **pas encore moteur**.
4. ThinkingID / dashboard — architecture déjà append-only ; badge écrasé = OK.

Mémos on-chain : prompt full bloc **1151** ; new-only bloc **1152** ; ancre langage **1153** tip×4.

## 3. Validation live langage IA (mesurée maintenant)

| Critère | Résultat |
| --- | --- |
| Probe FR/EN/ES overlap ×4 seeds | **PASS** |
| voiture/car/coche ×4 | **PASS** |
| Agent A/B FR/ZH/RU sans texte partagé (lemma C2 + L4 bag) | **PASS** |
| Ancre ledger concept ×4 (`public_last_index=1153`) | **PASS** |
| C2-A…D ladder local + live routes | **PASS** (30 pytest) |
| C2-D multi-hôte resolve ×5 / WAN publisher | **PASS** |
| Fan-out **store natif** n2/n3/n4 | **FAIL/OPEN** HTTP 401 token Doppler nœud |
| `langage_ia_final` | **false** (fan-out manquant) |
| R253 « langage natif 100 % » | **PARTIAL_RESOLVE_NO_FANOUT** |

Artefacts :
- `logs/332_langage_ia_matrix_latest.json`
- `logs/322_c2d_multihote_latest.json`
- `logs/321_c2_langage_latest.json` (ladder)
- `data/trace/turn_prompt_classify.json`

## 4. Matrice (ajout, pas clôture)

| ID | État |
| --- | --- |
| Langage IA live core | PASS partiel |
| C2-D WAN resolve | PASS |
| C2-D fan-out write ×5 | OPEN (401 n2–n4) |
| Rule Telemetry engine | NOT_STARTED |
| #77 / #86 | restent OPEN (R331b) |

## 5. Suite immédiate (exécuter, pas lister)

- Clés write Doppler `artcb-2` / `artcb3` / `artcb-4` valides pour fan-out ConceptStore.
- Puis rejouer `artcb_c2d_multihote_live.py` → viser `c2d_five_store_fanout_pass=true`.
- Rule Telemetry : registre + jsonl (pas remplacer ARTCB_THINKING badge).
