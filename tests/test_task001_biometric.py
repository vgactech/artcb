"""Tests TASK-001 — Secure Sketch FuzzyExtractor biométrique (2026-09-18).

Suite de tests couvrant :
  A  : fuzzy_extract() — structure du résultat
  B  : fuzzy_extract() — helper_data = salt || sketch || confirm
  C  : fuzzy_reproduce() — même template → secret identique
  D  : fuzzy_reproduce() — template différent → None (dist > 0 sans ECC)
  E  : fuzzy_reproduce() — helper_data corrompu → None
  F  : fuzzy_reproduce() — helper trop court → None
  G  : fuzzy_extract() — deux enrôlements, même template, sels différents → secrets différents
  H  : fuzzy_extract() — template vide → ValueError
  I  : fuzzy_reproduce() — helper hex invalide → None
  J  : enroll_biometric() → résultat public complet + secret privé
  K  : enroll_biometric() → secret_hex absent du résultat public
  L  : check_uniqueness() — template déjà enregistré → match_found=True
  M  : check_uniqueness() — template nouveau → match_found=False
  N  : derive_human_id() — déterministe (même inputs → même human_id)
  O  : unique_human_proven toujours False
  P  : algorithm = ARTCB-SECURE-SKETCH-HKDF-SHA256-v2 (pas l'ancien stub)
  Q  : biometric_version = 2 (Secure Sketch)
  R  : fuzzy_extract() + noise_tolerance > 0 → warning + tolérance réelle = 0
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch
import logging

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artcb.identity.biometric_onchain import (
    FuzzyExtractorResult,
    HumanIdentityRecord,
    BiometricEnrollmentResult,
    UniquenessCheckResult,
    _ALGO_NAME,
    _SALT_BYTES,
    _CONFIRM_BYTES,
    fuzzy_extract,
    fuzzy_reproduce,
    enroll_biometric,
    check_uniqueness,
    derive_human_id,
)
from artcb.crypto.homomorphic import commit_biometric_template


# ─── Fixtures ─────────────────────────────────────────────────────────────────

TEMPLATE_A = b"template_biometrique_normalise_exemple_utilisateur_001"
TEMPLATE_B = b"template_biometrique_normalise_exemple_utilisateur_002"


# ─── Test A : structure du résultat fuzzy_extract ─────────────────────────────

def test_A_fuzzy_extract_result_structure() -> None:
    """Test A : fuzzy_extract() retourne un FuzzyExtractorResult avec les bons champs."""
    result = fuzzy_extract(TEMPLATE_A)
    assert isinstance(result, FuzzyExtractorResult)
    assert result.secret_hex and len(result.secret_hex) == 64   # 32 octets hex
    assert result.helper_data_hex and len(result.helper_data_hex) > 0
    assert result.template_hash_hex and len(result.template_hash_hex) == 64  # SHA-256
    assert result.algorithm == _ALGO_NAME
    assert result.certified is False


# ─── Test B : structure helper_data = salt || sketch || confirm ───────────────

def test_B_helper_data_structure() -> None:
    """Test B : helper_data_hex encode salt(32) || sketch(32) || confirm(16) = 80 octets.

    Avec le schéma v2 (TASK-001), sketch = seed XOR pad = 32 octets fixes.
    helper est donc toujours 32 + 32 + 16 = 80 octets, indépendamment de len(template).
    """
    from artcb.identity.biometric_onchain import _SEED_BYTES
    result = fuzzy_extract(TEMPLATE_A)
    helper = bytes.fromhex(result.helper_data_hex)
    expected = _SALT_BYTES + _SEED_BYTES + _CONFIRM_BYTES  # 32 + 32 + 16 = 80
    assert len(helper) == expected, (
        f"helper_data longueur {len(helper)} ≠ attendu {expected}"
    )
    # Salt = premiers 32 octets
    salt = helper[:_SALT_BYTES]
    assert len(salt) == _SALT_BYTES
    # Sketch = 32 octets (seed XOR pad)
    sketch = helper[_SALT_BYTES: _SALT_BYTES + _SEED_BYTES]
    assert len(sketch) == _SEED_BYTES
    # Confirm = 16 octets
    confirm = helper[_SALT_BYTES + _SEED_BYTES: _SALT_BYTES + _SEED_BYTES + _CONFIRM_BYTES]
    assert len(confirm) == _CONFIRM_BYTES


# ─── Test C : fuzzy_reproduce — même template → secret identique ──────────────

def test_C_fuzzy_reproduce_same_template() -> None:
    """Test C : fuzzy_reproduce(template, helper) == secret original si template identique."""
    result = fuzzy_extract(TEMPLATE_A)
    reproduced = fuzzy_reproduce(TEMPLATE_A, result.helper_data_hex)
    assert reproduced is not None, "Reproduction doit réussir avec le même template"
    assert reproduced == result.secret_hex, (
        "Secret reproduit doit être identique au secret original"
    )


# ─── Test D : fuzzy_reproduce — template différent → None ────────────────────

def test_D_fuzzy_reproduce_different_template_fails() -> None:
    """Test D (adversarial) : template différent → fuzzy_reproduce retourne None.

    Sans ECC externe, dist > 0 → reproduction impossible (TASK-001 honnêteté).
    """
    result = fuzzy_extract(TEMPLATE_A)
    reproduced = fuzzy_reproduce(TEMPLATE_B, result.helper_data_hex)
    assert reproduced is None, (
        "Template différent doit échouer la reproduction (dist > 0, pas d'ECC)"
    )


# ─── Test E : fuzzy_reproduce — helper corrompu ──────────────────────────────

def test_E_fuzzy_reproduce_corrupted_helper_fails() -> None:
    """Test E (adversarial) : helper_data corrompu → None."""
    result = fuzzy_extract(TEMPLATE_A)
    helper = bytes.fromhex(result.helper_data_hex)
    # Corrompre le confirm (derniers 16 octets)
    corrupted = helper[:-_CONFIRM_BYTES] + bytes(_CONFIRM_BYTES)
    reproduced = fuzzy_reproduce(TEMPLATE_A, corrupted.hex())
    assert reproduced is None, "Helper corrompu doit échouer la reproduction"


# ─── Test F : fuzzy_reproduce — helper trop court → None ─────────────────────

def test_F_fuzzy_reproduce_short_helper_fails() -> None:
    """Test F (adversarial) : helper_data trop court → None."""
    result = fuzzy_reproduce(TEMPLATE_A, "aabbccdd")
    assert result is None


# ─── Test G : deux enrôlements, sels différents → secrets différents ─────────

def test_G_different_salts_give_different_secrets() -> None:
    """Test G : deux enrôlements du même template avec des sels différents produisent
    des secrets distincts (propriété d'indistinguabilité).
    """
    r1 = fuzzy_extract(TEMPLATE_A, salt=os.urandom(32))
    r2 = fuzzy_extract(TEMPLATE_A, salt=os.urandom(32))
    # Sels différents → secrets différents
    assert r1.secret_hex != r2.secret_hex
    # Chaque reproduction réussit avec son propre helper
    assert fuzzy_reproduce(TEMPLATE_A, r1.helper_data_hex) == r1.secret_hex
    assert fuzzy_reproduce(TEMPLATE_A, r2.helper_data_hex) == r2.secret_hex
    # Mais cross-reproduce échoue
    assert fuzzy_reproduce(TEMPLATE_A, r1.helper_data_hex) != r2.secret_hex


# ─── Test H : template vide → ValueError ─────────────────────────────────────

def test_H_empty_template_raises() -> None:
    """Test H : template_bytes vide → ValueError."""
    with pytest.raises(ValueError, match="vide"):
        fuzzy_extract(b"")


# ─── Test I : helper hex invalide → None ─────────────────────────────────────

def test_I_invalid_hex_helper_returns_none() -> None:
    """Test I (adversarial) : helper_data_hex non-hexadécimal → None."""
    result = fuzzy_reproduce(TEMPLATE_A, "ZZZINVALIDHEX!!")
    assert result is None


# ─── Test J : enroll_biometric — résultat public complet ─────────────────────

def test_J_enroll_biometric_public_fields() -> None:
    """Test J : enroll_biometric() retourne les champs publics complets."""
    result, secret_hex, blinding_hex = enroll_biometric(TEMPLATE_A)
    assert isinstance(result, BiometricEnrollmentResult)
    assert result.human_id.startswith("human_")
    assert "commitment" in result.human_identity_record
    assert "helper_data" in result.human_identity_record
    assert "template_hash" in result.human_identity_record
    assert result.unique_human_proven is False
    assert result.status == "enrolled"
    # Champs privés retournés séparément (jamais dans le record public)
    assert len(secret_hex) == 64
    assert len(blinding_hex) > 0


# ─── Test K : secret_hex absent du résultat public ───────────────────────────

def test_K_secret_not_in_public_record() -> None:
    """Test K (sécurité) : secret_hex n'apparaît jamais dans le record public."""
    result, secret_hex, blinding_hex = enroll_biometric(TEMPLATE_A)
    record_json = result.human_identity_record
    # Le secret ne doit jamais figurer dans le record on-chain
    for v in record_json.values():
        if isinstance(v, str):
            assert secret_hex not in v, "secret_hex trouvé dans le record public !"
    # Le blinding non plus
    for v in record_json.values():
        if isinstance(v, str):
            assert blinding_hex not in v, "blinding_hex trouvé dans le record public !"


# ─── Test L : check_uniqueness — déjà enregistré ─────────────────────────────

def test_L_uniqueness_match_found() -> None:
    """Test L : check_uniqueness détecte un template déjà enregistré."""
    result, _, _ = enroll_biometric(TEMPLATE_A)
    existing = [result.human_identity_record]
    commitment = commit_biometric_template(TEMPLATE_A)
    check = check_uniqueness(commitment, existing)
    assert check.match_found is True
    assert check.existing_human_id == result.human_id
    assert check.unique_human_proven is False


# ─── Test M : check_uniqueness — template nouveau ────────────────────────────

def test_M_uniqueness_no_match() -> None:
    """Test M : check_uniqueness autorise un nouveau template."""
    result, _, _ = enroll_biometric(TEMPLATE_A)
    existing = [result.human_identity_record]
    commitment_b = commit_biometric_template(TEMPLATE_B)
    check = check_uniqueness(commitment_b, existing)
    assert check.match_found is False
    assert check.unique_human_proven is False


# ─── Test N : derive_human_id — déterministe ─────────────────────────────────

def test_N_derive_human_id_deterministic() -> None:
    """Test N : derive_human_id produit le même résultat pour les mêmes inputs."""
    r1, _, _ = enroll_biometric(TEMPLATE_A)
    r2, _, _ = enroll_biometric(TEMPLATE_A)
    # Les human_id diffèrent (sels différents) mais la fonction est déterministe sur ses inputs
    commitment = r1.human_identity_record["commitment"]
    helper = r1.human_identity_record["helper_data"]
    hid1 = derive_human_id(commitment, helper)
    hid2 = derive_human_id(commitment, helper)
    assert hid1 == hid2, "derive_human_id doit être déterministe"


# ─── Test O : unique_human_proven toujours False ─────────────────────────────

def test_O_unique_human_proven_always_false() -> None:
    """Test O : unique_human_proven=False dans tous les objets retournés."""
    fe = fuzzy_extract(TEMPLATE_A)
    assert fe.certified is False
    result, _, _ = enroll_biometric(TEMPLATE_A)
    assert result.unique_human_proven is False
    assert result.human_identity_record["unique_human_proven"] is False


# ─── Test P : algorithm = v2 (Secure Sketch) ─────────────────────────────────

def test_P_algorithm_is_v2_not_stub() -> None:
    """Test P : l'algorithme est ARTCB-SECURE-SKETCH-HKDF-SHA256-v2, pas l'ancien stub."""
    fe = fuzzy_extract(TEMPLATE_A)
    assert fe.algorithm == "ARTCB-SECURE-SKETCH-HKDF-SHA256-v2"
    assert "STUB" not in fe.algorithm
    assert "SHA512" not in fe.algorithm


# ─── Test Q : biometric_version = 2 ──────────────────────────────────────────

def test_Q_biometric_version_is_2() -> None:
    """Test Q : biometric_version=2 (Secure Sketch v2, pas v1 stub)."""
    result, _, _ = enroll_biometric(TEMPLATE_A)
    assert result.human_identity_record["biometric_version"] == 2
    assert result.human_identity_record["verification_policy"] == "secure_sketch_hkdf_v2"


# ─── Test R : noise_tolerance > 0 → warning ──────────────────────────────────

def test_R_noise_tolerance_warning() -> None:
    """Test R : noise_tolerance > 0 sans ECC → warning loggé, tolérance effective = 0."""
    with patch.object(
        __import__("artcb.identity.biometric_onchain", fromlist=["logger"]).logger,
        "warning",
    ) as mock_warn:
        result = fuzzy_extract(TEMPLATE_A, noise_tolerance=8)
        mock_warn.assert_called_once()
        warn_msg = mock_warn.call_args[0][0]
        assert "noise_tolerance" in warn_msg or "ECC" in warn_msg

    # Malgré le warning, la fonctionnalité de base reste opérationnelle
    assert result.secret_hex
    reproduced = fuzzy_reproduce(TEMPLATE_A, result.helper_data_hex)
    assert reproduced == result.secret_hex
