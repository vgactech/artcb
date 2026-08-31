"""Phase 174 — D-034 hybrid AND, DV-03 protocol match, signed capability. No secrets."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from artcb.consensus_spec import LIVE_BFT_IMPLEMENTED, public_spec
from artcb.crypto.hybrid import HYBRID_PREFIX, verify_hybrid
from artcb.crypto_policy import (
    GENESIS_HASH,
    HYBRID_VERIFY_MODE,
    NETWORK_ID,
    PROTOCOL_VERSION,
    accept_peer_protocol,
    accept_peer_suite,
)
from artcb.devnet_validation import DECISIONS_174, DV
from artcb.p2p.handshake import (
    CapabilityHistory,
    build_signed_card,
    kem_fingerprint,
    load_or_create_handshake_key,
    verify_signed_card,
)
from artcb.p2p.peers import PeerManager
from nacl import signing

ROOT = Path(__file__).resolve().parents[1]


def test_decisions_174_do_not_overwrite_d033_dv_profile() -> None:
    assert DV["DV-03"]["letter"] == "B"
    assert DECISIONS_174["D-034"].startswith("A")
    assert "3 live" in DECISIONS_174["D-035"]
    assert "OVH1" in DECISIONS_174["D-036"]
    assert HYBRID_VERIFY_MODE == "AND"
    assert PROTOCOL_VERSION == "174-devnet-1"
    spec = public_spec()
    assert spec["live_bft_implemented"] is False
    assert LIVE_BFT_IMPLEMENTED is False


def test_dv03_protocol_match_and_legacy_reject() -> None:
    ok, reason = accept_peer_protocol(
        advertised_network_id=NETWORK_ID,
        advertised_protocol_version=PROTOCOL_VERSION,
        advertised_genesis_hash=GENESIS_HASH,
    )
    assert ok is True
    ok2, reason2 = accept_peer_protocol(
        advertised_network_id=NETWORK_ID,
        advertised_protocol_version=None,
        advertised_genesis_hash=GENESIS_HASH,
    )
    assert ok2 is False
    assert "legacy" in reason2
    ok3, reason3 = accept_peer_protocol(
        advertised_network_id="other-net",
        advertised_protocol_version=PROTOCOL_VERSION,
        advertised_genesis_hash=GENESIS_HASH,
    )
    assert ok3 is False
    assert "network_id" in reason3


def test_hybrid_and_rejects_or_semantics() -> None:
    msg = b"dv07-and"
    sk = signing.SigningKey.generate()
    ed_sig = sk.sign(msg).signature.hex()
    fake_hybrid = f"{HYBRID_PREFIX}ed25519:{ed_sig}|mldsa65:{'00' * 32}"
    assert (
        verify_hybrid(
            message=msg,
            signature_value=fake_hybrid,
            ed25519_public_key=sk.verify_key.encode(),
            pqc_public_key=b"\x00" * 32,
        )
        is False
    )


def test_anti_downgrade_and_expiration() -> None:
    ok, _ = accept_peer_suite(
        advertised="Ed25519",
        previously_seen="hybrid:ed25519+ML-DSA-65",
        pqc_available_here=True,
        signed=True,
    )
    assert ok is False
    ok2, reason2 = accept_peer_suite(
        advertised="Ed25519",
        previously_seen=None,
        pqc_available_here=True,
        signed=False,
        now=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert ok2 is False
    assert "window_closed" in reason2
    ok3, reason3 = accept_peer_suite(
        advertised="hybrid:ed25519+ML-DSA-65",
        previously_seen=None,
        pqc_available_here=True,
        signed=False,
    )
    assert ok3 is True
    assert "unsigned" in reason3


def test_signed_capability_bound_to_kem_fingerprint(tmp_path: Path) -> None:
    key = load_or_create_handshake_key(tmp_path)
    kem = "ab" * 32
    card = build_signed_card(
        node_id="artcb1test",
        kem_public_key_hex=kem,
        crypto_suite="hybrid:ed25519+ML-DSA-65",
        protocol_version=PROTOCOL_VERSION,
        network_id=NETWORK_ID,
        genesis_hash=GENESIS_HASH,
        handshake=key,
    )
    ok, reason = verify_signed_card(card)
    assert ok is True
    tampered = dict(card)
    tampered["crypto_suite"] = "Ed25519"
    ok2, reason2 = verify_signed_card(tampered)
    assert ok2 is False
    hist = CapabilityHistory(tmp_path)
    fp = kem_fingerprint(kem)
    hist.remember_trusted(fp, suite="hybrid:ed25519+ML-DSA-65", node_id="artcb1test", signed=True)
    mgr = PeerManager(tmp_path)
    mgr.add_peer(
        host="203.0.113.9",
        port=8000,
        kem_public_key_hex=kem,
        crypto_suite="hybrid:ed25519+ML-DSA-65",
        network_id=NETWORK_ID,
        protocol_version=PROTOCOL_VERSION,
        genesis_hash=GENESIS_HASH,
        capability_card=card,
        peer_id="peer_bound",
    )
    try:
        mgr.add_peer(
            host="203.0.113.9",
            port=8000,
            kem_public_key_hex=kem,
            crypto_suite="Ed25519",
            peer_id="peer_bound",
        )
        raise AssertionError("downgrade must be rejected")
    except ValueError as exc:
        assert "anti_downgrade" in str(exc)


def test_deploy_scripts_still_refuse_ovh1() -> None:
    body = (ROOT / "scripts" / "deploy_ovh2.sh").read_text(encoding="utf-8")
    assert "Refusing to deploy OVH2 script onto OVH1" in body
    aws = (ROOT / "scripts" / "deploy_aws.sh").read_text(encoding="utf-8")
    assert "152.228.144.34 n'a PAS été modifié" in aws
