# R462 — Quote TPM PCR dans le NodeTpmBinding (protocol v2)

**Date :** 2026-09-25T(session courante)  
**Auteur :** Agent Bob (mode DEBUG)  
**Commit :** en cours (groupé R461+R462+R463)  
**CERTIFIED_100=false**

---

## Résumé

R462 étend le protocole `ARTCB-NODE-TPM-BINDING` de v1 à v2 en incluant les champs `tpm_pcr0_sha256` et `tpm_quote_nonce` dans le payload signé. Cela couvre le gap identifié : un nœud malveillant pouvait déclarer `hardware_assurance_level="A"` avec un faux EK hash et signer lui-même.

---

## Contexte — gap sécurité identifié

R460 signait le tuple `(node_id, device_fingerprint, hardware_assurance_level, tpm_ek_cert_hash)`.  
Problème : rien n'empêche un nœud de fabriquer un `tpm_ek_cert_hash` fictif avec niveau A et de signer le tout avec sa propre clé Ed25519. La signature est valide cryptographiquement mais la prétention TPM est mensongère.

R462 ajoute la mesure PCR0 du TPM dans le payload signé, ce qui lie le binding à un état de boot mesurable — un nœud sans TPM réel ne peut pas fournir une valeur PCR0 cohérente.

**Limite honnête :** sans attestation distante complète (challenge/response TPM), R462 réduit le risque mais ne l'élimine pas. Une valeur PCR0 fabricée reste possible. L'architecture full D (preuve distante) reste le prochain chantier.

---

## Fichiers modifiés

### AVANT (état HEAD `1a3cb87` + R460)

| Fichier | État |
|---------|------|
| `src/artcb/security/node_tpm_binding.py` | v1 — payload sans PCR |
| `tests/test_r462_pcr_binding.py` | ❌ Absent |

### APRÈS (R462)

| Fichier | État |
|---------|------|
| `src/artcb/security/node_tpm_binding.py` | v2 — payload v2 avec PCR, `tpm_pcr_proven` |
| `tests/test_r462_pcr_binding.py` | ✅ Créé — T01–T22 |

---

## Modifications exactes

### `src/artcb/security/node_tpm_binding.py`

**Constante ajoutée :**
```python
# AVANT
BINDING_PROTOCOL = "ARTCB-NODE-TPM-BINDING-v1"

# APRÈS
BINDING_PROTOCOL = "ARTCB-NODE-TPM-BINDING-v1"
BINDING_PROTOCOL_V2 = "ARTCB-NODE-TPM-BINDING-v2"  # R462
```

**`_make_payload()` — signature étendue :**
```python
# AVANT — payload sans PCR
payload = { "protocol": BINDING_PROTOCOL, ..., "nonce": nonce }

# APRÈS — payload v2 si PCR présent
payload["protocol"] = BINDING_PROTOCOL_V2 if (tpm_pcr0_sha256 or tpm_quote_nonce) else BINDING_PROTOCOL
if tpm_pcr0_sha256 is not None:
    payload["tpm_pcr0_sha256"] = tpm_pcr0_sha256
if tpm_quote_nonce is not None:
    payload["tpm_quote_nonce"] = tpm_quote_nonce
```

**`NodeTpmBinding` — champs ajoutés :**
```python
# AVANT — pas de champs PCR
# (fin du dataclass)

# APRÈS
tpm_pcr0_sha256: str | None = None
tpm_quote_nonce: str | None = None
tpm_pcr_proven: bool = False
```

**`create_node_tpm_binding()` — tpm_pcr_proven :**
```python
# AVANT — tpm_pcr_proven absent

# APRÈS
tpm_pcr_proven = (
    hardware_assurance_level in TPM_PROVEN_LEVELS
    and bool(tpm_pcr0_sha256)
)
```

**`verify_node_tpm_binding()` — reconstruction payload v2 :**
```python
# AVANT — reconstruit toujours payload v1

# APRÈS — inclut tpm_pcr0_sha256 et tpm_quote_nonce si présents
payload = _make_payload(
    ...,
    tpm_pcr0_sha256=binding.tpm_pcr0_sha256,
    tpm_quote_nonce=binding.tpm_quote_nonce,
)
```

