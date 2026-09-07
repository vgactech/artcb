"""T-E49 — ARTCB as a real auto-dev user (session + agent), not operator key."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.autodev.user import AutodevUser
from artcb.mcp.tools import TOOLS, execute_tool

TEST_PASSWORD = "monMotDePasse42!"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_NODE_ID", "node-autodev")
    monkeypatch.setenv("ARTCB_AUTODEV_PASSWORD", TEST_PASSWORD)
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    return TestClient(create_app())


def test_operator_key_is_not_a_user(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_API_KEY", "artcb_" + "ab" * 32)
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + "artcb_" + "ab" * 32})
    assert r.status_code == 200
    body = r.json()
    assert body["is_user"] is False
    assert body["is_operator"] is True
    assert body["address"] is None


def test_anonymous_whoami(client: TestClient) -> None:
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["kind"] == "anonymous"
    assert r.json()["is_user"] is False


def test_autodev_loop_login_record_whoami(client: TestClient) -> None:
    user = AutodevUser(password=TEST_PASSWORD, agent_id="cursor-autodev")
    ident = user.ensure_wallet()
    assert ident.address.startswith("artcb1")
    login = user.login(client)
    assert login["ok"] is True
    assert login["token_printed"] is False
    me = user.whoami(client)
    assert me["is_user"] is True
    assert me["kind"] == "agent"
    assert me["agent_id"] == "cursor-autodev"
    assert me["address"] == ident.address
    stored = user.record(client, content="Rapport 233: user auto-dev branché.", memo_type="decision")
    assert stored["memo_stored"] is True
    assert stored["principal_kind"] == "agent"
    assert stored["actor_address"] == ident.address
    assert stored["visibility"] == "private"


def test_agent_cannot_create_org(client: TestClient) -> None:
    user = AutodevUser(wallet_name="human-alice", password=TEST_PASSWORD, agent_id="evil-agent")
    user.ensure_wallet()
    user.login(client)
    created = client.post("/api/v1/authz/orgs", json={"name": "ORG AUTODEV"}, headers=user.headers())
    assert created.status_code == 403


def test_human_session_without_agent_header_can_create_org(client: TestClient) -> None:
    user = AutodevUser(wallet_name="human-bob", password=TEST_PASSWORD)
    user.ensure_wallet()
    user.login(client)
    human = {"Authorization": f"Bearer {user.session_token}"}
    created = client.post("/api/v1/authz/orgs", json={"name": "ORG BOB"}, headers=human)
    assert created.status_code == 200, created.text
    assert created.json()["actor_certification"]["kind"] == "human"
    assert created.json()["ownership"]["node_owns_domain"] is False


def test_public_record_forbidden_by_default(client: TestClient) -> None:
    user = AutodevUser(password=TEST_PASSWORD)
    user.ensure_wallet()
    user.login(client)
    with pytest.raises(RuntimeError, match="public_memo_forbidden"):
        user.record(client, content="ne pas publier", visibility="public")


def test_mcp_tools_include_autodev() -> None:
    names = {t["name"] for t in TOOLS}
    assert names >= {"artcb_whoami", "artcb_login", "artcb_autodev_record", "artcb_memo"}


def test_mcp_memo_sends_content_not_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_post(url: str, data: dict) -> dict:
        captured["url"] = url
        captured["data"] = data
        return {
            "block_index": 7,
            "pol_score": 0.75,
            "block_hash": "aa" * 16,
            "message": "ok",
            "principal_kind": "agent",
            "visibility": "private",
        }

    monkeypatch.setattr("artcb.mcp.tools._api_post", fake_post)
    execute_tool("artcb_memo", {"text": "hello"}, api_url="http://test:8000")
    assert "/ai/memo" in captured["url"]
    assert captured["data"]["content"] == "hello"
    assert captured["data"]["visibility"] == "private"
