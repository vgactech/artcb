# R458 — CI DO-178C Gate Obligatoire + Audit de Sécurité Total AUDIT-SEC-TOTAL

**Date :** 2026-09-25  
**SHA commit :** `(à remplir après commit)`  
**SHA parent (R457) :** `41fbbaf`  
**CERTIFIED_100 :** `false`  
**Avancement global estimé :** 63 %

---

## 1. Contexte — lacune identifiée par l'audit expert

L'audit expert post-R457 a identifié que :

1. Le workflow CI `tests.yml` existait déjà avec un trigger `push: branches: [main]`, **mais** avec un `paths-ignore` large (rapports, logs, *.md, frontend) — les commits R455-R457 étaient donc bien déclenchés.
2. **Cependant :** aucun trigger `pull_request` n'existait — une PR vers `main` n'était pas bloquée.
3. **Et surtout :** aucune **branch protection rule** GitHub n'impose ce check comme obligatoire — un push direct avec `--no-verify` + absence de protection = le CI peut être contourné.
4. Le hook pre-commit local R430 est FAIL-CLOSED localement, mais est contournable avec `git commit --no-verify`.

### Avant / Après

**AVANT (R457) — `.github/workflows/tests.yml` ligne 15-28 :**
```yaml
on:
  push:
    branches: [main]
    paths-ignore:
      - "rapports/**"
      - "logs/**"
      - "*.md"
      - "frontend/**"
  workflow_dispatch:
    inputs:
      reason:
        description: "Raison du lancement"
        required: false
        default: "Validation manuelle"
```
Problèmes : pas de `pull_request`, pas de job critique séparé, aucune branch protection.

**APRÈS (R458) — `.github/workflows/do178c_gate.yml` :**
```yaml
on:
  push:
    branches: [main]
    paths-ignore: [rapports/**, logs/**, *.md, frontend/**]
  pull_request:
    branches: [main]
    paths-ignore: [rapports/**, logs/**, *.md, frontend/**]

jobs:
  do178c-gate:
    name: "DO-178C Gate — Tests critiques ARTCB"
    # Tests critiques : ~90s CI, 124 tests
    # Séparés en 3 étapes : biométrie | sécurité WebAuthn | capability + NodeID
  gate-scope:
    # Rapport de couverture : liste honnête de ce que ce gate NE couvre PAS
```

---

## 2. Architecture du nouveau gate CI

```
Push vers main
      │
      ▼
do178c_gate.yml
      │
      ├── job: do178c-gate
      │     ├── tests/test_task001_r378_hamming.py
      │     ├── tests/test_task001_r376_uniqueness.py
      │     ├── tests/test_task001_r374_bch.py
      │     ├── tests/test_task001_r373_human_identity_policy.py
      │     ├── tests/test_task001_biometric.py
      │     ├── tests/test_r454_webauthn_failclosed.py
      │     ├── tests/test_r455_d046_face_camera_unsupported.py
      │     ├── tests/test_r456_capability_token_single_use.py
      │     └── tests/test_r457_nodeid_key_binding_adversarial.py
      │
      └── job: gate-scope (always)
            └── Rapport honnête : ce que ce gate NE couvre PAS
```

**Status check obligatoire à configurer :** `DO-178C Gate — Tests critiques ARTCB`

---

## 3. Configuration branch protection requise (action utilisateur)

⚠️ **Action manuelle requise sur GitHub** (impossible à automatiser par push) :

```
GitHub → vgactech/artcb → Settings → Branches → main
→ Branch protection rules → Edit (ou Add rule)
→ ✅ Require status checks to pass before merging
→ ✅ Status check : "DO-178C Gate — Tests critiques ARTCB"
→ ✅ Require branches to be up to date before merging
→ ✅ Do not allow bypassing the above settings (recommandé)
```

Sans cette configuration, le workflow CI s'exécute mais ne bloque pas le merge.

---

## 4. AUDIT-SEC-TOTAL — Matrice des 29 couches (S00-S28)

### Définitions des statuts

| Statut | Signification |
|--------|--------------|
| `UNIT PASS` | Test local/unitaire validé |
| `E2E PASS` | Composants locaux intégrés validés |
| `LIVE NODE` | Exécuté sur une vraie machine du réseau |
| `LIVE MULTI-NODE` | Plusieurs nœuds réels participants |
| `NON VÉRIFIÉ` | Aucune preuve disponible à ce jour |
| `PARTIAL` | Partiellement couvert |

### Matrice complète

