"""T-E50 — ORG node roles: HOST ≠ REPLICA ≠ CONSENSUS (rapport 236).

authorized_nodes is a declaration. A founder-signed certificate + node
key possession is the proof. Listing a node does not copy the Genesis BODY.
TRANSFER_OWNERSHIP stays human. This is not a private ORG BFT certification.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from api.main import create_app
from artcb.authz.domains import REPLICATION_MATRIX
from artcb.authz.node_cert import (
    NodeCertError,
    cert_allows,
    issue_node_certificate,
    node_possession_proof,
    verify_node_certificate,
    verify_node_possession,
)
from artcb.authz.node_roles import (
    CAP_HOST,
    CAP_PRODUCE,
    CAP_VALIDATE,
    HUMAN_ONLY,
    ROLE_CONSENSUS,
    ROLE_HOST_ONLY,
    can_role,
)
from artcb.wallet.manager import WalletManager

TEST_PASSWORD = "monMotDePasse42!"


def _boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, node_id: str) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / node_id / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / node_id / "logs"))
    monkeypatch.setenv("ARTCB_NODE_ID", node_id)
    return TestClient(create_app())


def _user(name: str) -> dict:
    wallet = WalletManager().create_wallet(name=name, user_password=TEST_PASSWORD)
    return {"name": name, "address": wallet.address, "wallet": WalletManager().load_wallet(name=name, user_password=TEST_PASSWORD)}


def _login(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_matrix_distinguishes_node_cert_from_authorized_list() -> None:
    assert REPLICATION_MATRIX["DOMAIN_BODY"]["replication"] == "org_domain_nodes"
    assert REPLICATION_MATRIX["NODE_AUTHORIZATION_CERT"]["content"].startswith("domain_id+node_id")
    assert "TRANSFER_OWNERSHIP" in HUMAN_ONLY
    assert can_role(ROLE_HOST_ONLY, CAP_HOST) is True
    assert can_role(ROLE_HOST_ONLY, CAP_PRODUCE) is False
    assert can_role(ROLE_CONSENSUS, CAP_PRODUCE) is True
    assert can_role(ROLE_CONSENSUS, "TRANSFER_OWNERSHIP") is False


def test_list_entry_is_not_a_certificate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    _user("alice")
    headers = _login(client, "alice")
    created = client.post("/api/v1/authz/orgs", json={"name": "ACME"}, headers=headers)
    domain_id = created.json()["domain"]["domain_id"]
    replica = client.post(
        f"/api/v1/authz/domains/{domain_id}/replicas",
        json={"node_id": "node-frankfurt", "role": "CONSENSUS"},
        headers=headers,
    )
    assert replica.status_code == 200
    assert replica.json()["body_copied"] is False
    assert replica.json()["certified"] is False
    view = client.get(f"/api/v1/authz/domains/{domain_id}/nodes/node-frankfurt").json()
    assert view["listed_on_authorized_nodes"] is True
    assert view["certified"] is False
    assert view["can_produce"] is False
    assert view["can_validate"] is False
    assert view["body_present"] is False


def test_founder_cert_plus_node_key_allows_consensus_not_body_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _boot(tmp_path, monkeypatch, "node-paris")
    alice = _user("alice")
    headers = _login(client, "alice")
    created = client.post("/api/v1/authz/orgs", json={"name": "ACME"}, headers=headers)
    domain_id = created.json()["domain"]["domain_id"]
    genesis_hash = created.json()["content_hash"]
    node_key = SigningKey.generate()
    issued = client.post(
        f"/api/v1/authz/domains/{domain_id}/node-certificates",
        json={
            "node_id": "node-frankfurt",
            "node_public_key_hex": node_key.verify_key.encode().hex(),
            "role": "CONSENSUS",
            "wallet_password": TEST_PASSWORD,
        },
        headers=headers,
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["body_copied"] is False
    assert issued.json()["certified"] is True
    view = client.get(f"/api/v1/authz/domains/{domain_id}/nodes/node-frankfurt").json()
    assert view["certified"] is True
    assert view["can_produce"] is True
    assert view["can_validate"] is True
    assert view["can_change_governance"] is False
    assert view["body_present"] is False

    cert = issue_node_certificate(
        alice["wallet"].signing_key,
        domain_id=domain_id,
        node_id="node-dublin",
        node_public_key_hex=node_key.verify_key.encode().hex(),
        role="CONSENSUS",
        founder_address=alice["address"],
        genesis_hash=genesis_hash,
    )
    proof = node_possession_proof(node_key, cert)
    verify_node_possession(cert, proof)
    stranger = SigningKey.generate()
    with pytest.raises(NodeCertError):
        verify_node_possession(cert, node_possession_proof(stranger, cert))


def test_forged_founder_signature_rejected() -> None:
    founder = SigningKey.generate()
    node = SigningKey.generate()
    cert = issue_node_certificate(
        founder,
        domain_id="domain_x",
        node_id="node-b",
        node_public_key_hex=node.verify_key.encode().hex(),
        role="CONSENSUS",
        founder_address="artcb1alice",
        genesis_hash="ab" * 32,
    )
    verify_node_certificate(cert, expected_domain_id="domain_x")
    cert["founder_signature"] = "00" * 64
    with pytest.raises(NodeCertError):
        verify_node_certificate(cert)
    assert cert_allows({**cert, "founder_signature": "00" * 64}, CAP_PRODUCE) is False


def test_host_only_never_produces() -> None:
    assert can_role("HOST_ONLY", CAP_PRODUCE) is False
    assert can_role("REPLICA", CAP_PRODUCE) is False
    assert can_role("REPLICA", CAP_VALIDATE) is False
    assert can_role("GOVERNANCE", "TRANSFER_OWNERSHIP") is False
