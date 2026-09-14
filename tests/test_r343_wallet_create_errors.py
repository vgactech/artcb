"""R343 — wallet create 409 codes: name collision ≠ device limit."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from src.artcb.security.hardware_identity import DeviceIdentity
from src.artcb.security.wallet_device_binding import WalletDeviceBindingStore


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    return TestClient(create_app())


def test_duplicate_name_returns_wallet_name_exists(client: TestClient) -> None:
    r1 = client.post("/api/v1/wallet/create", json={"name": "alice_r343", "password": "password123"})
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/v1/wallet/create", json={"name": "alice_r343", "password": "password123"})
    assert r2.status_code == 409
    detail = r2.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "wallet_name_exists"


def test_second_wallet_same_device_is_device_limit_not_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ARTCB_ALLOW_MULTI_WALLET", raising=False)
    monkeypatch.delenv("ARTCB_BOOTSTRAP_NODE", raising=False)
    app = create_app()
    store = WalletDeviceBindingStore(tmp_path / "data")
    app.state.wallet_device_binding = store
    app.state.device_identity = DeviceIdentity(
        device_fingerprint="f" * 64,
        machine_id="m",
        hostname="t",
        platform_system="Darwin",
        tpm_available=False,
        tpm_ek_cert_hash=None,
        tpm_manufacturer=None,
        env_type="local",
        created_at="2026-09-14T00:00:00Z",
    )
    client = TestClient(app)
    a = client.post("/api/v1/wallet/create", json={"name": "first_r343", "password": "password123"})
    assert a.status_code == 200, a.text
    b = client.post("/api/v1/wallet/create", json={"name": "second_r343", "password": "password123"})
    assert b.status_code == 409, b.text
    detail = b.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "device_wallet_limit"