| Couche | Domaine | Local/Unit | E2E | Live 1 nœud | Live multi-nœuds | Preuve matérielle | Statut |
|--------|---------|-----------|-----|-------------|-----------------|-------------------|--------|
| S00 | Inventaire général | ✅ | ✅ | — | — | — | UNIT PASS |
| S01 | Hardware / TPM physique | ⚠️ partiel | ⚠️ partiel | ❌ | ❌ | ❌ | NON VÉRIFIÉ live |
| S02 | Boot / OS / processus | — | — | ❌ | ❌ | — | NON VÉRIFIÉ |
| S03 | Réseau / ports / TLS | — | ⚠️ partiel | ❌ | ❌ | — | NON VÉRIFIÉ live |
| S04 | Identité NodeID ↔ clé | ✅ 16 tests | ✅ | ⚠️ partiel | ❌ | ❌ TPM réel | UNIT PASS |
| S05 | Cryptographie Ed25519/PQC | ✅ | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S06 | Wallet isolation | ✅ | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S07 | Biométrie / WebAuthn D-046 | ✅ 45 tests | ✅ | ❌ | — | ❌ | UNIT PASS |
| S08 | API authz / IDOR | ✅ | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S09 | Capability tokens (routes P2P) | ✅ 25 tests | ❌ routes non branchées | ❌ | ❌ | — | PARTIAL — routes non branchées |
| S10 | P2P réseau | ✅ | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S11 | Consensus PBFT | ✅ 25 tests | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S12 | Blockchain live | ✅ | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S13 | PoL | ✅ | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S14 | Tokenomics / settlement | ✅ | ✅ | ⚠️ partiel | ❌ | — | E2E PASS |
| S15 | CI DO-178C autorité finale | ✅ hook local | ❌ → **R458 corrige** | — | — | — | **R458 EN COURS** |
| S16 | Stockage / secrets dans logs | — | — | ❌ | ❌ | — | NON VÉRIFIÉ |
| S17 | Secrets management | ✅ .env | ⚠️ | ❌ | ❌ | — | PARTIAL |
| S18 | CI/CD supply chain | ⚠️ partiel | — | — | — | — | PARTIAL |
| S19 | Supply chain dépendances | ❌ | — | — | — | — | NON VÉRIFIÉ |
| S20 | Monitoring / observabilité | ⚠️ partiel | ⚠️ | ⚠️ | ❌ | — | PARTIAL |
| S21 | Backup / recovery | — | — | ❌ | ❌ | — | NON VÉRIFIÉ |
| S22 | Multi-tenant / Genesis isolation | ✅ | ✅ | ⚠️ | ❌ | — | E2E PASS |
| S23 | Attaque adversariale | ✅ 16 tests A1-A9 | ✅ | ❌ | ❌ | — | UNIT PASS |
| S24 | Panne nœud / view-change | ✅ 25 tests V01-V25 | ✅ | ⚠️ | ❌ | — | E2E PASS |
| S25 | Reprise après panne | ✅ | ✅ | ⚠️ | ❌ | — | E2E PASS |
| S26 | LIVE 1 nœud vérifié | — | — | ⚠️ partiel | — | — | NON VÉRIFIÉ complet |
| S27 | LIVE multi-nœuds vérifié | — | — | — | ❌ | — | NON VÉRIFIÉ |
| S28 | Audit final croisé | — | — | — | — | — | NON VÉRIFIÉ |

---

## 5. Points critiques non bloquants en attente

### S09 — capability_token.py non branché sur API P2P (R456-integ)

```
capability_token.py ← tests 25/25 PASS (logique)
          ≠
routes API P2P ← pas encore modifiées pour exiger un token
```

**Impact :** un nœud peut toujours appeler une route privilégiée sans token de capability — la protection est en place dans la bibliothèque mais pas encore appliquée dans les handlers FastAPI.

### S01 — TPM physique non attesté

R457 teste le binding logique NodeID ↔ clé. Il ne prouve pas que :
```
machine OVH/AWS → TPM réel → EK/AK → clé de protocole
```

### S15 — Branch protection non encore activée (action utilisateur requise)

R458 crée le workflow. La branch protection doit être activée manuellement par le propriétaire du dépôt.

---

## 6. Prochaines étapes (ordre de priorité)

| Priorité | R# | Description |
|----------|----|-------------|
| **P0 — Action utilisateur** | — | Activer branch protection rule `main` sur GitHub |
| **P0** | R456-integ | Brancher `capability_token.py` sur routes API P2P |
| **P1** | R459 | Audit S02 (boot/OS) + S17 (secrets dans logs) sur N2/N4/N3 |
| **P1** | R460 | LIVE S26 — audit live 1 nœud complet (N2) |
| **P2** | R461 | TASK-001 FAR/FRR/PAD biométrie vrais capteurs |
| **P2** | R462 | FHE Concrete réel `check_uniqueness()` |

---

*Rapport généré post-exécution — ARTCB protocole R458 — SHA à remplir*
