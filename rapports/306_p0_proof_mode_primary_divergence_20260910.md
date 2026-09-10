# 306 — Mode preuve P0 (pas de certification)

**2026-09-10T15:20:00Z.** `CERTIFIED_100=false`. Jamais wipe / genesis / rescue. Ingest ce tour : HTTP **409** `equivocation`, `ingest_skipped=true`, prompt **pas** on-chain. `includes_thinking=false`.

## Accord avec l’audit opérateur

La synthèse (identité N=5 ≠ participation ≠ convergence ≠ certification ; couches SHA ; 409 ≠ écriture ; primary stocké vs calculé ; priorités M/N/L ; tokenomics/CI/crypto non certifiables trop tôt) est **retenue**. Pas de lift de `CERTIFIED_100`. Pas de nouvelles features — **mesure P0**.

## Mesures live (ce tour)

`origin/main` / HEAD : `404b1766a12b73a50126a356524c7d8906d53d6c`.

| P0 | Verdict | Preuve |
|----|---------|--------|
| 1 SHA ×5 | **PARTIAL** | OVH1/2/4 + Mac = `404b176…` ; **AWS3 encore `852f0e2…`** (lag follow-main ; SSH 22 refusé depuis ce LAN) |
| 2 Membership N=5 | **PASS_IDENTITY** | `/pbft/view` n=5 + Mac dans `replicas` ×5 — **pas** PREPARE |
| 3 Primary calculé | **FAIL_DIVERGENCE** | view 15 : `primary_of(15)=ovh-node-1` ; **stored=`ovh-node-4`** ×4 seeds (résidu N=4 : `15%4=3`). Mac view 0 match calc |
| 4 PREPARE/COMMIT | **FAIL_OR_BLOCKED** | Propose → calc primary : HTTP **409** `equivocation` ; → stored primary : HTTP **409** `not_primary`. Pas de pre-prepare. Mac hors fan-out |
| 5 Quorum Q=3 | **NOT_REACHED** | Bloqué par (3)+(4) |
| 6 Même tip | **PASS_SEEDS_ONLY** | Seeds height **1133** tip `cc0bf8a1…` ×4 ; Mac height **6** tip `01a5f743…` |
| 7–10 Chaos L/M/N | **NOT_RUN** | SSH `:22` Connection refused ×4 |

Livre inchangé après le probe propose (`book_unchanged=true`).

Crypto observée `/health.pqc.algorithm` : **ML-DSA-65** sur les nœuds joignables (≠ preuve que tout message PBFT est signé ML-DSA).

GitHub CI sur `404b176` : `state=pending`, `total_count=0`, check-runs **0** — **pas** CI verte sur ce HEAD.

## Ce que ça démontre (et pas)

**Oui :**
- Identité membership N=5 annoncée partout (JSON).
- Divergence d’autorité primary **opérationnelle** : le chemin propose utilise `primary_of` (refuse ovh-4 = `not_primary`) tout en gardant un primary stocké N=4-era ; propose vers ovh-1 = `equivocation` (état orphelin / anti-double).
- Seeds convergent encore sur le tip 1133.
- 409 propose ≠ écriture chaîne.

**Non :**
- Mac dans un quorum PREPARE/COMMIT.
- SHA unique ×5 (AWS3 lag).
- Primary cohérent membership/view/protocole.
- Chaos L / M / N live.
- `CERTIFIED_100`.

## Artefacts

- `scripts/run_live306_p0_proof_matrix.py`
- `logs/306_p0_proof_matrix.json` (+ stamp)
- `logs/306_p0_prepare_commit_probe.json`
- `logs/306_ssh_reachability.json`
- `tests/test_e2e306_p0_proof_matrix.py` (5 passed avec 303)

## Suite P0 (bloquants mesurés)

1. Débloquer SSH ou follow-main hors LAN filtré → AWS3 = `origin/main`.
2. Réaligner primary stocké avec `primary_of` (VIEW-CHANGE / NEW-VIEW mesuré, processus UP) **sans wipe**.
3. Tunnel public Mac mesuré (`ARTCB_MAC_TUNNEL_HEALTH_HTTP`) avant de compter le Mac dans le fan-out PREPARE.
4. Alors seulement : PREPARE → COMMIT → Q=3 → même tip ×5 ; puis L/M/N.
