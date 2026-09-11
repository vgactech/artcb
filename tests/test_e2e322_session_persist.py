"""R322 — session persistence across process memory clear (disk store)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import auth_routes, session_store
from api.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    monkeypatch.setenv("ARTCB_SESSION_BIND_DEVICE", "0")
    auth_routes._sessions.clear()
    session_store.reset_for_tests()
    return TestClient(create_app())


def test_session_survives_memory_clear(client: TestClient) -> None:
    w = client.post("/api/v1/wallet/create", json={"name": "persist_u", "password": "pwd_r322_ok"})
    assert w.status_code == 200
    login = client.post("/api/v1/auth/login", json={"name": "persist_u", "password": "pwd_r322_ok"})
    assert login.status_code == 200
    token = login.json()["session_token"]
    path = Path(os.environ["ARTCB_DATA_DIR"]) / "auth" / "sessions.json"
    assert path.is_file()
    # Simulate process restart: wipe in-memory dict + reload flag
    auth_routes._sessions.clear()
    session_store.reset_for_tests()
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json().get("authenticated") is True


def test_logout_removes_disk_session(client: TestClient) -> None:
    client.post("/api/v1/wallet/create", json={"name": "logout_u", "password": "pwd_r322_ok"})
    login = client.post("/api/v1/auth/login", json={"name": "logout_u", "password": "pwd_r322_ok"})
    token = login.json()["session_token"]
    assert (
        client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )
    auth_routes._sessions.clear()
    session_store.reset_for_tests()
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401
    assert me.json().get("detail")
