"""Phase 198 — brancher verify_hybrid_and aux call sites chain/groups/governance.

AND = les DEUX signatures. Fenêtre Ed25519 D-032 B jusqu'au 2026-12-31.
Pas de secrets. Pas de faux TPM. certified reste false.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from nacl import encoding, signing

from api.main import REPLIT_CORS_ORIGIN_REGEX
from artcb.chain.manager import ChainManager
from artcb.crypto.hybrid import (
    HYBRID_PREFIX,
    MLDSA65_PREFIX,
    verify_hybrid_and,
    verify_hybrid_and_or_window,
)
from artcb.crypto_policy import ED25519_ONLY_UNTIL, public_health_block
from artcb.devnet_validation import DECISIONS_198, certification_gate, public_lock
from artcb.groups.signing import verify_join_signature
from artcb.wallet.address import address_from_public_key_bytes

ROOT = Path(__file__).resolve().parents[1]
FROZEN_TS = datetime(2026, 9, 2, 14, 30, 0, tzinfo=UTC)


def _ed_pair(msg: bytes = b"d034-and-198") -> tuple[signing.SigningKey, bytes, bytes, str]:
    sk = signing.SigningKey.generate()
    ed_sig = sk.sign(msg).signature.hex()
    return sk, msg, sk.verify_key.encode(), ed_sig


def _patch_mldsa_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    fn = lambda *a, **k: True
    monkeypatch.setattr("artcb.crypto.hybrid.verify_message", fn)
    monkeypatch.setattr("src.artcb.crypto.hybrid.verify_message", fn)


def _freeze_gov_now(monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_TS if tz is None else FROZEN_TS.astimezone(tz)

    monkeypatch.setattr("artcb.governance.manager.datetime", FrozenDateTime)
    monkeypatch.setattr("src.artcb.governance.manager.datetime", FrozenDateTime)


def test_d051_locked_and_certified_stays_false() -> None:
    assert "verify_hybrid_and" in DECISIONS_198["D-051"]
    assert "2026-12-31" in DECISIONS_198["D-051"]
    lock = public_lock()
    assert "decisions_198" in lock
    assert lock["distributed_certified"] is False
    gate = certification_gate(
        {k: "PASS" for k in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    assert gate["certified_distributed_mainnet"] is True
    assert gate["operator_certification_go"] is True


def test_call_sites_import_and_helper() -> None:
    chain = (ROOT / "src" / "artcb" / "chain" / "manager.py").read_text(encoding="utf-8")
    gov = (ROOT / "src" / "artcb" / "governance" / "manager.py").read_text(encoding="utf-8")
    groups = (ROOT / "src" / "artcb" / "groups" / "signing.py").read_text(encoding="utf-8")
    handshake = (ROOT / "src" / "artcb" / "p2p" / "handshake.py").read_text(encoding="utf-8")
    assert "verify_hybrid_and_or_window" in chain
    assert "verify_hybrid_and_or_window" in gov
    assert "verify_hybrid_and_or_window" in groups
    assert "verify_hybrid_and" in chain
    assert "verify_hybrid_and" in gov
    assert "verify_hybrid_and" in groups
    # Écart honnête : peer_handshake n'est pas dans ce câblage.
    assert "verify_hybrid_and" not in handshake
    assert "verify_ed25519" in handshake


def test_window_helper_and_refuses_one_leg(monkeypatch) -> None:
    _sk, msg, pub, ed_sig = _ed_pair()
    alone = f"ed25519:{ed_sig}"
    assert (
        verify_hybrid_and_or_window(
            message=msg,
            signature_value=alone,
            ed25519_public_key=pub,
            pqc_public_key=None,
        )
        is True
    )
    assert (
        verify_hybrid_and(
            message=msg,
            signature_value=alone,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is False
    )
    closed = datetime(2027, 1, 1, tzinfo=UTC)
    assert (
        verify_hybrid_and_or_window(
            message=msg,
            signature_value=alone,
            ed25519_public_key=pub,
            pqc_public_key=None,
            now=closed,
        )
        is False
    )
    assert ED25519_ONLY_UNTIL.startswith("2026-12-31")

    _patch_mldsa_ok(monkeypatch)
    mldsa_only = f"{MLDSA65_PREFIX}{'ab' * 32}"
    assert (
        verify_hybrid_and_or_window(
            message=msg,
            signature_value=mldsa_only,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is False
    )
    envelope = f"{HYBRID_PREFIX}ed25519:{ed_sig}|mldsa65:{'cd' * 32}"
    assert (
        verify_hybrid_and_or_window(
            message=msg,
            signature_value=envelope,
            ed25519_public_key=pub,
            pqc_public_key=None,
        )
        is False
    )
    assert (
        verify_hybrid_and_or_window(
            message=msg,
            signature_value=envelope,
            ed25519_public_key=pub,
            pqc_public_key=b"\x01" * 32,
        )
        is True
    )


def test_chain_verify_block_signature_window_and_hybrid(tmp_path, monkeypatch) -> None:
    blocks = tmp_path / "blocks.jsonl"
    key = tmp_path / "chain.key"
    cm = ChainManager(blocks, key_path=key, enable_security=False)
    block_hash = "ab" * 32
    message = block_hash.encode("utf-8")
    ed_only = f"ed25519:{cm._signing_key.sign(message).signature.hex()}"
    assert cm.verify_block_signature(block_hash, ed_only) is True
    own = cm._sign_block(block_hash)
    assert cm.verify_block_signature(block_hash, own) is True

    _patch_mldsa_ok(monkeypatch)
    envelope = (
        f"{HYBRID_PREFIX}ed25519:{cm._signing_key.sign(message).signature.hex()}"
        f"|mldsa65:{'cd' * 32}"
    )
    if cm._pqc_public_key:
        assert cm.verify_block_signature(block_hash, envelope) is True
    else:
        assert cm.verify_block_signature(block_hash, envelope) is False


def test_groups_join_ed25519_and_hybrid_and(monkeypatch) -> None:
    _sk, msg, pub, ed_sig = _ed_pair(b"ARTCB-JOIN-198")
    addr = address_from_public_key_bytes(pub)
    assert (
        verify_join_signature(
            public_key_hex=pub.hex(),
            address=addr,
            signature_hex=ed_sig,
            message=msg,
        )
        is True
    )
    envelope = f"{HYBRID_PREFIX}ed25519:{ed_sig}|mldsa65:{'cd' * 32}"
    assert (
        verify_join_signature(
            public_key_hex=pub.hex(),
            address=addr,
            signature_hex=envelope,
            message=msg,
        )
        is False
    )
    _patch_mldsa_ok(monkeypatch)
    assert (
        verify_join_signature(
            public_key_hex=pub.hex(),
            address=addr,
            signature_hex=envelope,
            message=msg,
            pqc_public_key_hex="01" * 32,
        )
        is True
    )


def test_governance_ed25519_window_hybrid_needs_pqc(tmp_path, monkeypatch) -> None:
    from artcb.governance.manager import GovernanceError, GovernanceManager

    _freeze_gov_now(monkeypatch)
    gm = GovernanceManager(data_dir=tmp_path)
    sk = signing.SigningKey.generate()
    old_addr = sk.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii")
    new_addr = signing.SigningKey.generate().verify_key.encode(
        encoder=encoding.Base64Encoder
    ).decode("ascii")
    now_str = FROZEN_TS.strftime("%Y-%m-%dT%H:%M:%SZ")
    message = f"{old_addr}:{new_addr}:{now_str}".encode("utf-8")
    ed_sig = f"ed25519:{sk.sign(message).signature.hex()}"
    result = gm.user_key_rotation(
        old_address=old_addr,
        new_address=new_addr,
        signature_hex=ed_sig,
    )
    assert result["sig_status"] == "verified"
    assert result["sig_format"] == "ed25519"

    sk2 = signing.SigningKey.generate()
    old2 = sk2.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii")
    new2 = signing.SigningKey.generate().verify_key.encode(
        encoder=encoding.Base64Encoder
    ).decode("ascii")
    msg2 = f"{old2}:{new2}:{now_str}".encode("utf-8")
    hybrid_sig = f"{HYBRID_PREFIX}ed25519:{sk2.sign(msg2).signature.hex()}|mldsa65:{'aa' * 32}"
    with pytest.raises(GovernanceError, match="signature invalide"):
        gm.user_key_rotation(
            old_address=old2,
            new_address=new2,
            signature_hex=hybrid_sig,
        )
    _patch_mldsa_ok(monkeypatch)
    ok = gm.user_key_rotation(
        old_address=old2,
        new_address=new2,
        signature_hex=hybrid_sig,
        pqc_public_key_hex="01" * 32,
    )
    assert ok["sig_status"] == "verified"
    assert ok["sig_format"] == "hybrid:ed25519+ML-DSA-65"


def test_health_wired_but_not_enforced_high_value() -> None:
    health = public_health_block(True)
    assert health["hybrid_and_call_sites_wired"] is True
    assert health["high_value_hybrid_enforced"] is False
    assert health["ed25519_only_still_accepted"] is True
    assert health["hybrid_and_function"] == "verify_hybrid_and"


def test_cors_regex_has_no_named_replit_account() -> None:
    assert REPLIT_CORS_ORIGIN_REGEX == r"https://.*\.(replit\.app|repl\.co|replit\.dev)"
    main = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    cfg = (ROOT / "src" / "artcb" / "config.py").read_text(encoding="utf-8")
    assert "vgacofficiel.replit" not in main
    assert "vgac42371" not in main
    assert "vgacofficiel.replit" not in cfg
    assert "artcb--vgacofficiel" not in main
