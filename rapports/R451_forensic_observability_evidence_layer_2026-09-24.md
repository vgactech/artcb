# R451 — FORENSIC-01 : Forensic Observability & Evidence Layer ARTCB

**Date :** 2026-09-24T00:00:00Z  
**SHA avant :** `8423573` (HEAD début session)  
**SHA R451 :** `8ed880b`  
**CERTIFIED_100=false**

---

## 1. Résumé exécutif

| Chantier | État | Tests |
|----------|------|-------|
| `src/artcb/trace/forensic.py` — ForensicEvent + ForensicLedger | ✅ COMMITTÉ | — |
| `src/artcb/reasoning/pipeline.py` — intégration forensic G4 | ✅ COMMITTÉ | — |
| `src/artcb/identity/biometric_onchain.py` — forensic enroll/check | ✅ COMMITTÉ | — |
| `tests/test_r451_forensic_event_ledger.py` — 30 tests F01→F30 | ✅ PASS | 30/30 |
| Non-régression R431→R451 | ✅ PASS | 234/234 |
| Gate DO-178C | ✅ PASS | 124/124 |
| Auto-bump modules | ✅ | 3 modules |

---

## 2. Décision architecturale — FAR/FRR non bloquant

Formalisée par l'utilisateur (session R451) :

> **FAR/FRR/PAD réels ne sont pas une condition bloquante aujourd'hui. Ils deviennent une métrique expérimentale à collecter automatiquement dès que des utilisateurs réels utilisent ARTCB, avec une instrumentation forensic complète déjà présente.**

La règle figée :

> **Ne pas bloquer ARTCB sur FAR/FRR aujourd'hui, mais rendre impossible la perte des données techniques nécessaires à leur calcul futur.**

---

## 3. Architecture FORENSIC-01

### AVANT (HEAD 8423573)

```
biometric_onchain.py — trace R386 :
    emit(None, {"kind": "biometric_enroll", ...})  ← pas de hash-chain, pas de corrélation

pipeline.py — aucune trace forensic
wallet_device_binding.py — hash-chain LOCAL (purges seulement)
```

### APRÈS (HEAD 8ed880b)

```
src/artcb/trace/forensic.py    ← NOUVEAU (455 lignes)
    ForensicEventType           — 50 types couvrant 9 couches ARTCB
    AttemptOutcome              — 11 outcomes distincts (SUCCESS/REJECTED/STORE_UNAVAILABLE/…)
    EvaluationContext           — 11 contextes (ENROLLMENT/AUTH/SYBIL_CHECK/…)
    ForensicEvent               — dataclass frozen, hash-chain, invariants
    ForensicLedger              — JSONL append-only, verify_chain(), Merkle root
    emit_forensic()             — helper fail-open (jamais bloquant)
```

### Pipeline forensic complet G4 (R451)

```
text
  ↓
[IR_ENCODE_OK / IR_ENCODE_FAIL]            ← correlation_id propagé
  ↓
[CANONICAL_OK / CANONICAL_FAIL]            ← reasoning_id dans state_after
  ↓
[KNOWLEDGE_CREATE_OK / FAIL]               ← knowledge_id dans subject_ref
  ↓
[USAGE_RECORD_OK / FAIL]                   ← pol_eligible dans state_after
  ↓
[POL_SCORE_OK / FAIL]                      ← pol_score, block_accepted
  ↓
[REASONING_PIPELINE_OK / FAIL]             ← résumé complet tous maillons
```

**6 événements par run() complet** — tous corrélables par `correlation_id`.

---

## 4. Propriétés garanties

| Propriété | Implémentation |
|-----------|----------------|
| INTÉGRITÉ | `hash_prev → event_hash` SHA-256 sur chaque événement |
| CORRÉLATION | `correlation_id + trace_id + session_id` |
| TRAÇABILITÉ | `git_sha, module_version, protocol_version` par événement |
| NON-REPUDIATION | `actor_ref` = identité vérifiée serveur (jamais body client) |
| CONFIDENTIALITÉ | Jamais : clé privée, PIN, template brut, blinding_hex, challenge brut |
| FAIL-OPEN I/O | Exception d'écriture → WARNING log, opération métier non interrompue |
| MERKLE ROOT | `compute_merkle_root()` + `emit_merkle_checkpoint()` ancre périodique |
| CERTIFIED_100 | False — invariant inviolable |
| unique_human_proven | False — invariant inviolable |

---

## 5. Couverture forensic par couche

