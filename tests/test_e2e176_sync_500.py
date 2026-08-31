"""Phase 176 — /p2p/sync must not HTTP 500 when a peer KEM key is the wrong size."""

from __future__ import annotations

from pathlib import Path

import pytest

from artcb.crypto.kem import KEMError, advertised_kem_algorithm, encrypt_payload
from artcb.p2p.node_identity import NodeIdentityStore
from artcb.p2p.peers import PeerRecord
from artcb.p2p.sync import P2PSyncError, P2PSyncService

ROOT = Path(__file__).resolve().parents[1]


def test_advertised_kem_algorithm_follows_key_size_not_slogan() -> None:
    assert advertised_kem_algorithm(b"\x00" * 32) == "X25519-fallback"
    assert advertised_kem_algorithm(b"\x11" * 1184) == "ML-KEM-768"
    assert advertised_kem_algorithm(b"\x22" * 8) == "unknown"


def test_encrypt_short_key_is_kemerror_not_runtimeerror() -> None:
    from artcb.crypto.kem import _oqs_available

    if not _oqs_available():
        pytest.skip("liboqs not available in this environment")
    with pytest.raises(KEMError) as exc:
        encrypt_payload(b"payload", b"\x00" * 32)
    assert "invalid_peer_kem_public_len:32" in str(exc.value)


def test_push_encrypt_failure_is_p2psyncerror_not_500() -> None:
    svc = object.__new__(P2PSyncService)
    svc.peers = type("P", (), {"update_peer_status": staticmethod(lambda *a, **k: None)})()
    svc.identity = type("I", (), {"network_id": "artcb-devnet-1", "node_id": "n", "kem_public_key_hex": "aa"})()
    svc.get_public_blocks = lambda **k: [{"index": 0, "visibility": "public"}]

    def boom(*_a, **_k):
        raise RuntimeError("Can not encapsulate secret")

    svc.build_encrypted_envelope = boom
    peer = PeerRecord(peer_id="aws3_stale", host="203.0.113.10", port=8000, kem_public_key_hex="00" * 32)
    with pytest.raises(P2PSyncError) as exc:
        svc.push_to_peer(peer)
    assert "push_encrypt_failed" in str(exc.value)


def test_sync_all_peers_keeps_successful_pull_when_push_fails() -> None:
    svc = object.__new__(P2PSyncService)
    peer = PeerRecord(peer_id="aws3_stale", host="203.0.113.10", port=8000, kem_public_key_hex="00" * 32)
    svc.peers = type("P", (), {"list_peers": staticmethod(lambda: [peer])})()
    svc.pull_from_peer = lambda *_a, **_k: {"received": 3, "imported": 3}

    def boom_push(*_a, **_k):
        raise P2PSyncError("push_encrypt_failed:KEMError")

    svc.push_to_peer = boom_push
    results = svc.sync_all_peers()
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["pull"]["received"] == 3
    assert results[0]["push_ok"] is False


def test_identity_store_upgrades_32byte_key_when_liboqs_present(tmp_path: Path) -> None:
    from artcb.crypto.liboqs_runtime import native_liboqs_available

    store = NodeIdentityStore(tmp_path)
    store.path.write_text(
        '{"network_id":"artcb-devnet-1","node_id":"artcb1test","kem_public_key_hex":"%s",'
        '"kem_secret_key_hex":"%s","api_port":8000,"p2p_port":18444}'
        % ("ab" * 32, "cd" * 32),
        encoding="utf-8",
    )
    ident = store.load_or_create(api_port=8000)
    if native_liboqs_available():
        assert len(bytes.fromhex(ident.kem_public_key_hex)) == 1184
    else:
        assert len(bytes.fromhex(ident.kem_public_key_hex)) == 32


def test_deploy_scripts_still_refuse_ovh1() -> None:
    body = (ROOT / "scripts" / "deploy_ovh4.sh").read_text(encoding="utf-8")
    assert "Refusing to deploy OVH4 script onto OVH1" in body
    aws = (ROOT / "scripts" / "deploy_aws.sh").read_text(encoding="utf-8")
    assert "152.228.144.34" in aws
