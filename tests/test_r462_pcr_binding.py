"""Tests R462 — Quote TPM PCR dans le NodeTpmBinding.

Suite : T01–T22
Protocole : ARTCB-NODE-TPM-BINDING-v2
Module testé : src/artcb/security/node_tpm_binding.py (extension R462)

Stratégie :
    - Vérifier que les champs PCR (tpm_pcr0_sha256, tpm_quote_nonce, tpm_pcr_proven)
      sont correctement inclus dans le payload signé.
    - Vérifier que la signature v2 ne passe PAS avec le payload v1 (et vice-versa).
    - Vérifier les invariants : certified=False, unique_human_proven=False absolu.
    - Vérifier tpm_pcr_proven=True ssi niveau A/B ET pcr0_sha256 présent.
    - FAIL-CLOSED sur pcr0 altéré après signature.
    - Bindings réels (nacl + optionnel liboqs) — pas de stub.

CERTIFIED_100=false.
"""
from __future__ import annotations

import secrets
import pytest
from nacl import signing as nacl_signing

from src.artcb.security.node_tpm_binding import (
    BINDING_PROTOCOL,
    BINDING_PROTOCOL_V2,
    NodeTpmBinding,
    BindingVerificationResult,
    create_node_tpm_binding,
    verify_node_tpm_binding,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ed_key():
    """Paire Ed25519 pour les tests R462."""
    return nacl_signing.SigningKey.generate()


@pytest.fixture(scope="module")
def ed_key_b():
    """Deuxième paire Ed25519 pour tests multi-nœuds."""
    return nacl_signing.SigningKey.generate()


def _make_binding_v2(ed_key, node_id="node-pcr-001", level="A"):
    """Helper : binding v2 avec PCR0 + nonce."""
    return create_node_tpm_binding(
        node_id=node_id,
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="a" * 64,
        hardware_assurance_level=level,
        hardware_kind="physical_tpm" if level in ("A", "B") else "software",
        tpm_ek_cert_hash="b" * 64 if level in ("A", "B") else None,
        tpm_kind="physical" if level == "A" else ("virtual" if level == "B" else "absent"),
        platform_system="Linux",
        env_type="test",
        tpm_pcr0_sha256="c" * 64,
        tpm_quote_nonce=secrets.token_hex(32),
    )


def _make_binding_v1(ed_key, node_id="node-v1-001", level="E"):
    """Helper : binding v1 sans PCR (niveau E)."""
    return create_node_tpm_binding(
        node_id=node_id,
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="d" * 64,
        hardware_assurance_level=level,
        hardware_kind="software",
        tpm_ek_cert_hash=None,
        tpm_kind="absent",
        platform_system="Linux",
        env_type="test",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

# T01 — Binding v2 créé avec pcr0_sha256 → protocol = BINDING_PROTOCOL_V2
def test_T01_v2_protocol_field(ed_key):
    b = _make_binding_v2(ed_key)
    assert b.to_dict()["protocol"] == BINDING_PROTOCOL_V2


# T02 — Binding v1 créé sans pcr0 → protocol = BINDING_PROTOCOL
def test_T02_v1_protocol_field(ed_key):
    b = _make_binding_v1(ed_key)
    assert b.to_dict()["protocol"] == BINDING_PROTOCOL


# T03 — tpm_pcr_proven=True pour niveau A avec pcr0_sha256
def test_T03_pcr_proven_level_A(ed_key):
    b = _make_binding_v2(ed_key, level="A")
    assert b.tpm_pcr_proven is True


# T04 — tpm_pcr_proven=False pour niveau E même avec pcr0_sha256 fourni
def test_T04_pcr_proven_false_level_E(ed_key):
    b = create_node_tpm_binding(
        node_id="node-level-e",
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="e" * 64,
        hardware_assurance_level="E",
        hardware_kind="software",
        tpm_ek_cert_hash=None,
        tpm_kind="absent",
        platform_system="Linux",
        env_type="test",
        tpm_pcr0_sha256="f" * 64,  # fourni mais niveau E → tpm_pcr_proven=False
        tpm_quote_nonce=secrets.token_hex(32),
    )
    assert b.tpm_pcr_proven is False


# T05 — tpm_pcr_proven=True pour niveau B avec pcr0_sha256
def test_T05_pcr_proven_level_B(ed_key):
    b = _make_binding_v2(ed_key, level="B")
    assert b.tpm_pcr_proven is True


# T06 — tpm_pcr_proven=False si pcr0_sha256=None même niveau A
def test_T06_pcr_proven_false_if_no_pcr0(ed_key):
    b = create_node_tpm_binding(
        node_id="node-no-pcr",
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="g" * 64,
        hardware_assurance_level="A",
        hardware_kind="physical_tpm",
        tpm_ek_cert_hash="h" * 64,
        tpm_kind="physical",
        platform_system="Linux",
        env_type="test",
        tpm_pcr0_sha256=None,  # pas de PCR → pcr_proven=False
    )
    assert b.tpm_pcr_proven is False


# T07 — verify_node_tpm_binding v2 → valid=True
def test_T07_verify_v2_valid(ed_key):
    b = _make_binding_v2(ed_key)
    result = verify_node_tpm_binding(b, expected_node_id="node-pcr-001")
    assert result.valid is True
    assert result.ed25519_ok is True
    assert result.certified is False


# T08 — Altérer tpm_pcr0_sha256 après signature → verify invalide (FAIL-CLOSED)
def test_T08_verify_pcr0_tampered_fails(ed_key):
    b = _make_binding_v2(ed_key)
    # Altération du PCR0 après signature
    b_bad = NodeTpmBinding(
        **{
            **b.__dict__,
            "tpm_pcr0_sha256": "0" * 64,  # PCR0 altéré
        }
    )
    result = verify_node_tpm_binding(b_bad, expected_node_id="node-pcr-001")
    assert result.valid is False


# T09 — Altérer tpm_quote_nonce après signature → verify invalide
def test_T09_verify_nonce_tampered_fails(ed_key):
    b = _make_binding_v2(ed_key)
    b_bad = NodeTpmBinding(**{**b.__dict__, "tpm_quote_nonce": "0" * 64})
    result = verify_node_tpm_binding(b_bad, expected_node_id="node-pcr-001")
    assert result.valid is False


# T10 — Invariant certified=False dans BindingVerificationResult
def test_T10_invariant_certified_false_in_result(ed_key):
    b = _make_binding_v2(ed_key)
    result = verify_node_tpm_binding(b, expected_node_id="node-pcr-001")
    assert result.certified is False
    d = result.to_dict()
    assert d["certified"] is False


# T11 — Invariant unique_human_proven=False dans le binding
def test_T11_invariant_unique_human_proven_false(ed_key):
    b = _make_binding_v2(ed_key)
    assert b.unique_human_proven is False
    assert b.to_dict()["unique_human_proven"] is False


# T12 — tpm_proven=True pour niveau A avec EK cert
def test_T12_tpm_proven_level_A(ed_key):
    b = _make_binding_v2(ed_key, level="A")
    assert b.tpm_proven is True


# T13 — tpm_proven=False pour niveau E
def test_T13_tpm_proven_false_level_E(ed_key):
    b = _make_binding_v1(ed_key, level="E")
    assert b.tpm_proven is False


# T14 — verify v2 : require_tpm_proven=True avec niveau A → valid=True
def test_T14_require_tpm_proven_level_A(ed_key):
    b = _make_binding_v2(ed_key, level="A")
    result = verify_node_tpm_binding(b, expected_node_id="node-pcr-001", require_tpm_proven=True)
    assert result.valid is True


# T15 — verify v2 : require_tpm_proven=True avec niveau E → valid=False
def test_T15_require_tpm_proven_level_E_fails(ed_key):
    b = _make_binding_v1(ed_key, level="E")
    result = verify_node_tpm_binding(b, expected_node_id="node-v1-001", require_tpm_proven=True)
    assert result.valid is False
    assert result.failure_reason == "tpm_proven_required_not_satisfied"


# T16 — to_dict() v2 contient tpm_pcr0_sha256 et tpm_quote_nonce
def test_T16_to_dict_contains_pcr_fields(ed_key):
    b = _make_binding_v2(ed_key)
    d = b.to_dict()
    assert "tpm_pcr0_sha256" in d
    assert "tpm_quote_nonce" in d
    assert "tpm_pcr_proven" in d
    assert d["tpm_pcr0_sha256"] == "c" * 64


# T17 — to_dict() v1 contient tpm_pcr0_sha256=None
def test_T17_v1_pcr_fields_are_none(ed_key):
    b = _make_binding_v1(ed_key)
    d = b.to_dict()
    assert d["tpm_pcr0_sha256"] is None
    assert d["tpm_quote_nonce"] is None
    assert d["tpm_pcr_proven"] is False


# T18 — Deux nœuds différents, signatures croisées → invalides
def test_T18_cross_node_signatures_invalid(ed_key, ed_key_b):
    b_a = _make_binding_v2(ed_key, node_id="node-A")
    b_b = _make_binding_v2(ed_key_b, node_id="node-B")
    # Signature de A avec node_id B → node_id_mismatch
    b_cross = NodeTpmBinding(
        **{**b_a.__dict__, "node_id": "node-B"}
    )
    result = verify_node_tpm_binding(b_cross, expected_node_id="node-B")
    assert result.valid is False


# T19 — verify v2 avec expected_node_id incorrect → valid=False
def test_T19_wrong_expected_node_id(ed_key):
    b = _make_binding_v2(ed_key, node_id="node-pcr-001")
    result = verify_node_tpm_binding(b, expected_node_id="node-wrong")
    assert result.valid is False
    assert result.node_id_match is False


# T20 — note du binding v2 contient protocol et invariants
def test_T20_note_contains_invariants(ed_key):
    b = _make_binding_v2(ed_key, level="A")
    assert "certified=False" in b.note
    assert "unique_human_proven=False" in b.note


# T21 — tpm_pcr_proven est inclus dans le payload signé (v2 accepté, pas v1)
def test_T21_pcr_proven_in_signed_payload(ed_key):
    """PCR0 présent → protocol=v2 → signature couvre PCR0 — toute altération → invalid."""
    b = _make_binding_v2(ed_key, level="A")
    # Vérification nominale
    ok = verify_node_tpm_binding(b, expected_node_id="node-pcr-001")
    assert ok.valid is True
    # Si on retire PCR0, le payload reconstruit sera v1 → signature v2 invalide
    b_no_pcr = NodeTpmBinding(**{**b.__dict__, "tpm_pcr0_sha256": None, "tpm_quote_nonce": None})
    bad = verify_node_tpm_binding(b_no_pcr, expected_node_id="node-pcr-001")
    assert bad.valid is False


# T22 — Binding v2 avec niveau C → tpm_pcr_proven=False (niveau C non éligible)
def test_T22_level_C_pcr_proven_false(ed_key):
    b = create_node_tpm_binding(
        node_id="node-level-c",
        ed25519_signing_key_bytes=bytes(ed_key),
        device_fingerprint="i" * 64,
        hardware_assurance_level="C",
        hardware_kind="tee",
        tpm_ek_cert_hash=None,
        tpm_kind="absent",
        platform_system="Linux",
        env_type="test",
        tpm_pcr0_sha256="j" * 64,  # fourni mais niveau C → tpm_pcr_proven=False
        tpm_quote_nonce=secrets.token_hex(32),
    )
    assert b.tpm_pcr_proven is False
    assert b.tpm_proven is False
