"""Phase 196 — D-034 hybrid AND + honest hardware tpm_type. No secrets. No fake TPM."""

from __future__ import annotations

from pathlib import Path

from nacl import signing

from api.main import REPLIT_CORS_ORIGIN_REGEX
from artcb.crypto.hybrid import (
    HYBRID_PREFIX,
    MLDSA65_PREFIX,
    is_ed25519_only_envelope,
    is_hybrid_envelope,
    is_mldsa_only_envelope,
    verify_hybrid,
    verify_hybrid_and,
)
from artcb.crypto_policy import (
    HIGH_VALUE_MESSAGES,
    HYBRID_VERIFY_MODE,
    public_health_block,
)
from artcb.devnet_validation import DECISIONS_174, DECISIONS_196, certification_gate, public_lock
from artcb.node_registry import NODES, SHARED_DOPPLER_PROJECT
from artcb.security.hardware_identity import (
    HARDWARE_ASSURANCE_LEVELS,
    attestation_nonce_schema,
    classify_hardware_assurance,
    new_attestation_nonce,
    nitro_attestation_facts,
    public_machine_view,
    tpm_sysfs_facts,
)

ROOT = Path(__file__).resolve().parents[1]


def _ed_pair() -> tuple[signing.SigningKey, bytes, bytes, str]:
    sk = signing.SigningKey.generate()
    msg = b"d034-and-196"
    ed_sig = sk.sign(msg).signature.hex()
    return sk, msg, sk.verify_key.encode(), ed_sig


