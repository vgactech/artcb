"""Tests GO-B — Pull P2P chiffré ML-KEM-768 + from_node_id lié à la clé.

Vérifie :
- pull_from_peer envoie X-ARTCB-KEM-Public-Key + X-ARTCB-Node-Id
- réponse chiffrée → déchiffrement correct + extraction blocks
- from_node_id issu de l'enveloppe (lié à la clé KEM du pair, pas auto-déclaré)
- fallback en clair si pair ancien (pas de header retourné)
- erreur de déchiffrement → P2PSyncError
- rétrocompatibilité : réponse sans "encrypted" → import direct
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from artcb.crypto.kem import encrypt_payload, generate_kem_keypair
from artcb.crypto_policy import NETWORK_ID
from artcb.p2p.node_identity import NodeIdentity
from artcb.p2p.peers import PeerRecord
from artcb.p2p.sync import P2PSyncError, P2PSyncService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_identity(suffix: str = "local") -> NodeIdentity:
    secret, public = generate_kem_keypair()
    return NodeIdentity(
        network_id=NETWORK_ID,
        node_id=f"artcb1node_{suffix}",
        kem_public_key_hex=public.hex(),
        kem_secret_key_hex=secret.hex(),
        api_port=8000,
        p2p_port=18444,
    )


def _make_peer(node_id: str, kem_public_hex: str) -> PeerRecord:
    return PeerRecord(
        peer_id=node_id,
        host="peer-host",
        port=8000,
        kem_public_key_hex=kem_public_hex,
    )


def _make_sync(identity: NodeIdentity) -> P2PSyncService:
    chain = MagicMock()
    chain.list_blocks.return_value = []
    chain.last_hash.return_value = "0" * 64
    chain._read_all_blocks.return_value = []
    chain.blocks_path = MagicMock()
    chain.blocks_path.parent.parent = MagicMock()

    peers = MagicMock()
    archive = MagicMock()
    archive.store_blocks.return_value = 0

    return P2PSyncService(
        chain=chain,
        peers=peers,
        identity=identity,
        archive=archive,
    )


def _make_encrypted_response(
    blocks: list[dict],
    responder_identity: NodeIdentity,
    requester_pk_hex: str,
) -> dict:
    """Simule ce que GET /p2p/blocks/public retourne quand le header KEM est présent."""
    payload = json.dumps({
        "blocks": blocks,
        "network_id": NETWORK_ID,
        "from_node_id": responder_identity.node_id,
        "from_kem_public_key_hex": responder_identity.kem_public_key_hex,
    }, ensure_ascii=False).encode("utf-8")
    peer_pk = bytes.fromhex(requester_pk_hex)
    envelope = encrypt_payload(payload, peer_pk)
    envelope["from_node_id"] = responder_identity.node_id
    envelope["requester_node_id"] = "requester_node"
    return {
        "envelope": envelope,
        "encrypted": True,
        "count": len(blocks),
        "from_index": 0,
    }


# ── Tests pull chiffré ────────────────────────────────────────────────────────

def test_pull_encrypted_sends_kem_header() -> None:
    """pull_from_peer doit envoyer X-ARTCB-KEM-Public-Key + X-ARTCB-Node-Id."""
    local = _make_identity("local")
    remote = _make_identity("remote")
    peer = _make_peer(remote.node_id, remote.kem_public_key_hex)
    svc = _make_sync(local)

    encrypted_resp = _make_encrypted_response([], remote, local.kem_public_key_hex)

    captured_headers: dict = {}

    def fake_get(url, *, params=None, headers=None, **_kw):
        nonlocal captured_headers
        captured_headers = dict(headers or {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = encrypted_resp
        return mock_resp

    with patch("artcb.p2p.sync.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = fake_get
        mock_client_cls.return_value = mock_client

        svc.pull_from_peer(peer)

    assert "X-ARTCB-KEM-Public-Key" in captured_headers
    assert captured_headers["X-ARTCB-KEM-Public-Key"] == local.kem_public_key_hex
    assert captured_headers.get("X-ARTCB-Node-Id") == local.node_id


def test_pull_encrypted_decrypts_blocks() -> None:
    """Réponse chiffrée → blocks extraits correctement après déchiffrement."""
    local = _make_identity("local")
    remote = _make_identity("remote")
    peer = _make_peer(remote.node_id, remote.kem_public_key_hex)
    svc = _make_sync(local)

    sample_block = {"index": 0, "visibility": "public", "hash": "abc"}
    encrypted_resp = _make_encrypted_response([sample_block], remote, local.kem_public_key_hex)

    def fake_get(url, *, params=None, headers=None, **_kw):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = encrypted_resp
        return mock_resp

    with patch("artcb.p2p.sync.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = fake_get
        mock_client_cls.return_value = mock_client

        result = svc.pull_from_peer(peer)

    assert result["received"] == 1
    assert result["encrypted"] is True


def test_pull_encrypted_from_node_id_from_envelope() -> None:
    """from_node_id issu de l'enveloppe (lié clé KEM) et non auto-déclaré par le pair."""
    local = _make_identity("local")
    remote = _make_identity("remote_real")
    peer = _make_peer("peer_declared_id", remote.kem_public_key_hex)
    svc = _make_sync(local)

    encrypted_resp = _make_encrypted_response([], remote, local.kem_public_key_hex)
    # from_node_id dans l'enveloppe = remote.node_id (différent du peer.peer_id déclaré)
    assert encrypted_resp["envelope"]["from_node_id"] == remote.node_id

    captured_from_node: list[str] = []

    def fake_import(blocks, *, from_node_id="unknown"):
        captured_from_node.append(from_node_id)
        return 0

    svc.import_public_blocks = fake_import  # type: ignore[method-assign]

    def fake_get(url, *, params=None, headers=None, **_kw):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = encrypted_resp
        return mock_resp

    with patch("artcb.p2p.sync.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = fake_get
        mock_client_cls.return_value = mock_client

        svc.pull_from_peer(peer)

    assert captured_from_node[0] == remote.node_id


def test_pull_cleartext_fallback_retrocompat() -> None:
    """Pair ancien : réponse sans 'encrypted' → import direct en clair."""
    local = _make_identity("local")
    remote = _make_identity("remote")
    peer = _make_peer(remote.node_id, remote.kem_public_key_hex)
    svc = _make_sync(local)

    cleartext_resp = {
        "blocks": [{"index": 0, "visibility": "public"}],
        "count": 1,
        "from_index": 0,
        "encrypted": False,
    }

    def fake_get(url, *, params=None, headers=None, **_kw):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = cleartext_resp
        return mock_resp

    with patch("artcb.p2p.sync.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = fake_get
        mock_client_cls.return_value = mock_client

        result = svc.pull_from_peer(peer)

    assert result["received"] == 1
    assert result["encrypted"] is False


def test_pull_decrypt_error_raises_p2p_sync_error() -> None:
    """Déchiffrement échoué → P2PSyncError (pas crash silencieux)."""
    local = _make_identity("local")
    remote = _make_identity("remote")
    peer = _make_peer(remote.node_id, remote.kem_public_key_hex)
    svc = _make_sync(local)

    # Enveloppe chiffrée pour une AUTRE clé — le local ne peut pas déchiffrer
    wrong_secret, wrong_public = generate_kem_keypair()
    fake_envelope = encrypt_payload(b'{"blocks":[]}', wrong_public)
    fake_envelope["from_node_id"] = remote.node_id

    bad_resp = {"envelope": fake_envelope, "encrypted": True, "count": 0}

    def fake_get(url, *, params=None, headers=None, **_kw):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = bad_resp
        return mock_resp

    with patch("artcb.p2p.sync.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = fake_get
        mock_client_cls.return_value = mock_client

        with pytest.raises(P2PSyncError, match="pull_decrypt_failed"):
            svc.pull_from_peer(peer)
