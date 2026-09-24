# R457 — Issue #77 : NodeID ↔ Clé — 9 Scénarios Adversariaux PASS

**Date :** 2026-09-25  
**SHA commit :** `4c744ba`  
**SHA parent (R456) :** `991049c`  
**Fingerprint :** `logs/R457_module_fingerprints.json` (généré sur `4c744ba`)  
**CERTIFIED_100 :** `false`  
**Avancement global estimé :** 62 %

---

## 1. Problème résolu (Issue #77)

L'issue #77 demandait de tester les 9 scénarios adversariaux sur le binding NodeID ↔ clé publique Ed25519/PQC, en s'appuyant sur `src/artcb/consensus/replica_identity.py` (existant depuis R390).

Avant R457, ces scénarios n'avaient **aucun test dédié**. Un attaquant pouvait théoriquement :
- usurper un NodeID officiel avec une autre clé
- réutiliser une clé révoquée ou expirée
- contourner l'obligation PQC (downgrade)

---

## 2. Scénarios adversariaux testés (A1-A9)

| Test | Scénario | Vecteur d'attaque | Résultat attendu | Résultat |
|------|----------|-------------------|-----------------|---------|
| A1 | Key substitution | NodeID valide + mauvaise clé | DENIED | PASS |
| A2 | Clé inconnue | NodeID officiel + clé non enregistrée | DENIED | PASS |
| A3 | Impersonation | Clé de NODE_B présentée comme NODE_A | DENIED | PASS |
| A4 | Clé révoquée | Clé revoked=True présentée | DENIED | PASS |
| A5 | Clé expirée | not_after_epoch=1 (1970) | DENIED | PASS |
| A6 | Activation future | activation_epoch=9999999999 (2286) | DENIED | PASS |
| A7 | PQC downgrade | require_pqc=True, aucune PQC fournie | DENIED | PASS |
| A8 | NodeID non enregistré | NodeID officiel absent du registre test | DENIED ou registry_inactive | PASS |
| A9 | Collision de clé | Même clé revendiquée par NODE_A et NODE_B | Propriété security respectée | PASS |

---

## 3. Tests positifs et utilitaires (B1-B6)

| Test | Description | Résultat |
|------|-------------|---------|
| B1 | Liaison légitime → `ok` | PASS |
| B2 | `install_test_replica_registry()` → isolation correcte | PASS |
| B3 | `clear_test_replica_registry()` → override vidé | PASS |
| B4 | `override_replica_registry()` ctx manager → isolation propre | PASS |
| B5 | `owner_of_ed25519()` → retrouve le bon NodeID | PASS |
| B5b | `owner_of_ed25519()` → None pour clé inconnue | PASS |
| B6 | `public_registry_view()` → pas d'exception, retourne dict | PASS |

---

## 4. Résultats globaux

| Suite | Résultat |
|-------|---------|
| `test_r457_nodeid_key_binding_adversarial.py` (16 tests) | **16/16 PASS** |
| Gate DO-178C (R430) | **124/124 PASS** |
| Non-régression R455-R456 | **172/172 PASS** |

---

## 5. Architecture `replica_identity.py` — résumé

Le module `verify_replica_key_binding()` applique les vérifications dans cet ordre :
1. Clé connue avec mauvais NodeID → `invalid_replica_key_binding`
2. NodeID officiel dans le registre → vérifie existence
3. Si absent et binding enforced → `unregistered_replica_key`
4. Si `revoked=True` → `replica_key_revoked`
5. Si `activation_epoch` dans le futur → `replica_key_not_yet_valid`
6. Si `not_after_epoch` dépassé → `replica_key_expired`
7. Clé Ed25519 ne correspond pas → `invalid_replica_key_binding`
8. `require_pqc=True` et pas de PQC → `replica_pqc_downgrade`
9. Clé PQC présente mais mismatch → `invalid_replica_pqc_binding`

---

## 6. Limites documentées

1. **TPM physique non testé** — `hardware_identity.py` sonde le vrai TPM si disponible. Les tests R457 ne testent que le binding logique clé ↔ NodeID, pas l'attestation TPM matérielle.
2. **Epoch = `time.time()` interne** — impossible de mocquer l'horloge sans patch. Tests A5/A6 utilisent 1970 et 2286 pour garantir le résultat quelle que soit l'horloge.
3. **Collision de clé** — le comportement A9 est déterministe (premier match gagne) mais l'architecture n'a pas de vérification explicite de l'unicité des clés au moment de l'enregistrement.

---

## 7. Prochaines étapes

| R# | Priorité | Description |
|----|----------|-------------|
| CI GitHub | P0 | Gate DO-178C autorité finale (R430 préconisation) |
| R456-integ | P1 | Brancher `capability_token.py` sur les routes API P2P |
| TASK-001 | P1 | FAR/FRR/PAD biométrie vrais capteurs |
| FHE-réel | P2 | Concrete/TFHE réel pour `check_uniqueness()` |

---

*Rapport généré post-exécution — ARTCB protocole R457 — SHA `4c744ba`*
