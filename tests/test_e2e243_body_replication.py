"""Tests GO-D — Réplication privée auto du BODY ORG.

Vérifie :
- Chiffrement du BODY pour un nœud cible (ML-KEM + AES-GCM)
- Déchiffrement et vérification canonical_hash
- Stockage local chmod 0600
- Erreur si nœud non autorisé
- Erreur si hash mismatch
- Erreur si BODY absent localement
- manifest.body_replicated = True après réception
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from artcb.authz.body_replication import (
    BodyReplicationService,
    BodyHashMismatch,
    BodyReplicationError,
)
from artcb.authz.registry import DomainRegistry, DomainManifest
from artcb.authz.domains import canonical_hash
from artcb.crypto.kem import MLKEM768_PUBLIC_BYTES, generate_kem_keypair
from artcb.p2p.node_identity import NodeIdentity
from artcb.crypto_policy import NETWORK_ID


def _make_identity(tmp_path: Path, suffix: str = "", *, require_mlkem: bool = False) -> NodeIdentity:
    secret, public = generate_kem_keypair()
    if require_mlkem and len(public) != MLKEM768_PUBLIC_BYTES:
        pytest.skip(
            "GO-D chiffrement exige ML-KEM-768 (1184 bytes). "
            "liboqs absent ici → generate_kem_keypair() retombe sur X25519 (32 bytes)."
        )
    return NodeIdentity(
        network_id=NETWORK_ID,
        node_id=f"artcb1node_{suffix}",
        kem_public_key_hex=public.hex(),
        kem_secret_key_hex=secret.hex(),
        api_port=8000,
        p2p_port=18444,
    )


def _make_registry(tmp_path: Path) -> DomainRegistry:
    return DomainRegistry(tmp_path / "registry.jsonl")


def _sample_body() -> dict:
    return {
        "org_name": "TestOrg",
        "founder": "artcb1alice",
        "rules": {"min_members": 1},
        "version": 1,
    }


def _make_manifest(domain_id: str, node_id: str, founder: str = "artcb1alice") -> DomainManifest:
    body = _sample_body()
    return DomainManifest(
        domain_id=domain_id,
        domain_type="ORG",
        subject_id="subj_test",
        founder_address=founder,
        genesis_hash=canonical_hash(body),
        hosting_node_id=node_id,
        authorized_nodes=[node_id],
    )


# ── Chiffrement / déchiffrement ───────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip(tmp_path: Path) -> None:
    """Chiffrement pour nœud A, déchiffrement par nœud A."""
    identity_a = _make_identity(tmp_path, "a", require_mlkem=True)
    registry = _make_registry(tmp_path)
    svc = BodyReplicationService(registry, identity_a, tmp_path)

    body = _sample_body()
    domain_id = "dom_test_001"
    envelope = svc.encrypt_body_for_node(domain_id, body, identity_a.kem_public_key_hex)
    assert envelope.get("body_replication") == "true"
    assert envelope.get("domain_id") == domain_id

    # Déchiffrement
    payload = svc.decrypt_body_envelope(envelope)
    assert payload["domain_id"] == domain_id
    assert payload["body"]["org_name"] == "TestOrg"
    assert payload["canonical_hash"] == canonical_hash(body)


def test_decrypt_wrong_key_fails(tmp_path: Path) -> None:
    """Un nœud avec une autre clé ne peut pas déchiffrer."""
    identity_a = _make_identity(tmp_path, "a", require_mlkem=True)
    identity_b = _make_identity(tmp_path, "b", require_mlkem=True)
    registry = _make_registry(tmp_path)
    svc_a = BodyReplicationService(registry, identity_a, tmp_path)
    svc_b = BodyReplicationService(registry, identity_b, tmp_path)

    body = _sample_body()
    # Chiffré pour A
    envelope = svc_a.encrypt_body_for_node("dom_001", body, identity_a.kem_public_key_hex)
    # B essaie de déchiffrer → erreur
    with pytest.raises(BodyReplicationError):
        svc_b.decrypt_body_envelope(envelope)


# ── Stockage local ────────────────────────────────────────────────────────────

def test_store_and_load_body(tmp_path: Path) -> None:
    identity = _make_identity(tmp_path, "x")
    registry = _make_registry(tmp_path)
    svc = BodyReplicationService(registry, identity, tmp_path)

    body = _sample_body()
    path = svc.store_body("dom_store", body)
    assert path.exists()
    assert oct(path.stat().st_mode)[-3:] == "600"  # chmod 0600

    loaded = svc.load_body("dom_store")
    assert loaded["org_name"] == "TestOrg"


def test_has_body(tmp_path: Path) -> None:
    identity = _make_identity(tmp_path, "x")
    registry = _make_registry(tmp_path)
    svc = BodyReplicationService(registry, identity, tmp_path)

    assert svc.has_body("dom_absent") is False
    svc.store_body("dom_present", _sample_body())
    assert svc.has_body("dom_present") is True


# ── Réception ────────────────────────────────────────────────────────────────

def test_receive_valid_body(tmp_path: Path) -> None:
    """Réception et stockage d'un BODY chiffré valide."""
    identity_sender = _make_identity(tmp_path / "sender", "sender", require_mlkem=True)
    identity_receiver = _make_identity(tmp_path / "receiver", "receiver", require_mlkem=True)
    registry = _make_registry(tmp_path)

    domain_id = "dom_receive"
    body = _sample_body()
    manifest = _make_manifest(domain_id, identity_receiver.node_id)
    registry._upsert(manifest)

    svc_sender = BodyReplicationService(registry, identity_sender, tmp_path / "sender_data")
    svc_receiver = BodyReplicationService(registry, identity_receiver, tmp_path / "receiver_data")

    # Sender chiffre pour receiver
    envelope = svc_sender.encrypt_body_for_node(
        domain_id, body, identity_receiver.kem_public_key_hex
    )

    # Receiver reçoit
    result = svc_receiver.receive_body_envelope(envelope)
    assert result["ok"] is True
    assert result["domain_id"] == domain_id
    assert result["body_replicated"] is True
    assert svc_receiver.has_body(domain_id)


