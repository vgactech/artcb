"""Dashboard API integration tests — CDC v1.6 endpoints réels."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    logs.mkdir(parents=True)
    (data / "founders").mkdir(parents=True)
    founders_src = Path("data/founders/founders_allocation.json")
    if founders_src.is_file():
        shutil.copy(founders_src, data / "founders" / "founders_allocation.json")
    demo_src = Path("logs/demo_live_latest.txt")
    if demo_src.is_file():
        shutil.copy(demo_src, logs / "demo_live_latest.txt")
    for mining in sorted(Path("logs").glob("mining_results_*.json"), reverse=True)[:1]:
        shutil.copy(mining, logs / mining.name)
        break
    monkeypatch.setenv("ARTCB_DATA_DIR", str(data))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(logs))
    return TestClient(create_app())


def test_dashboard_demo_live_log(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard/logs/demo-live")
    assert r.status_code == 200
    assert r.json()["line_count"] > 0


def test_dashboard_mining_latest(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard/logs/mining-latest")
    assert r.status_code == 200
    assert "data" in r.json()


def test_dashboard_founders(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard/founders/allocation")
    if r.status_code == 404:
        pytest.skip("founders file not in test data dir")
    assert r.status_code == 200
    assert "balances" in r.json()


def test_dashboard_mining_status(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard/mining/status")
    assert r.status_code == 200
    data = r.json()
    assert data["current_reward_artcb"] == 50.0
    assert "blocks_until_halving" in data


def test_chain_block_detail(client: TestClient) -> None:
    text = "Bloc detail test phrase."
    enc = client.post("/api/v1/encode", json={"text": text})
    graph_id = enc.json()["graph_id"]
    store = client.post("/api/v1/store", json={"graph_id": graph_id})
    assert store.status_code == 200
    idx = store.json()["block_index"]
    r = client.get(f"/api/v1/chain/block/{idx}")
    assert r.status_code == 200
    assert r.json()["block"]["index"] == idx


def test_chain_filter_visibility(client: TestClient) -> None:
    r = client.get("/api/v1/chain", params={"visibility": "private"})
    assert r.status_code == 200
    assert "blocks" in r.json()