| Couche | Types d'événements couverts |
|--------|----------------------------|
| Biométrique | BIO_ENROLL_OK/FAIL/BLOCKED, BIO_UNIQUENESS_OK/FAIL, BIO_FUZZY_*, BIO_HAMMING_* |
| Authenticator/WebAuthn | WEBAUTHN_REGISTER_*, WEBAUTHN_AUTH_*, WEBAUTHN_UV_CLAIMED |
| Anti-Sybil | SYBIL_CHECK_OK/BLOCKED/STORE_UNAVAILABLE/EMPTY, HUMAN_ID_*, WALLET_LIMIT_* |
| Wallet/Binding | WALLET_CREATE/LINK/REVOKE/PURGE_OK/FAIL, BINDING_CHECK_* |
| Raisonnement IA | REASONING_PIPELINE_OK/FAIL, IR_ENCODE_*, CANONICAL_*, KNOWLEDGE_*, USAGE_*, POL_*, KW_* |
| Multilingue | LANG_LOOKUP_HIT/MISS, CONCEPT_ID_RESOLVED/DIVERGED |
| Blockchain | BLOCK_ACCEPTED/REJECTED, WORK_RECORD_SEALED/PENDING, CONSENSUS_* |
| Économique | REWARD_ESTIMATED/PENDING/SETTLED/REVOKED, ECONOMIC_EVENT |
| Sécurité | SECURITY_BLOCK, POLICY_BLOCK, RATE_LIMIT, INTERNAL_ERROR |
| Forensic self | FORENSIC_ACCESS, FORENSIC_MERKLE_ROOT |

---

## 6. Segmentation FAR/FRR future

Les données nécessaires au calcul FAR/FRR sont maintenant captées par `EvaluationContext` :

```
ENROLLMENT      ← tentative initiale d'inscription
AUTHENTICATION  ← tentative d'authentification
RECOVERY        ← récupération après changement d'appareil
UNIQUENESS_CHECK← check_uniqueness()
SYBIL_CHECK     ← gate anti-Sybil
```

Et par `AttemptOutcome` :

```
SUCCESS              → genuine accepted
REJECTED             → genuine rejected (FRR) OU impostor rejected (TNR)
SYBIL_BLOCKED        → politique anti-Sybil
STORE_UNAVAILABLE    → 503 (R447 — à distinguer d'un rejet logique)
STORE_EMPTY          → légal — aucune identité enregistrée
STORE_MISSING        → fichier absent — légal
```

Les futurs calculs :
```
FRR = genuine_rejected / genuine_attempts      (segment: ENROLLMENT/AUTHENTICATION)
FAR = impostor_accepted / impostor_attempts    (segment: AUTHENTICATION/UNIQUENESS_CHECK)
```

---

## 7. Tests R451 — 30 PASS

| Groupe | Tests | Résultat |
|--------|-------|----------|
| ForensicEvent (structure, hash, invariants) | F01→F08 | ✅ 8/8 |
| Ledger hash-chain | F09→F15 | ✅ 7/7 |
| Merkle root | F16→F18 | ✅ 3/3 |
| emit_forensic() helper | F19→F22 | ✅ 4/4 |
| Intégration pipeline G4 | F23→F26 | ✅ 4/4 |
| Intégration biométrie | F27→F28 | ✅ 2/2 |
| Types et énumérations | F29→F30 | ✅ 2/2 |
| **TOTAL** | **30** | **✅ 30/30** |

---

## 8. Non-régression finale

```
R431→R451 (11 suites) :  234/234 ✅
Gate DO-178C :           124/124 ✅
Auto-bump :
  biometric_onchain.py   1.0.3 → 1.0.4
  pipeline.py            1.0.1 → 1.0.2
  forensic.py            1.0.0 → 1.0.1
```

---

## 9. Fingerprint L-053 (sur SHA 8ed880b)

```json
{
  "git_sha": "8ed880b5e6d549bb8aecc4265a13fe763908f244",
  "modules": {
    "src/artcb/trace/forensic.py":           "9c71f0dd...",
    "src/artcb/reasoning/pipeline.py":        "1c7da8b8...",
    "src/artcb/identity/biometric_onchain.py":"e5d01fa5...",
    "tests/test_r451_forensic_event_ledger.py":"668883e9..."
  }
}
```

Artefact : `logs/R451_module_fingerprints.json`

---

## 10. Limites honnêtes

| Limite | Statut |
|--------|--------|
| FHE réel `check_uniqueness()` | ❌ NON FAIT — stub Pedersen |
| FAR/FRR sur population réelle | ❌ ATTENTE UTILISATEURS RÉELS |
| Forensic access control (chiffrement at rest) | ❌ NON IMPLÉMENTÉ — pas de chiffrement du JSONL |
| Audit des accès au forensic lui-même | ❌ NON IMPLÉMENTÉ — FORENSIC_ACCESS type présent, pas branché |
| Retention policy automatique | ❌ NON IMPLÉMENTÉ |
| CI GitHub gate | ❌ NON CONFIGURÉ |

---

## 11. Prochains chantiers

| Priorité | Chantier |
|----------|----------|
| P0 | FHE biométrique `check_uniqueness()` — Concrete/OpenFHE |
| P1 | CI GitHub gate DO-178C obligatoire |
| P1 | Chiffrement at rest du forensic_ledger.jsonl |
| P1 | Branchement FORENSIC_ACCESS (audit des consultations du forensic) |
| P1 | Couverture lexicale 14 langues + LANG_COVERAGE métrique |

**CERTIFIED_100=false.**
