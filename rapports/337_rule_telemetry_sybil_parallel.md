# R337 — Rule Telemetry + Anti-Sybil + parallèles (2026-09-13T19:05:16Z)

## Verdict

`CERTIFIED_100=false`

### Avancement honnête (chantiers « déjà dus »)

| Chantier | Avant ce tour | Maintenant | % panier |
|----------|---------------|------------|----------|
| Rule Telemetry (R332 NOT_STARTED) | 0 % | **moteur v1** registry+usage+badge+tests | **~25 %** (design→code; pas encore efficacité/conflicts engine complet) |
| Anti-Sybil calibrage statistique (076) | moteur seul | baseline live `sample_count=25` <50 | **~15 %** (campagne **NON CERTIFIÉE**) |
| R334 baseline | PASS | inchangé (référence) | **~100 % du panier R334** |
| C2-D / langage IA | PASS partiel | remesure **PASS** fanout+matrix | **~80 %** |
| #77 N04 | FAIL/OPEN | **not_proven** (SSH:22 CLOSED) | **~60 %** (#77 hors N04) |
| #77 TPM/C04 | NOT_PROVEN | inchangé | **~10 %** |
| #86 multi-controller ORG | OPEN | non démarré ce tour | **~40 %** (#86 hors multi-ctrl) |
| **Global CERTIFIED_100** | false | **false = 0 %** | — |

**Global P0 déclaré (pondéré) : ~55–62 %** — telemetry amorcée, sybil pas calibré, N04/TPM/ORG multi-ctrl ouverts.

## Rule Telemetry livré (sans fausse preuve)

- `rules/rule_registry.json` (versionné)
- `src/artcb/rules/telemetry.py` — compteurs seen/checked/applied/applied_confirmed/violated/corrected/not_proven
- `applied_confirmed` **refuse** thinking-only / claim-only
- priorité : criticité > fréquence (testé)
- CLI `scripts/artcb_rule_telemetry.py`
- badge header dans hook `after_agent_thought.py` (display ≠ source de vérité)
- usage local : `data/trace/rule_usage.jsonl` (gitignored)

## Anti-Sybil

Live `GET /anti-sybil/metrics` : sample_count **25**, suggested_limit_s=1, `quantity_gate_50=false`, `campaign_certified=false`.
Artefact : `logs/R337/anti_sybil_baseline.json`.

## Parallèle remesure

- C2-D : `c2d_five_store_fanout_pass=true`
- Langage matrix : ok/verdict PASS multi-hôte
- #77 live script : non exécuté (pas de `timeout` macOS) — N04 reste SSH-blocked

CERTIFIED_100=false
