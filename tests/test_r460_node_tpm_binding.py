"""Tests R460 — Liaison cryptographique TPM EK → NodeID.

Scénarios :
    T01  Niveau A (bare-metal simulé) : fingerprint TPM-based → binding créé
    T02  Niveau A : tpm_proven=True ssi EK cert hash présent
    T03  Niveau B (vTPM) : tpm_proven=True ssi EK cert hash présent
    T04  Niveau C (TEE) : tpm_proven=False
    T05  Niveau D (HSM) : tpm_proven=False
    T06  Niveau E (software) : tpm_proven=False
    T07  node_id vide → ValueError
    T08  device_fingerprint vide → ValueError
    T09  Vérification OK même NodeID → valid=True
    T10  Vérification NodeID mismatch → valid=False, failure_reason=node_id_mismatch
    T11  Falsification device_fingerprint → valid=False (signature invalide)
    T12  Falsification hardware_assurance_level → valid=False
    T13  Falsification tpm_ek_cert_hash → valid=False
    T14  certified=False invariant absolu
    T15  unique_human_proven=False invariant absolu
    T16  to_dict() round-trip payload complet
    T17  Niveau A sans EK cert → tpm_proven=False (invariant)
    T18  require_tpm_proven=True + niveau E → valid=False
    T19  require_tpm_proven=True + niveau A + EK → valid=True
    T20  Nonce différent à chaque create (anti-rejeu)
    T21  Signature Ed25519 incorrecte → valid=False
    T22  BindingVerificationResult.to_dict() structure complète
"""

from __future__ import annotations

import hashlib
import secrets

import pytest

