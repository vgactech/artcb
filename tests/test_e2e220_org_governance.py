"""Phase 220 — public hash anchor + transferable ORG/GROUP authority.

User certification rules applied to organisations: human session only,
agents cannot transfer, unique_human_proven stays false, ORG_ID never
changes, Genesis body stays off the public chain.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artcb.authz.domains import REPLICATION_MATRIX
from artcb.wallet.manager import WalletManager
from api.main import create_app

TEST_PASSWORD = "monMotDePasse42!"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_NODE_ID", "node-paris")
    return TestClient(create_app())


def _user(name: str) -> dict:
    wallet = WalletManager().create_wallet(name=name, user_password=TEST_PASSWORD)
    return {"name": name, "address": wallet.address}


def _login(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_matrix_has_commitment_block_and_authority() -> None:
    assert REPLICATION_MATRIX["DOMAIN_COMMITMENT_BLOCK"]["content"] == "public_block_kind+id+hash_only"
    assert REPLICATION_MATRIX["ORG_AUTHORITY"]["content"] == "legal_owner+controller_not_genesis"
    assert REPLICATION_MATRIX["ORG_CONTROL_TRANSFER"]["content"] == "tx+subject+reason+old_new_controller_no_body"


def test_create_org_anchors_public_hash_not_body(client: TestClient) -> None:
    alice = _user("alice")
    h = _login(client, "alice")
    created = client.post("/api/v1/authz/orgs", json={"name": "ORG A"}, headers=h)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["actor_certification"]["unique_human_proven"] is False
    assert body["actor_certification"]["kind"] == "human"
    assert body["authority"]["controller_address"] == alice["address"]
    assert body["authority"]["legal_owner"] == alice["address"]
    assert body["authority"]["founder_address"] == alice["address"]
    assert body["domain"]["commitment_anchored_on_chain"] is True
    assert body["ownership"]["node_owns_domain"] is False

    chain = client.get("/api/v1/chain")
    assert chain.status_code == 200
    blocks = chain.json().get("blocks") or chain.json()
    if isinstance(chain.json(), dict) and "blocks" not in chain.json():
        # some deployments wrap differently
        blocks = chain.json() if isinstance(chain.json(), list) else chain.json().get("chain") or []
    public = [b for b in blocks if isinstance(b, dict) and b.get("visibility") == "public"]
    assert public
    commit_blocks = [b for b in public if (b.get("public_symbols") or {}).get("artcb_event") == "DOMAIN_COMMITMENT"]
    assert commit_blocks
    symbols = commit_blocks[-1]["public_symbols"]
    assert symbols["content_hash"] == body["content_hash"]
    assert symbols["contains_private_data"] == "false"
    assert symbols["unique_human_proven"] == "false"
    assert commit_blocks[-1].get("block_reward") in (0, None)
    blob = str(commit_blocks[-1])
    assert "members" not in blob
    assert "join_code" not in blob
    assert "genesis_body" not in blob


def test_agent_cannot_create_or_transfer_org(client: TestClient) -> None:
    alice = _user("alice")
    h = _login(client, "alice")
    headers = {**h, "x-artcb-agent-id": "agent-alice-01"}
    denied = client.post("/api/v1/authz/orgs", json={"name": "Nope"}, headers=headers)
    assert denied.status_code == 403

    human = client.post("/api/v1/authz/orgs", json={"name": "ORG A"}, headers=h)
    org_id = human.json()["organization_id"]
    xfer = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": "artcb1bobxxxxxxxx", "reason": "DIRECTOR_CHANGE"},
        headers=headers,
    )
    assert xfer.status_code == 403


def test_control_transfer_keeps_org_id_and_revokes_old(client: TestClient) -> None:
    alice = _user("alice")
    bob = _user("bob")
    h_a = _login(client, "alice")
    h_b = _login(client, "bob")
    created = client.post("/api/v1/authz/orgs", json={"name": "Entreprise XYZ"}, headers=h_a)
    org_id = created.json()["organization_id"]
    domain_id = created.json()["domain"]["domain_id"]
    genesis_hash = created.json()["content_hash"]

    spoof = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": alice["address"], "reason": "SALE"},
        headers=h_b,
    )
    assert spoof.status_code == 403

    proposed = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": bob["address"], "reason": "SALE"},
        headers=h_a,
    )
    assert proposed.status_code == 200, proposed.text
    tx_id = proposed.json()["tx_id"]
    assert proposed.json()["org_id_unchanged"] is True

    accepted = client.post("/api/v1/authz/transfers/accept", json={"tx_id": tx_id}, headers=h_b)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "finalized"
    assert accepted.json()["authority"]["controller_address"] == bob["address"]
    assert accepted.json()["authority"]["legal_owner"] == bob["address"]
    assert accepted.json()["authority"]["founder_address"] == alice["address"]
    assert accepted.json()["authority"]["subject_id"] == org_id
    assert accepted.json()["actor_certification"]["unique_human_proven"] is False

    auth = client.get(f"/api/v1/authz/orgs/{org_id}/authority")
    assert auth.json()["controller_address"] == bob["address"]
    assert auth.json()["founder_address"] == alice["address"]

    alice_export = client.post(f"/api/v1/authz/domains/{domain_id}/export", headers=h_a)
    assert alice_export.status_code == 403
    bob_export = client.post(f"/api/v1/authz/domains/{domain_id}/export", headers=h_b)
    assert bob_export.status_code == 200
    assert bob_export.json()["genesis_body"]["organization_id"] == org_id
    assert bob_export.json()["genesis_body"]["content_hash"] == genesis_hash


def test_director_change_keeps_legal_owner(client: TestClient) -> None:
    alice = _user("aline")
    bob = _user("directeur")
    h_a = _login(client, "aline")
    h_b = _login(client, "directeur")
    created = client.post("/api/v1/authz/orgs", json={"name": "Association ABC"}, headers=h_a)
    org_id = created.json()["organization_id"]
    proposed = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": bob["address"], "reason": "DIRECTOR_CHANGE"},
        headers=h_a,
    )
    client.post("/api/v1/authz/transfers/accept", json={"tx_id": proposed.json()["tx_id"]}, headers=h_b)
    auth = client.get(f"/api/v1/authz/orgs/{org_id}/authority").json()
    assert auth["legal_owner"] == alice["address"]
    assert auth["controller_address"] == bob["address"]
    assert auth["subject_id"] == org_id


def test_group_and_subgroup_transfer_do_not_move_org(client: TestClient) -> None:
    alice = _user("alice")
    bob = _user("bob")
    h_a = _login(client, "alice")
    h_b = _login(client, "bob")
    org = client.post("/api/v1/authz/orgs", json={"name": "ORG A"}, headers=h_a)
    org_id = org.json()["organization_id"]
    group = client.post(
        "/api/v1/groups",
        json={"name": "Engineering", "founder_address": alice["address"], "organization_id": org_id},
        headers=h_a,
    )
    assert group.status_code == 200, group.text
    gid = group.json()["group_id"]
    sub = client.post(
        f"/api/v1/groups/{gid}/subgroups",
        json={"name": "Platform"},
        headers=h_a,
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["ownership"]["transfers_parent_org"] is False
    assert sub.json()["parent_group_id"] == gid

    proposed = client.post(
        f"/api/v1/authz/groups/{gid}/transfer",
        json={"new_controller": bob["address"], "reason": "DIRECTOR_CHANGE"},
        headers=h_a,
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["parent_unchanged"] is True
    client.post("/api/v1/authz/transfers/accept", json={"tx_id": proposed.json()["tx_id"]}, headers=h_b)

    org_auth = client.get(f"/api/v1/authz/orgs/{org_id}/authority").json()
    assert org_auth["controller_address"] == alice["address"]
    group_auth = client.get(f"/api/v1/authz/orgs/{gid}/authority")
    # group authority lives on same store keyed by subject_id
    assert group_auth.status_code == 200
    assert group_auth.json()["controller_address"] == bob["address"]
    assert group_auth.json()["parent_id"] == org_id


def test_anonymous_and_non_controller_blocked(client: TestClient) -> None:
    _user("alice")
    assert client.post("/api/v1/authz/orgs", json={"name": "X"}).status_code == 401
    assert client.post("/api/v1/authz/orgs/org_x/transfer", json={"new_controller": "artcb1xxxxxxxx"}).status_code == 401


def test_succession_and_key_rotation_keep_legal_owner(client: TestClient) -> None:
    alice = _user("alice")
    heir = _user("heir")
    h_a = _login(client, "alice")
    h_h = _login(client, "heir")
    org_id = client.post("/api/v1/authz/orgs", json={"name": "Famille"}, headers=h_a).json()["organization_id"]
    for reason in ("SUCCESSION", "KEY_ROTATION"):
        proposed = client.post(
            f"/api/v1/authz/orgs/{org_id}/transfer",
            json={"new_controller": heir["address"], "reason": reason},
            headers=h_a,
        )
        assert proposed.status_code == 200, proposed.text
        accepted = client.post("/api/v1/authz/transfers/accept", json={"tx_id": proposed.json()["tx_id"]}, headers=h_h)
        assert accepted.status_code == 200, accepted.text
        auth = client.get(f"/api/v1/authz/orgs/{org_id}/authority").json()
        assert auth["legal_owner"] == alice["address"]
        assert auth["controller_address"] == heir["address"]
        # hand back to alice so the second reason still starts from the original controller
        back = client.post(
            f"/api/v1/authz/orgs/{org_id}/transfer",
            json={"new_controller": alice["address"], "reason": "DIRECTOR_CHANGE"},
            headers=h_h,
        )
        client.post("/api/v1/authz/transfers/accept", json={"tx_id": back.json()["tx_id"]}, headers=h_a)


def test_cancel_and_decline_keep_controller(client: TestClient) -> None:
    alice = _user("alice")
    bob = _user("bob")
    h_a = _login(client, "alice")
    h_b = _login(client, "bob")
    org_id = client.post("/api/v1/authz/orgs", json={"name": "Hold"}, headers=h_a).json()["organization_id"]
    proposed = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": bob["address"], "reason": "DIRECTOR_CHANGE"},
        headers=h_a,
    )
    cancelled = client.post("/api/v1/authz/transfers/cancel", json={"tx_id": proposed.json()["tx_id"]}, headers=h_a)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    listed = client.get(f"/api/v1/authz/transfers?subject_id={org_id}")
    assert listed.status_code == 200
    assert any(row["status"] == "cancelled" for row in listed.json()["transfers"])
    again = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": bob["address"], "reason": "DIRECTOR_CHANGE"},
        headers=h_a,
    )
    declined = client.post("/api/v1/authz/transfers/decline", json={"tx_id": again.json()["tx_id"]}, headers=h_b)
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"
    auth = client.get(f"/api/v1/authz/orgs/{org_id}/authority").json()
    assert auth["controller_address"] == alice["address"]


def test_old_controller_and_agents_lose_grants_after_sale(client: TestClient) -> None:
    alice = _user("alice")
    bob = _user("bob")
    h_a = _login(client, "alice")
    h_b = _login(client, "bob")
    created = client.post("/api/v1/authz/orgs", json={"name": "Vente"}, headers=h_a)
    org_id = created.json()["organization_id"]
    domain_id = created.json()["domain"]["domain_id"]
    grant = client.post(
        "/api/v1/authz/grants",
        headers=h_a,
        json={
            "subject": "agent-alice-01",
            "action": "READ",
            "subject_kind": "agent",
            "parent_subject": alice["address"],
            "resource": {"organization_id": org_id},
        },
    )
    assert grant.status_code == 200, grant.text
    proposed = client.post(
        f"/api/v1/authz/orgs/{org_id}/transfer",
        json={"new_controller": bob["address"], "reason": "SALE"},
        headers=h_a,
    )
    accepted = client.post("/api/v1/authz/transfers/accept", json={"tx_id": proposed.json()["tx_id"]}, headers=h_b)
    assert accepted.status_code == 200, accepted.text
    assert grant.json()["tx_id"] in accepted.json()["revoked_stale_grants"]
    chain = client.get("/api/v1/chain").json()
    blocks = chain.get("blocks") or chain
    xfer_blocks = [
        b
        for b in blocks
        if isinstance(b, dict) and (b.get("public_symbols") or {}).get("artcb_event") == "ORG_CONTROL_TRANSFER"
    ]
    assert xfer_blocks
    assert xfer_blocks[-1]["public_symbols"]["reason"] == "SALE"
    assert "genesis_body" not in str(xfer_blocks[-1])
    assert client.post(f"/api/v1/authz/domains/{domain_id}/export", headers=h_a).status_code == 403
    assert client.post(f"/api/v1/authz/domains/{domain_id}/export", headers=h_b).status_code == 200
