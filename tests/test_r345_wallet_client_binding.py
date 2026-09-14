"""R345 — wallet create binds client FP, not server host DeviceIdentity."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ARTCB_ALLOW_MULTI_WALLET", raising=False)
    monkeypatch.delenv("ARTCB_BOOTSTRAP_NODE", raising=False)
    return TestClient(create_app())


def test_second_wallet_same_client_device_blocked(client: TestClient) -> None:
    headers = {"X-ARTCB-Device-Id": "browser-device-aaa", "User-Agent": "R345Test/1"}
    a = client.post(
        "/api/v1/wallet/create",
        json={"name": "first_r345", "password": "password123"},
        headers=headers,
    )
    assert a.status_code == 200, a.text
    b = client.post(
        "/api/v1/wallet/create",
        json={"name": "second_r345", "password": "password123"},
        headers=headers,
    )
    assert b.status_code == 409, b.text
    detail = b.json()["detail"]
    assert detail["code"] == "device_wallet_limit"
    assert detail.get("binding_scope") == "client"
    assert "first_r345" in detail["message"]


def test_different_client_devices_can_create(client: TestClient) -> None:
    a = client.post(
        "/api/v1/wallet/create",
        json={"name": "alice_r345", "password": "password123"},
        headers={"X-ARTCB-Device-Id": "dev-alice", "User-Agent": "R345Test/1"},
    )
    assert a.status_code == 200, a.text
    b = client.post(
        "/api/v1/wallet/create",
        json={"name": "bob_r345", "password": "password123"},
        headers={"X-ARTCB-Device-Id": "dev-bob", "User-Agent": "R345Test/1"},
    )
    assert b.status_code == 200, b.text
