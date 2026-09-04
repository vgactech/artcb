"""Group management API tests — request-to-join (Solution 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.wallet.manager import WalletManager

TEST_PASSWORD = "monMotDePasse42!"


@pytest.fixture
def wallets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ARTCB_DEBUG_DIRECT_MEMBER", raising=False)
    wm = WalletManager()
    return {
        "founder": wm.create_wallet(name="founder", user_password=TEST_PASSWORD),
        "admin": wm.create_wallet(name="admin", user_password=TEST_PASSWORD),
        "member": wm.create_wallet(name="member", user_password=TEST_PASSWORD),
        "other": wm.create_wallet(name="other", user_password=TEST_PASSWORD),
    }


@pytest.fixture
def client(wallets: dict) -> TestClient:
    return TestClient(create_app())


def _auth(client: TestClient, name: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def _create_group(client: TestClient, founder_address: str, name: str = "Projet LVX") -> dict:
    r = client.post(
        "/api/v1/groups",
        json={"name": name, "founder_address": founder_address},
        headers=_auth(client, "founder"),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _join_request(client: TestClient, join_code: str, wallet_name: str) -> dict:
    r = client.post(
        "/api/v1/groups/join-requests/sign-with-wallet",
        json={"join_code": join_code, "wallet_name": wallet_name, "wallet_password": TEST_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["request"]


def _approve(client: TestClient, group_id: str, actor_address: str, request_id: str, actor_name: str = "founder") -> None:
    r = client.post(
        f"/api/v1/groups/{group_id}/join-requests/{request_id}/approve",
        json={"actor_address": actor_address},
        headers=_auth(client, actor_name),
    )
    assert r.status_code == 200, r.text


def _add_member_via_join(client: TestClient, group: dict, wallet_name: str, approver: str) -> None:
    req = _join_request(client, group["join_code"], wallet_name)
    _approve(client, group["group_id"], approver, req["request_id"])


def test_create_group_has_join_code(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    assert group["founder_address"] == wallets["founder"].address
    assert group["members"][0]["role"] == "founder"
    assert len(group["join_code"]) == 8
    assert group["dissolved"] is False


def test_direct_invite_blocked_by_default(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    r = client.post(
        f"/api/v1/groups/{group['group_id']}/members",
        json={"actor_address": wallets["founder"].address, "address": wallets["member"].address},
        headers=_auth(client, "founder"),
    )
    assert r.status_code == 403
    assert "join-request" in r.json()["detail"]["message"].lower()


def test_join_request_flow(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    r_info = client.get(f"/api/v1/groups/by-code/{group['join_code']}")
    assert r_info.status_code == 200
    assert r_info.json()["name"] == "Projet LVX"
    assert "members" not in r_info.json()

    req = _join_request(client, group["join_code"], "member")
    assert req["status"] == "pending"
    assert req["address"] == wallets["member"].address

    pending = client.get(
        f"/api/v1/groups/{group['group_id']}/join-requests",
        params={"actor_address": wallets["founder"].address, "status": "pending"},
        headers=_auth(client, "founder"),
    )
    assert pending.json()["count"] == 1

    _approve(client, group["group_id"], wallets["founder"].address, req["request_id"])

    listed = client.get("/api/v1/groups", headers=_auth(client, "member"))
    assert listed.json()["count"] == 1


def test_founder_cannot_be_removed_by_admin(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    _add_member_via_join(client, group, "admin", wallets["founder"].address)
    client.post(
        f"/api/v1/groups/{group['group_id']}/members/{wallets['admin'].address}/role",
        json={"actor_address": wallets["founder"].address, "role": "admin"},
        headers=_auth(client, "founder"),
    )
    r = client.delete(
        f"/api/v1/groups/{group['group_id']}/members/{wallets['founder'].address}",
        params={"actor_address": wallets["admin"].address},
        headers=_auth(client, "admin"),
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "FOUNDER_IMMUTABLE"


def test_only_founder_promotes_admin(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    _add_member_via_join(client, group, "member", wallets["founder"].address)
    r = client.post(
        f"/api/v1/groups/{group['group_id']}/members/{wallets['member'].address}/role",
        json={"actor_address": wallets["founder"].address, "role": "admin"},
        headers=_auth(client, "founder"),
    )
    assert r.status_code == 200
    roles = {m["address"]: m["role"] for m in r.json()["members"]}
    assert roles[wallets["member"].address] == "admin"


def test_admin_cannot_promote_admin(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    _add_member_via_join(client, group, "admin", wallets["founder"].address)
    _add_member_via_join(client, group, "member", wallets["founder"].address)
    client.post(
        f"/api/v1/groups/{group['group_id']}/members/{wallets['admin'].address}/role",
        json={"actor_address": wallets["founder"].address, "role": "admin"},
        headers=_auth(client, "founder"),
    )
    r = client.post(
        f"/api/v1/groups/{group['group_id']}/members/{wallets['member'].address}/role",
        json={"actor_address": wallets["admin"].address, "role": "admin"},
        headers=_auth(client, "admin"),
    )
    assert r.status_code == 403


def test_dissolve_group_founder_only(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    _add_member_via_join(client, group, "admin", wallets["founder"].address)
    client.post(
        f"/api/v1/groups/{group['group_id']}/members/{wallets['admin'].address}/role",
        json={"actor_address": wallets["founder"].address, "role": "admin"},
        headers=_auth(client, "founder"),
    )
    r_admin = client.post(
        f"/api/v1/groups/{group['group_id']}/dissolve",
        json={"actor_address": wallets["admin"].address, "confirm": "DISSOLVE"},
        headers=_auth(client, "admin"),
    )
    assert r_admin.status_code == 403
    r_founder = client.post(
        f"/api/v1/groups/{group['group_id']}/dissolve",
        json={"actor_address": wallets["founder"].address, "confirm": "DISSOLVE"},
        headers=_auth(client, "founder"),
    )
    assert r_founder.status_code == 200
    assert r_founder.json()["dissolved"] is True


def test_reject_join_request(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    req = _join_request(client, group["join_code"], "member")
    r = client.post(
        f"/api/v1/groups/{group['group_id']}/join-requests/{req['request_id']}/reject",
        json={"actor_address": wallets["founder"].address},
        headers=_auth(client, "founder"),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    listed = client.get("/api/v1/groups", headers=_auth(client, "member"))
    assert listed.json()["count"] == 0


def test_store_group_visibility_and_chain_filter(client: TestClient, wallets: dict) -> None:
    group = _create_group(client, wallets["founder"].address)
    text = "Groupe test mémorisation bloc scoped."
    enc = client.post("/api/v1/encode", json={"text": text})
    graph_id = enc.json()["graph_id"]

    r_bad = client.post(
        "/api/v1/store",
        json={
            "graph_id": graph_id,
            "visibility": "group",
            "group_id": group["group_id"],
            "actor_address": wallets["other"].address,
        },
    )
    assert r_bad.status_code == 401

    r_spoof = client.post(
        "/api/v1/store",
        json={
            "graph_id": graph_id,
            "visibility": "group",
            "group_id": group["group_id"],
            "actor_address": wallets["founder"].address,
            "wallet_name": "other",
            "wallet_password": TEST_PASSWORD,
        },
    )
    assert r_spoof.status_code == 403

    r_ok = client.post(
        "/api/v1/store",
        json={
            "graph_id": graph_id,
            "visibility": "group",
            "group_id": group["group_id"],
            "wallet_name": "founder",
            "wallet_password": TEST_PASSWORD,
        },
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["group_id"] == group["group_id"]

    anon = client.get("/api/v1/chain", params={"group_id": group["group_id"]})
    assert anon.json()["count"] == 0
    chain_group = client.get(
        "/api/v1/chain",
        params={"group_id": group["group_id"]},
        headers=_auth(client, "founder"),
    )
    assert chain_group.json()["count"] == 1
