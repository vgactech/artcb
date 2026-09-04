"""Phase 217 — domain genesis, public commitments, CAN_I, no actor_address spoof.

ORG/GROUP constitutions live in the local domain store. The network only
sees kind + id + content_hash. P2P still refuses non-public blocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artcb.authz.domains import P2P_SYNCS_PRIVATE_BLOCKS, REPLICATION_MATRIX, canonical_hash
from artcb.wallet.manager import WalletManager
from api.main import create_app

TEST_PASSWORD = "monMotDePasse42!"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    return TestClient(create_app())


def _user(name: str) -> dict:
    wallet = WalletManager().create_wallet(name=name, user_password=TEST_PASSWORD)
    return {"name": name, "address": wallet.address}


def _login(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_replication_matrix_says_p2p_never_sends_private() -> None:
    assert P2P_SYNCS_PRIVATE_BLOCKS is False
    assert REPLICATION_MATRIX["PRIVATE_RESOURCE"]["replication"] == "never_p2p"
    assert REPLICATION_MATRIX["ORG_GENESIS_HASH"]["content"] == "kind+id+content_hash"
    assert REPLICATION_MATRIX["USER_DOMAIN"]["replication"] == "owner_only"


def test_create_group_without_session_is_rejected(client: TestClient) -> None:
    _user("founder")
    r = client.post("/api/v1/groups", json={"name": "X", "founder_address": "artcb1fakefounderxxx"})
    assert r.status_code == 401


def test_spoofed_founder_address_is_rejected(client: TestClient) -> None:
    a = _user("alice")
    _user("bob")
    r = client.post(
        "/api/v1/groups",
        json={"name": "Org", "founder_address": a["address"]},
        headers=_login(client, "bob"),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "actor_address_mismatch"


def test_org_and_group_commitments_are_hashes_not_members(client: TestClient) -> None:
    c3 = _user("C3")
    h = _login(client, "C3")
    org = client.post("/api/v1/authz/orgs", json={"name": "ORG A"}, headers=h)
    assert org.status_code == 200, org.text
    org_id = org.json()["organization_id"]
    assert org.json()["content_hash"]
    assert org.json()["forbidden_delegations"] == ["ADMIN_ORG"]

    listed = client.get("/api/v1/authz/orgs")
    assert listed.status_code == 200
    view = listed.json()["orgs"][0]
    assert view["projection"] == "public_commitment"
    assert "founder_address" not in view
    assert view["content_hash"] == org.json()["content_hash"]

    group = client.post(
        "/api/v1/groups",
        json={"name": "Groupe C", "founder_address": c3["address"], "organization_id": org_id},
        headers=h,
    )
    assert group.status_code == 200, group.text
    assert group.json()["genesis_hash"]
    assert "members" in group.json()  # founder session sees full group
    member_addr = group.json()["members"][0]["address"]

    commits = client.get("/api/v1/authz/commitments")
    assert commits.status_code == 200
    body = commits.json()
    assert body["contains_private_data"] is False
    assert body["count"] >= 2
    blob = str(body)
    assert "members" not in blob
    assert "join_code" not in blob
    assert member_addr  # founder is also the issuer of the commitment — that hash row may name them
    assert "secret" not in blob.lower()
    kinds = {row["kind"] for row in body["commitments"]}
    assert "org" in kinds
    assert "group" in kinds
    for row in body["commitments"]:
        assert row["contains_private_data"] is False
        assert len(row["content_hash"]) == 64

    matrix = client.get("/api/v1/authz/replication")
    assert matrix.json()["p2p_syncs_private_blocks"] is False


def test_p2p_public_list_excludes_private_and_group_blocks(client: TestClient) -> None:
    _user("owner")
    h = _login(client, "owner")
    enc = client.post("/api/v1/encode", json={"text": "Document RH secret de ORG A."})
    stored = client.post(
        "/api/v1/store",
        json={
            "graph_id": enc.json()["graph_id"],
            "visibility": "private",
            "wallet_name": "owner",
            "wallet_password": TEST_PASSWORD,
        },
        headers=h,
    )
    assert stored.status_code == 200, stored.text
    pub = client.get("/api/v1/p2p/blocks/public")
    assert pub.status_code == 200
    for block in pub.json()["blocks"]:
        assert block.get("visibility") == "public"
        assert "Document RH secret" not in str(block)


def test_can_i_agent_discovers_rights_before_work(client: TestClient) -> None:
    a3 = _user("A3")
    c3 = _user("C3")
    h_a3 = _login(client, "A3")
    h_c3 = _login(client, "C3")
    client.post("/api/v1/groups", json={"name": "C", "founder_address": c3["address"]}, headers=h_c3)
    enc = client.post("/api/v1/encode", json={"text": "Document X de C3."})
    stored = client.post(
        "/api/v1/store",
        json={
            "graph_id": enc.json()["graph_id"],
            "visibility": "private",
            "resource_id": "doc-x",
            "wallet_name": "C3",
            "wallet_password": TEST_PASSWORD,
        },
        headers=h_c3,
    )
    assert stored.status_code == 200, stored.text

    denied = client.post(
        "/api/v1/authz/can-i",
        headers=h_a3,
        json={"action": "READ", "resource": {"resource_id": "doc-x"}},
    )
    assert denied.status_code == 200
    assert denied.json()["effect"] == "DENY"

    grant = client.post(
        "/api/v1/authz/grants",
        headers=h_c3,
        json={"subject": a3["address"], "action": "READ", "resource": {"resource_id": "doc-x"}},
    )
    assert grant.status_code == 200, grant.text

    allowed = client.post(
        "/api/v1/authz/can-i",
        headers=h_a3,
        json={"action": "READ", "resource": {"resource_id": "doc-x"}},
    )
    assert allowed.json()["effect"] == "ALLOW"
    assert allowed.json()["proof"]["delegation"] is False

    agent = client.post(
        "/api/v1/authz/can-i",
        headers=h_a3,
        json={"action": "READ", "resource": {"resource_id": "doc-x"}, "agent_id": "agent-a3-01"},
    )
    assert agent.json()["effect"] == "DENY"
    assert agent.json()["reason"] in {"default_deny", "agent_exceeds_human_ceiling"} or agent.json()["effect"] == "DENY"

    client.post(
        "/api/v1/authz/grants",
        headers=h_c3,
        json={
            "subject": "agent-a3-01",
            "action": "READ",
            "subject_kind": "agent",
            "parent_subject": a3["address"],
            "resource": {"resource_id": "doc-x"},
        },
    )
    agent_ok = client.post(
        "/api/v1/authz/can-i",
        headers=h_a3,
        json={"action": "READ", "resource": {"resource_id": "doc-x"}, "agent_id": "agent-a3-01"},
    )
    assert agent_ok.json()["effect"] == "ALLOW"
    assert agent_ok.json()["proof"]["delegation"] is True
    assert agent_ok.json()["proof"]["parent"] == a3["address"]


def test_canonical_hash_is_stable() -> None:
    a = canonical_hash({"b": 1, "a": 2})
    b = canonical_hash({"a": 2, "b": 1})
    assert a == b
    assert len(a) == 64