def test_d034_and_d050_are_locked() -> None:
    assert DECISIONS_174["D-034"].startswith("A")
    assert HYBRID_VERIFY_MODE == "AND"
    assert "verify_hybrid_and" in DECISIONS_196["D-050"]
    assert "artcb-blockchain" in DECISIONS_196["D-050"]
    lock = public_lock()
    assert "decisions_196" in lock
    assert lock["distributed_certified"] is False
    gate = certification_gate(
        {k: "PASS" for k in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    assert gate["certified_distributed_mainnet"] is False


def test_and_refuses_ed25519_only() -> None:
    _sk, msg, pub, ed_sig = _ed_pair()
    alone = f"ed25519:{ed_sig}"
    assert is_ed25519_only_envelope(alone) is True
    assert is_hybrid_envelope(alone) is False
    assert (
        verify_hybrid_and(
            message=msg,
            signature_value=alone,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is False
    )
    assert (
        verify_hybrid(
            message=msg,
            signature_value=alone,
            ed25519_public_key=pub,
            pqc_public_key=b"",
            require_and=True,
        )
        is False
    )


def test_and_refuses_mldsa_only(monkeypatch) -> None:
    _sk, msg, pub, _ed = _ed_pair()
    monkeypatch.setattr("artcb.crypto.hybrid.verify_message", lambda *a, **k: True)
    alone = f"{MLDSA65_PREFIX}{'ab' * 32}"
    assert is_mldsa_only_envelope(alone) is True
    assert is_hybrid_envelope(alone) is False
    assert (
        verify_hybrid_and(
            message=msg,
            signature_value=alone,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is False
    )


def test_and_accepts_valid_hybrid_both_legs(monkeypatch) -> None:
    _sk, msg, pub, ed_sig = _ed_pair()
    monkeypatch.setattr("artcb.crypto.hybrid.verify_message", lambda *a, **k: True)
    envelope = f"{HYBRID_PREFIX}ed25519:{ed_sig}|mldsa65:{'cd' * 32}"
    assert is_hybrid_envelope(envelope) is True
    assert (
        verify_hybrid_and(
            message=msg,
            signature_value=envelope,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is True
    )


def test_and_refuses_broken_ed25519_leg(monkeypatch) -> None:
    _sk, msg, pub, _ed = _ed_pair()
    monkeypatch.setattr("artcb.crypto.hybrid.verify_message", lambda *a, **k: True)
    broken = f"{HYBRID_PREFIX}ed25519:{'00' * 64}|mldsa65:{'cd' * 32}"
    assert (
        verify_hybrid_and(
            message=msg,
            signature_value=broken,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is False
    )


def test_and_refuses_broken_mldsa_leg(monkeypatch) -> None:
    _sk, msg, pub, ed_sig = _ed_pair()
    monkeypatch.setattr("artcb.crypto.hybrid.verify_message", lambda *a, **k: False)
    broken = f"{HYBRID_PREFIX}ed25519:{ed_sig}|mldsa65:{'00' * 32}"
    assert (
        verify_hybrid_and(
            message=msg,
            signature_value=broken,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is False
    )


def test_honest_legacy_verify_hybrid_still_accepts_ed25519() -> None:
    """Ne pas mentir : verify_hybrid() sans require_and accepte encore Ed25519 seule.

    Le câblage des call sites (AND + fenêtre D-032) est dans 198.
    high_value_hybrid_enforced reste false tant que la fenêtre Ed25519 est ouverte.
    """
    _sk, msg, pub, ed_sig = _ed_pair()
    alone = f"ed25519:{ed_sig}"
    assert (
        verify_hybrid(
            message=msg,
            signature_value=alone,
            ed25519_public_key=pub,
            pqc_public_key=b"",
        )
        is True
    )
    health = public_health_block(True)
    assert health["high_value_hybrid_enforced"] is False
    assert health["legacy_verify_hybrid_still_accepts_ed25519_only"] is True
    assert health["hybrid_and_function"] == "verify_hybrid_and"
    assert "block_append" in HIGH_VALUE_MESSAGES


def test_tpm_type_physical_virtual_absent() -> None:
    physical = classify_hardware_assurance(tpm_device_present=True, chassis_virtual=False)
    assert physical["tpm_type"] == "physical"
    assert physical["tpm_kind"] == "physical"
    assert physical["hardware_assurance_level"] == "A"
    virtual = classify_hardware_assurance(tpm_device_present=True, chassis_virtual=True)
    assert virtual["tpm_type"] == "virtual"
    assert virtual["hardware_assurance_level"] == "B"
    absent = classify_hardware_assurance(tpm_device_present=False, chassis_virtual=True)
    assert absent["tpm_type"] == "absent"
    assert absent["hardware_assurance_level"] == "E"
    assert set(HARDWARE_ASSURANCE_LEVELS) == {"A", "B", "C", "D", "E"}


def test_attestation_false_without_tpm_or_nsm() -> None:
    facts = tpm_sysfs_facts()
    nitro = nitro_attestation_facts()
    view = public_machine_view(None)
    assert view["tpm_type"] in {"physical", "virtual", "absent"}
    assert view["tpm_type"] == view["tpm_kind"]
    assert "attestation_available" in view
    assert view["attestation_quote"] is None
    if not facts["tpm_device_present"]:
        assert view["tpm_type"] == "absent"
        assert view["attestation_available"] is False
        assert view["nitro_tpm"] is False
        assert nitro["invented"] is False
        assert nitro["quote"] is None
        assert nitro["attestation_available"] is False


def test_nonce_is_not_a_quote() -> None:
    schema = attestation_nonce_schema()
    assert schema["quote"] is None
    assert schema["quote_invented"] is False
    assert schema["nonce_hex"] is None
    nonce = new_attestation_nonce()
    assert nonce["quote"] is None
    assert nonce["quote_invented"] is False
    assert len(nonce["nonce_hex"]) == 64
    assert nonce["purpose"] == "future_tpm_quote"
    view = public_machine_view(None)
    assert view["attestation_nonce"]["quote"] is None
    assert view["attestation_nonce"]["nonce_hex"] is None


def test_cors_regex_has_no_named_replit_account() -> None:
    assert REPLIT_CORS_ORIGIN_REGEX == r"https://.*\.(replit\.app|repl\.co|replit\.dev)"
    main = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    cfg = (ROOT / "src" / "artcb" / "config.py").read_text(encoding="utf-8")
    assert "vgacofficiel.replit" not in main
    assert "vgac42371" not in main
    assert "vgacofficiel.replit" not in cfg
    assert "allow_origin_regex=REPLIT_CORS_ORIGIN_REGEX" in main
    assert "artcb--vgacofficiel" not in main


def test_ovh1_still_shares_artcb_blockchain_doppler() -> None:
    """Écart documenté : pas de projet Doppler inventé pour OVH1."""
    spec = NODES["ovh-node-1"]
    assert spec.doppler_project == SHARED_DOPPLER_PROJECT
    assert spec.doppler_project == "artcb-blockchain"
    assert "never created" in spec.public_notes
    assert "artcb-ovh-node-1 was never created" in spec.public_notes
    assert NODES["ovh-node-2"].doppler_project == "artcb-2"
    assert NODES["aws-node-3"].doppler_project == "artcb3"
    assert NODES["ovh-node-4"].doppler_project == "artcb-4"
