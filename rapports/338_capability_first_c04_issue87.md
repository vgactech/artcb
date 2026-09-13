# R338 — Capability-first C04 + reprise #87 (2026-09-13T20:01:44Z)

## Verdict

`CERTIFIED_100=false`

### Mac C04 (capability discovery)

| Champ | Valeur |
|-------|--------|
| model | `MacBookAir7,1` |
| arch | `x86_64` |
| TPM_ROOT_OF_TRUST | `NOT_AVAILABLE_ON_THIS_MAC` |
| C04_verdict | **`UNSUPPORTED_HARDWARE`** |
| software_fallback | AVAILABLE_BUT_NOT_EQUIVALENT |
| security_equivalence | **false** |

**Ne plus forcer C04 sur ce Mac.** Utiliser une machine compatible (Apple Silicon / T2 / NitroTPM) pour C04 PASS.

Méthode figée : `CAPABILITY_DISCOVERY_FIRST` — `src/artcb/platform/capability_discovery.py`.

### Issue #87

Confirmée **open** sur GitHub : *MASTER EXECUTION*. Ordre respecté : #86 puis #77 puis suite. Pas de wipe / pas de NOT_PROVEN→PASS.

### #86 remesure (R331 script, SHA live `cbd114d`)

| Critère | Résultat |
|---------|----------|
| pollution private ≠ public tip | `True` |
| tips égaux après | `True` |
| auto VC | `True` |
| Mac restart | `True` |
| ORG body multi-node | `NOT_PROVEN_acl_session` |
| CERTIFIED_100 | false |

Public tip **1173** ×4 seeds (`ca9a38df…`). Suffixe privé ovh1 ≠ peers (attendu split).

### Toujours OPEN (non effacé)

N04 (SSH:22), C04 Mac=UNSUPPORTED, TPM seeds partiel, #86 multi-controller ORG, Anti-Sybil sample&lt;50, Genesis réplication body, PoUC/KCG, V-01…V-07.

CERTIFIED_100=false