---

## Règles d'invariant

| Champ | Valeur | Condition |
|-------|--------|-----------|
| `tpm_proven` | `True` | `level ∈ {A,B}` ET `tpm_ek_cert_hash` présent |
| `tpm_pcr_proven` | `True` | `level ∈ {A,B}` ET `tpm_pcr0_sha256` présent |
| `tpm_pcr_proven` | `False` | niveau C/D/E **même si** `tpm_pcr0_sha256` fourni |
| `protocol` | `v2` | `tpm_pcr0_sha256` ou `tpm_quote_nonce` présent |
| `protocol` | `v1` | les deux `None` |
| `certified` | `False` | invariant absolu |
| `unique_human_proven` | `False` | invariant absolu |

---

## Tests

Fichier : `tests/test_r462_pcr_binding.py`  
Suite : **T01–T22** — 22 tests PASS

| Test | Description |
|------|-------------|
| T01 | Binding v2 avec pcr0 → protocol = v2 |
| T02 | Binding v1 sans pcr0 → protocol = v1 |
| T03 | `tpm_pcr_proven=True` niveau A + pcr0 |
| T04 | `tpm_pcr_proven=False` niveau E même avec pcr0 |
| T05 | `tpm_pcr_proven=True` niveau B + pcr0 |
| T06 | `tpm_pcr_proven=False` si pcr0=None même niveau A |
| T07 | `verify_node_tpm_binding` v2 → valid=True |
| T08 | `tpm_pcr0_sha256` altéré → verify invalide (FAIL-CLOSED) |
| T09 | `tpm_quote_nonce` altéré → verify invalide |
| T10 | `certified=False` dans BindingVerificationResult |
| T11 | `unique_human_proven=False` dans NodeTpmBinding |
| T12 | `tpm_proven=True` niveau A + EK cert |
| T13 | `tpm_proven=False` niveau E |
| T14 | `require_tpm_proven=True` niveau A → valid |
| T15 | `require_tpm_proven=True` niveau E → invalid + reason |
| T16 | `to_dict()` v2 contient `tpm_pcr0_sha256`, `tpm_quote_nonce`, `tpm_pcr_proven` |
| T17 | `to_dict()` v1 → champs PCR None/False |
| T18 | Signatures croisées (nœud A signe pour B) → invalid |
| T19 | `expected_node_id` incorrect → invalid + node_id_match=False |
| T20 | `note` contient `certified=False` + `unique_human_proven=False` |
| T21 | PCR0 présent → toute altération invalide la signature v2 |
| T22 | Niveau C + pcr0 → `tpm_pcr_proven=False` |

---

## Résultats

```
tests/test_r462_pcr_binding.py  22/22 PASS
tests/test_r461_node_tpm_binding_routes.py  20/20 PASS  (non-régression R461)
tests/test_r460_node_tpm_binding.py  22/22 PASS  (non-régression R460)
Non-régression biométrie totale : 162/162 PASS
```

---

## Chaîne de preuve — état d'avancement

| Niveau | Description | État R462 |
|--------|-------------|-----------|
| A | TPM physique présent (`/dev/tpm0`) | Documenté (audit TPM) |
| B | TPM accessible au processus ARTCB | `hardware_identity.py` |
| C | Identité ARTCB dérivée du TPM (EK cert hash signé) | ✅ R460/R461 |
| C+ | Mesure PCR0 incluse dans le binding signé | ✅ R462 |
| D | Preuve distante (challenge/response TPM attestation) | 🔴 Non implémenté |

---

## Limites honnêtes

- `tpm_pcr0_sha256` est fourni par le nœud lui-même — sans challenge nonce du vérificateur, un nœud malveillant peut rejouer une valeur PCR0 ancienne.
- L'attestation distante complète (nonce challenge → TPM2_Quote → signature EK → vérification par le pair) est le chantier suivant (niveau D).
- `CERTIFIED_100=false`.
