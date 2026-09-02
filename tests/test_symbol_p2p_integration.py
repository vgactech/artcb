"""Tests integration symboles publics + P2P + blockchain."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
    return TestClient(create_app())


def test_public_block_carries_symbols(client: TestClient) -> None:
    agents = client.post(
        "/api/v1/agents/run",
        json={
            "text": "The flarnick zorbax process requires careful observation today.",
            "session_id": "sym_pub",
        },
    )
    assert agents.status_code == 200
    assert agents.json().get("orig_symbols")
    graph_id = agents.json()["graph_id"]
    # Wallet système — password requis depuis rapport 107 (chiffrement clé privée)
    w = client.post("/api/v1/wallet/create", json={"name": "sym_wallet", "password": "test_pwd_123"})
    address = w.json()["address"]
    store = client.post(
        "/api/v1/store",
        json={
            "graph_id": graph_id,
            "session_id": "sym_pub",
            "visibility": "public",
            "wallet_name": "sym_wallet",
            "wallet_password": "test_pwd_123",
            "actor_address": address,
        },
    )
    assert store.status_code == 200
    explorer = client.get("/api/v1/chain/explorer")
    latest = explorer.json()["latest_blocks"]
    public = [b for b in latest if b.get("visibility") == "public"]
    assert public
    symbols = public[-1].get("public_symbols") or {}
    assert len(symbols) > 0


def test_symbol_publish_and_registry(client: TestClient) -> None:
    pub = client.post(
        "/api/v1/symbols/publish",
        json={"symbols": {"testkey|abc": "gamma1"}, "graph_id": "g_test"},
    )
    assert pub.status_code == 200
    reg = client.get("/api/v1/symbols/registry")
    assert reg.json()["count"] >= 1


def test_p2p_symbols_endpoints(client: TestClient) -> None:
    r = client.get("/api/v1/p2p/symbols/public")
    assert r.status_code == 200
    assert "symbols" in r.json()


def test_gossip_announce(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_API_KEY", "artcb_local_test_operator_key")
    r = client.post("/api/v1/p2p/gossip/announce")
    assert r.status_code == 401
    r2 = client.post(
        "/api/v1/p2p/gossip/announce",
        headers={"Authorization": "Bearer artcb_local_test_operator_key"},
    )
    assert r2.status_code == 200
    assert r2.json()["announcement"]["node_id"]
    listed = client.get("/api/v1/p2p/gossip/announcements")
    assert listed.json()["announcements"]
