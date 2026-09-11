"""R319 — wallet balance authz (anon 401, session ownership, foreign address 403)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    monkeypatch.delenv("ARTCB_WALLET_BALANCE_PUBLIC", raising=False)
    return TestClient(create_app())


def _mk(client: TestClient, name: str, password: str = "pwd_r319_ok") -> tuple[str, str]:
    r = client.post("/api/v1/wallet/create", json={"name": name, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["address"], password


def _login(client: TestClient, name: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"name": name, "password": password})
    assert r.status_code == 200
    return r.json()["session_token"]


def test_balance_anon_401(client: TestClient) -> None:
    addr, _ = _mk(client, "anon_bal")
    assert client.get(f"/api/v1/wallet/balance/{addr}").status_code == 401
    assert client.post("/api/v1/wallet/balance", json={"address": addr}).status_code == 401


def test_balance_session_own_200(client: TestClient) -> None:
    addr, pwd = _mk(client, "own_bal")
    tok = _login(client, "own_bal", pwd)
    r = client.get(
        f"/api/v1/wallet/balance/{addr}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200


def test_balance_session_foreign_403(client: TestClient) -> None:
    addr_a, pwd_a = _mk(client, "sess_a")
    addr_b, _ = _mk(client, "sess_b")
    tok = _login(client, "sess_a", pwd_a)
    r = client.get(
        f"/api/v1/wallet/balance/{addr_b}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "wallet_balance_address_not_owned_by_session"
    # Own address still OK
    assert (
        client.get(
            f"/api/v1/wallet/balance/{addr_a}",
            headers={"Authorization": f"Bearer {tok}"},
        ).status_code
        == 200
    )


def test_session_ttl_config_is_1800() -> None:
    from api.auth_routes import _SESSION_TTL

    assert _SESSION_TTL == 1800
