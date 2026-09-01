"""Tests P2P devnet API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.crypto_policy import NETWORK_ID


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    return TestClient(create_app())


def test_p2p_status(client: TestClient) -> None:
    r = client.get("/api/v1/p2p/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["network_id"] == NETWORK_ID == "artcb-mainnet-1"
    assert body["kem_algorithm"] == "ML-KEM-768"
    assert "kem_public_key_hex" in body
    assert body["private_never_synced"] is True


def test_add_peer(client: TestClient) -> None:
    status = client.get("/api/v1/p2p/status").json()
    kem = status["kem_public_key_hex"]
    r = client.post(
        "/api/v1/p2p/peers",
        json={"host": "127.0.0.1", "port": 8001, "kem_public_key_hex": kem, "label": "test"},
    )
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/p2p/peers").json()["count"] == 1


def test_public_blocks_endpoint(client: TestClient) -> None:
    r = client.get("/api/v1/p2p/blocks/public")
    assert r.status_code == 200
    assert "blocks" in r.json()
