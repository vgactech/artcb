# R456 — Issue #90 : Capability Tokens à Usage Unique — Bypasses Internes FAIL-CLOSED

**Date :** 2026-09-25  
**SHA commit :** `be6e952`  
**SHA parent (R455) :** `15489c1`  
**Fingerprint :** `logs/R456_module_fingerprints.json` (généré sur `be6e952`)  
**CERTIFIED_100 :** `false`  
**Avancement global estimé :** 60 %

---

## 1. Problème résolu (Issue #90)

Avant R456, les rôles/certificats de nœuds accordaient des capabilities de façon **permanente et répétée** sans mécanisme de comptage ni d'audit trail. Un nœud malveillant pouvait :

- réutiliser la même autorisation indéfiniment pour déclencher des opérations privilégiées (PRODUCE, VALIDATE, CHANGE_GOVERNANCE…)
- ne laisser **aucune trace** de chaque utilisation
- bypasser la politique de séparation par nonce

---

## 2. Solution — `capability_token.py`

Nouveau module : [`src/artcb/authz/capability_token.py`](src/artcb/authz/capability_token.py)

### Architecture

```
NodeCert (permanent, rôle)
        │
        ▼ issue_token()
CapabilityToken (état = PENDING)
        │
        ▼ store.redeem()
 ┌──────────────────────────────┐
 │ Vérification 0 : unknown     │ → DENIED:unknown_token
 │ Vérification 1 : non PENDING │ → DENIED:already_consumed
 │ Vérification 2 : expiré      │ → DENIED:token_expired
 │ Vérification 3 : capability  │ → DENIED:capability_mismatch
 │ Vérification 4 : node_id     │ → DENIED:node_mismatch
 │ Vérification 5 : domain_id   │ → DENIED:domain_mismatch
 │ ✅ Toutes OK                 │ → CONSUMED (irréversible)
 └──────────────────────────────┘
        │
        ▼ (toujours)
    AuditEntry enregistrée (succès ET échec)
```

### Propriétés de sécurité

| Propriété | Valeur |
|-----------|--------|
| Réutilisation | ❌ impossible — état CONSUMED irréversible |
| Token inconnu | ❌ DENIED (FAIL-CLOSED) |
| Expiration | ❌ DENIED si `now > valid_until` |
| Mismatch node/domain/cap | ❌ DENIED |
| Thread-safety | ✅ verrou par rédemption |
| Audit trail | ✅ toutes les tentatives (succès + refus) |
| Effacement d'historique | ❌ impossible — append-only |

---

## 3. Avant / Après

### AVANT (R455 et antérieur)

```python
# node_cert.py — cert_allows()
def cert_allows(cert, capability):
    payload = verify_node_certificate(cert)
    return can_role(payload["role"], capability)
# → appelable INFINIMENT avec le même cert, aucune trace
```

### APRÈS (R456)

```python
# Émission
tok = issue_token(node_id="node-artcb-ovh-2", domain_id="artcb-mainnet-1",
                  capability=CAP_PRODUCE, role="CONSENSUS", valid_until="2099-01-01T00:00:00Z")
store.register(tok)

# Première rédemption → allowed=True, état → CONSUMED
result = store.redeem(tok.token_id, expected_node_id="...", ...)
# assert result.allowed is True

# Deuxième rédemption → allowed=False, reason="already_consumed"
result2 = store.redeem(tok.token_id, expected_node_id="...", ...)
# assert result2.allowed is False
# assert result2.reason == "already_consumed"
```

---

## 4. Résultats des tests (25 tests C01-C25)

| Test | Description | Résultat |
|------|-------------|---------|
| C01 | Émission OK CONSENSUS/CAP_PRODUCE | PASS |
| C02 | Émission refusée HOST_ONLY → CAP_PRODUCE (FAIL-CLOSED) | PASS |
| C03 | Première rédemption → CONSUMED | PASS |
| C04 | Double rédemption → DENIED:already_consumed | PASS |
| C05 | Triple rédemption → DENIED (idempotent) | PASS |
| C06 | Token inconnu → DENIED:unknown_token | PASS |
| C07 | Token expiré → DENIED:token_expired | PASS |
| C08 | Capability mismatch → DENIED | PASS |
| C09 | Node mismatch → DENIED | PASS |
| C10 | Domain mismatch → DENIED | PASS |
| C11 | Audit trail conservé après refus | PASS |
| C12 | Audit trail conservé après succès | PASS |
| C13 | count_by_state() exact (1 pending, 1 consumed, 1 expired) | PASS |
| C14 | Deux tokens = deux token_id distincts | PASS |
| C15 | token_id dépend du nonce (10 émissions = 10 IDs uniques) | PASS |
| C16 | Duplicate registration → CapabilityTokenError | PASS |
| C17 | Token non-PENDING à l'enregistrement → erreur | PASS |
| C18 | HOST_ONLY ne peut pas émettre CAP_PRODUCE | PASS |
| C19 | GOVERNANCE peut émettre CAP_CHANGE_GOVERNANCE | PASS |
| C20 | state_of() → None pour token inconnu | PASS |
| C21 | state_of() → CONSUMED après rédemption réussie | PASS |
| C22 | get_audit_trail() filtré par token_id | PASS |
| C23 | 20 threads concurrents → exactement 1 CONSUMED | PASS |
| C24 | valid_until futur = non expiré | PASS |
| C25 | Raison "ok" dans audit trail sur succès | PASS |

| Suite | Résultat |
|-------|---------|
| `test_r456_capability_token_single_use.py` | **25/25 PASS** |
| Gate DO-178C (R430) | **124/124 PASS** |
| Non-régression R451-R455 | **147/147 PASS** |

---

## 5. Limites documentées

1. **Store en mémoire** — pas de persistance disque dans cette version. Pour production : brancher sur une table append-only (SQLite/Redis/chain evidence layer R451).
2. **Rotation de tokens non automatisée** — l'émetteur doit explicitement créer un nouveau token pour chaque opération.
3. **Intégration API non faite** — `cert_allows()` dans `node_cert.py` n'est pas encore remplacé par le mécanisme token. C'est l'étape suivante (R456-bis ou R457).
4. **Pas de révocation anticipée** — un token PENDING ne peut pas être annulé avant expiration (à implémenter si besoin).

---

## 6. Prochaines étapes

| R# | Issue | Description |
|----|-------|-------------|
| **R457** | #77 | NodeID ↔ clé TPM/live — 9 scénarios adversariaux |
| CI GitHub | R430 | Gate DO-178C autorité finale |
| R456-integ | — | Brancher capability_token.py sur les routes API P2P |
| TASK-001 | — | FAR/FRR/PAD vrais capteurs |

---

*Rapport généré post-exécution — ARTCB protocole R456 — SHA `be6e952`*
