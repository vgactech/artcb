"""Tests faucet devnet et chain explorer."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.devnet.faucet import DevnetFaucet, FaucetError


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    return TestClient(create_app())


def test_faucet_unit(tmp_path: Path) -> None:
    faucet = DevnetFaucet(tmp_path)
    result = faucet.request("artcb1testfaucetaddress00000001")
    assert result["amount_satoshi"] > 0
    assert faucet.total_for_address("artcb1testfaucetaddress00000001") > 0


def test_faucet_limit(tmp_path: Path) -> None:
    faucet = DevnetFaucet(tmp_path)
    addr = "artcb1testfaucetlimit000000002"
    for _ in range(3):
        faucet.request(addr)
    with pytest.raises(FaucetError):
        faucet.request(addr)


def test_faucet_api(client: TestClient) -> None:
    w = client.post("/api/v1/wallet/create", json={"name": "faucet_wallet", "password": "devpassword1"})
    assert w.status_code == 200
    address = w.json()["address"]
    r = client.post("/api/v1/devnet/faucet", json={"address": address})
    assert r.status_code == 403
    assert r.json()["detail"] == "faucet_disabled_on_mainnet"
    status = client.get("/api/v1/devnet/faucet/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False


def test_wallet_balance_includes_faucet(client: TestClient) -> None:
    w = client.post("/api/v1/wallet/create", json={"name": "bal_wallet", "password": "test_pwd_123"})
    address = w.json()["address"]
    denied = client.post("/api/v1/devnet/faucet", json={"address": address})
    assert denied.status_code == 403
    bal = client.get(f"/api/v1/wallet/balance/{address}")
    assert bal.status_code == 200
    assert int(bal.json().get("faucet_satoshi") or 0) == 0


def test_chain_explorer(client: TestClient) -> None:
    r = client.get("/api/v1/chain/explorer")
    assert r.status_code == 200
    body = r.json()
    assert body["network"] == "artcb-mainnet-1"
    assert "block_count" in body


def test_gradium_tts_fallback(client: TestClient) -> None:
    r = client.post("/api/v1/integrations/gradium/tts", json={"text": "Bonjour ARTCB"})
    assert r.status_code == 200
    assert r.json()["mode"] in ("fallback", "gradium")