def test_receive_hash_mismatch_raises(tmp_path: Path) -> None:
    """Si le hash reçu ne correspond pas → BodyHashMismatch."""
    identity = _make_identity(tmp_path, "x", require_mlkem=True)
    registry = _make_registry(tmp_path)
    svc = BodyReplicationService(registry, identity, tmp_path)

    # Crée une enveloppe avec un mauvais canonical_hash
    body = _sample_body()
    domain_id = "dom_hash_mismatch"
    payload = json.dumps({
        "domain_id": domain_id,
        "body": body,
        "canonical_hash": "wrong_hash_000000000000",  # hash incorrect
        "from_node_id": "attacker",
    }, ensure_ascii=False).encode()

    from artcb.crypto.kem import encrypt_payload
    envelope = encrypt_payload(payload, bytes.fromhex(identity.kem_public_key_hex))
    envelope["domain_id"] = domain_id
    envelope["from_node_id"] = "attacker"
    envelope["body_replication"] = "true"

    with pytest.raises(BodyHashMismatch):
        svc.receive_body_envelope(envelope)


def test_receive_not_authorized_raises(tmp_path: Path) -> None:
    """Si ce nœud n'est pas dans authorized_nodes → BodyReplicationError."""
    identity_sender = _make_identity(tmp_path / "s", "sender", require_mlkem=True)
    identity_receiver = _make_identity(tmp_path / "r", "receiver", require_mlkem=True)
    registry = _make_registry(tmp_path)

    domain_id = "dom_not_auth"
    body = _sample_body()
    # Manifest sans le receiver dans authorized_nodes
    manifest = _make_manifest(domain_id, "some_other_node")
    registry._upsert(manifest)

    svc_s = BodyReplicationService(registry, identity_sender, tmp_path / "s_data")
    svc_r = BodyReplicationService(registry, identity_receiver, tmp_path / "r_data")

    envelope = svc_s.encrypt_body_for_node(domain_id, body, identity_receiver.kem_public_key_hex)

    with pytest.raises(BodyReplicationError, match="authorized_nodes"):
        svc_r.receive_body_envelope(envelope)


def test_replicate_body_absent_raises(tmp_path: Path) -> None:
    """replicate_to_node échoue si le BODY n'existe pas localement."""
    identity = _make_identity(tmp_path, "src")
    registry = _make_registry(tmp_path)
    domain_id = "dom_no_body"
    manifest = _make_manifest(domain_id, identity.node_id)
    registry._upsert(manifest)

    svc = BodyReplicationService(registry, identity, tmp_path)
    target_secret, target_public = generate_kem_keypair()

    with pytest.raises(BodyReplicationError, match="introuvable"):
        svc.replicate_to_node(
            domain_id,
            "http://fake-target:8000",
            target_public.hex(),
            "artcb1alice",
        )