# Import sous test
from src.artcb.security.node_tpm_binding import (
    BINDING_PROTOCOL,
    BindingVerificationResult,
    NodeTpmBinding,
    create_node_tpm_binding,
    verify_node_tpm_binding,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

try:
    from nacl import signing as _nacl_signing
    _HAS_NACL = True
except ImportError:
    _HAS_NACL = False

pytestmark = pytest.mark.skipif(not _HAS_NACL, reason="PyNaCl requis pour ces tests")


def _make_ed25519_key() -> bytes:
    """Génère une clé Ed25519 aléatoire (32 octets)."""
    return _nacl_signing.SigningKey.generate().encode()


def _fake_fingerprint(level: str) -> str:
    """Fingerprint SHA-256 simulé selon le niveau."""
    raw = f"fingerprint:test:level:{level}:{secrets.token_hex(8)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _fake_ek_cert_hash() -> str:
    """Hash SHA-256 simulé d'un certificat EK TPM."""
    return hashlib.sha256(b"fake-ek-cert-nuvoton-2026").hexdigest()


def _create_binding_level(level: str, *, with_ek: bool = True) -> NodeTpmBinding:
    """Factory de binding selon le niveau A–E."""
    level_map = {
        "A": ("physical_tpm", "physical"),
        "B": ("virtual_tpm", "virtual"),
        "C": ("tee", "absent"),
        "D": ("hsm", "absent"),
        "E": ("software", "absent"),
    }
    hardware_kind, tpm_kind = level_map[level]
    ek = _fake_ek_cert_hash() if with_ek and level in {"A", "B"} else None
    return create_node_tpm_binding(
        node_id=f"node-test-{level}",
        ed25519_signing_key_bytes=_make_ed25519_key(),
        device_fingerprint=_fake_fingerprint(level),
        hardware_assurance_level=level,
        hardware_kind=hardware_kind,
        tpm_ek_cert_hash=ek,
        tpm_kind=tpm_kind,
        platform_system="Linux",
        env_type="linux_headless",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_T01_niveau_A_binding_cree():
    """T01 — Niveau A : binding créé sans exception."""
    binding = _create_binding_level("A")
    assert binding.node_id == "node-test-A"
    assert binding.hardware_assurance_level == "A"
    assert binding.hardware_kind == "physical_tpm"
    assert binding.ed25519_public_key_hex
    assert binding.ed25519_signature_hex
    assert len(binding.nonce) == 64  # 32 octets hex


def test_T02_niveau_A_tpm_proven_avec_ek():
    """T02 — Niveau A avec EK cert → tpm_proven=True."""
    binding = _create_binding_level("A", with_ek=True)
    assert binding.tpm_proven is True
    assert binding.tpm_ek_cert_hash is not None


def test_T03_niveau_B_tpm_proven_avec_ek():
    """T03 — Niveau B (vTPM) avec EK cert → tpm_proven=True."""
    binding = _create_binding_level("B", with_ek=True)
    assert binding.tpm_proven is True
    assert binding.tpm_kind == "virtual"


def test_T04_niveau_C_tpm_proven_false():
    """T04 — Niveau C (TEE) → tpm_proven=False invariant."""
    binding = _create_binding_level("C")
    assert binding.tpm_proven is False
    assert binding.hardware_kind == "tee"


def test_T05_niveau_D_tpm_proven_false():
    """T05 — Niveau D (HSM) → tpm_proven=False invariant."""
    binding = _create_binding_level("D")
    assert binding.tpm_proven is False
    assert binding.hardware_kind == "hsm"


def test_T06_niveau_E_software_tpm_proven_false():
    """T06 — Niveau E (software) → tpm_proven=False invariant."""
    binding = _create_binding_level("E")
    assert binding.tpm_proven is False
    assert binding.hardware_kind == "software"
    assert binding.tpm_kind == "absent"


def test_T07_node_id_vide_raise_valueerror():
    """T07 — node_id vide → ValueError."""
    with pytest.raises(ValueError, match="node_id"):
        create_node_tpm_binding(
            node_id="",
            ed25519_signing_key_bytes=_make_ed25519_key(),
            device_fingerprint=_fake_fingerprint("E"),
            hardware_assurance_level="E",
            hardware_kind="software",
            tpm_ek_cert_hash=None,
        )


def test_T08_device_fingerprint_vide_raise_valueerror():
    """T08 — device_fingerprint vide → ValueError."""
    with pytest.raises(ValueError, match="device_fingerprint"):
        create_node_tpm_binding(
            node_id="node-test",
            ed25519_signing_key_bytes=_make_ed25519_key(),
            device_fingerprint="",
            hardware_assurance_level="E",
            hardware_kind="software",
            tpm_ek_cert_hash=None,
        )


def test_T09_verification_ok_meme_node_id():
    """T09 — Vérification OK avec le bon node_id → valid=True."""
    sk_bytes = _make_ed25519_key()
    binding = create_node_tpm_binding(
        node_id="node-ovh2",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("A"),
        hardware_assurance_level="A",
        hardware_kind="physical_tpm",
        tpm_ek_cert_hash=_fake_ek_cert_hash(),
        tpm_kind="physical",
    )
    result = verify_node_tpm_binding(binding, expected_node_id="node-ovh2")
    assert result.valid is True
    assert result.ed25519_ok is True
    assert result.node_id_match is True
    assert result.failure_reason is None
    assert result.certified is False


def test_T10_verification_node_id_mismatch():
    """T10 — NodeID mismatch → valid=False, failure_reason=node_id_mismatch."""
    binding = _create_binding_level("A")
    result = verify_node_tpm_binding(binding, expected_node_id="node-AUTRE")
    assert result.valid is False
    assert result.node_id_match is False
    assert result.failure_reason == "node_id_mismatch"


def test_T11_falsification_device_fingerprint():
    """T11 — Falsifier device_fingerprint après signature → valid=False."""
    sk_bytes = _make_ed25519_key()
    binding = create_node_tpm_binding(
        node_id="node-test",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("A"),
        hardware_assurance_level="A",
        hardware_kind="physical_tpm",
        tpm_ek_cert_hash=_fake_ek_cert_hash(),
        tpm_kind="physical",
    )
    # Falsification : on altère le fingerprint APRÈS signature
    import dataclasses
    tampered = dataclasses.replace(
        binding,
        device_fingerprint="0" * 64,  # fingerprint falsifié
    )
    result = verify_node_tpm_binding(tampered, expected_node_id="node-test")
    assert result.valid is False
    assert result.ed25519_ok is False


def test_T12_falsification_hardware_assurance_level():
    """T12 — Falsifier hardware_assurance_level → valid=False."""
    import dataclasses
    sk_bytes = _make_ed25519_key()
    binding = create_node_tpm_binding(
        node_id="node-test",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("E"),
        hardware_assurance_level="E",
        hardware_kind="software",
        tpm_ek_cert_hash=None,
        tpm_kind="absent",
    )
    # Élévation frauduleuse E → A
    tampered = dataclasses.replace(binding, hardware_assurance_level="A")
    result = verify_node_tpm_binding(tampered, expected_node_id="node-test")
    assert result.valid is False


def test_T13_falsification_tpm_ek_cert_hash():
    """T13 — Falsifier tpm_ek_cert_hash → valid=False."""
    import dataclasses
    sk_bytes = _make_ed25519_key()
    binding = create_node_tpm_binding(
        node_id="node-test",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("A"),
        hardware_assurance_level="A",
        hardware_kind="physical_tpm",
        tpm_ek_cert_hash=_fake_ek_cert_hash(),
        tpm_kind="physical",
    )
    tampered = dataclasses.replace(binding, tpm_ek_cert_hash="a" * 64)
    result = verify_node_tpm_binding(tampered, expected_node_id="node-test")
    assert result.valid is False


def test_T14_certified_false_invariant():
    """T14 — certified=False absolu sur binding et résultat vérif."""
    binding = _create_binding_level("A")
    assert binding.certified is False
    result = verify_node_tpm_binding(binding, expected_node_id="node-test-A")
    assert result.certified is False


def test_T15_unique_human_proven_false_invariant():
    """T15 — unique_human_proven=False absolu sur binding."""
    for level in ("A", "B", "C", "D", "E"):
        binding = _create_binding_level(level)
        assert binding.unique_human_proven is False, f"Niveau {level} : unique_human_proven doit être False"


def test_T16_to_dict_round_trip():
    """T16 — to_dict() contient tous les champs attendus."""
    binding = _create_binding_level("A")
    d = binding.to_dict()
    required_keys = {
        "protocol", "node_id", "device_fingerprint",
        "hardware_assurance_level", "hardware_kind",
        "tpm_ek_cert_hash", "tpm_kind", "tpm_proven",
        "platform_system", "env_type", "nonce", "timestamp",
        "ed25519_public_key_hex", "ed25519_signature_hex",
        "mldsa65_public_key_hex", "mldsa65_signature_hex",
        "hybrid_and", "certified", "unique_human_proven", "note",
    }
    assert required_keys.issubset(d.keys()), f"Clés manquantes : {required_keys - d.keys()}"
    assert d["protocol"] == BINDING_PROTOCOL
    assert d["certified"] is False
    assert d["unique_human_proven"] is False


def test_T17_niveau_A_sans_ek_cert_tpm_proven_false():
    """T17 — Niveau A mais EK cert absent → tpm_proven=False (invariant)."""
    binding = _create_binding_level("A", with_ek=False)
    assert binding.tpm_proven is False
    assert binding.tpm_ek_cert_hash is None


def test_T18_require_tpm_proven_niveau_E_echec():
    """T18 — require_tpm_proven=True + niveau E → valid=False."""
    sk_bytes = _make_ed25519_key()
    binding = create_node_tpm_binding(
        node_id="node-software",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("E"),
        hardware_assurance_level="E",
        hardware_kind="software",
        tpm_ek_cert_hash=None,
        tpm_kind="absent",
    )
    result = verify_node_tpm_binding(
        binding,
        expected_node_id="node-software",
        require_tpm_proven=True,
    )
    assert result.valid is False
    assert result.failure_reason == "tpm_proven_required_not_satisfied"


def test_T19_require_tpm_proven_niveau_A_avec_ek_ok():
    """T19 — require_tpm_proven=True + niveau A + EK → valid=True."""
    sk_bytes = _make_ed25519_key()
    binding = create_node_tpm_binding(
        node_id="node-bare-metal",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("A"),
        hardware_assurance_level="A",
        hardware_kind="physical_tpm",
        tpm_ek_cert_hash=_fake_ek_cert_hash(),
        tpm_kind="physical",
    )
    result = verify_node_tpm_binding(
        binding,
        expected_node_id="node-bare-metal",
        require_tpm_proven=True,
    )
    assert result.valid is True
    assert result.tpm_proven is True


def test_T20_nonce_different_chaque_create():
    """T20 — Nonce différent à chaque appel (anti-rejeu)."""
    sk_bytes = _make_ed25519_key()
    b1 = create_node_tpm_binding(
        node_id="node-a",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("E"),
        hardware_assurance_level="E",
        hardware_kind="software",
        tpm_ek_cert_hash=None,
    )
    b2 = create_node_tpm_binding(
        node_id="node-a",
        ed25519_signing_key_bytes=sk_bytes,
        device_fingerprint=_fake_fingerprint("E"),
        hardware_assurance_level="E",
        hardware_kind="software",
        tpm_ek_cert_hash=None,
    )
    assert b1.nonce != b2.nonce


def test_T21_signature_ed25519_incorrecte():
    """T21 — Signature Ed25519 incorrecte (hex altéré) → valid=False."""
    import dataclasses
    binding = _create_binding_level("A")
    # Inverser le premier octet de la signature
    sig_bytes = bytes.fromhex(binding.ed25519_signature_hex)
    bad_sig = bytes([sig_bytes[0] ^ 0xFF]) + sig_bytes[1:]
    tampered = dataclasses.replace(binding, ed25519_signature_hex=bad_sig.hex())
    result = verify_node_tpm_binding(tampered, expected_node_id="node-test-A")
    assert result.valid is False
    assert result.ed25519_ok is False


def test_T22_binding_verification_result_to_dict():
    """T22 — BindingVerificationResult.to_dict() structure complète."""
    binding = _create_binding_level("A")
    result = verify_node_tpm_binding(binding, expected_node_id="node-test-A")
    d = result.to_dict()
    required_keys = {
        "valid", "node_id_match", "ed25519_ok", "mldsa65_ok",
        "hybrid_and_satisfied", "tpm_proven", "hardware_assurance_level",
        "failure_reason", "certified", "note",
    }
    assert required_keys.issubset(d.keys())
    assert d["certified"] is False
