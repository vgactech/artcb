"""FastAPI route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    app = create_app()
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "git_sha" in body
    assert "git_branch" in body


def test_encode_decode_roundtrip(client: TestClient) -> None:
    text = "Observer le monde pour apprendre."
    enc = client.post("/api/v1/encode", json={"text": text})
    assert enc.status_code == 200
    graph_id = enc.json()["graph_id"]
    dec = client.post("/api/v1/decode", json={"graph_id": graph_id})
    assert dec.status_code == 200
    assert dec.json()["reversible"] is True


def test_search_and_node(client: TestClient) -> None:
    text = "Nous avons décidé d'utiliser FastAPI. Le problème est la perte de contexte."
    enc = client.post("/api/v1/encode", json={"text": text})
    graph_id = enc.json()["graph_id"]
    search = client.post(
        "/api/v1/search",
        json={"query": "FastAPI", "graph_id": graph_id},
    )
    assert search.status_code == 200
    assert search.json()["count"] >= 1
    node_id = search.json()["results"][0]["node_id"]
    node = client.get(f"/api/v1/node/{node_id}", params={"graph_id": graph_id})
    assert node.status_code == 200


def test_agents_run_and_pol(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agents/run",
        json={"text": "Observer le monde pour apprendre."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pol"]["pol_score"] > 0
    pol = client.get("/api/v1/pol/score")
    assert pol.status_code == 200


def test_store_and_chain(client: TestClient) -> None:
    enc = client.post(
        "/api/v1/agents/run",
        json={"text": "Nous avons décidé d'utiliser FastAPI pour le backend."},
    )
    graph_id = enc.json()["graph_id"]
    store = client.post("/api/v1/store", json={"graph_id": graph_id})
    assert store.status_code == 200
    chain = client.get("/api/v1/chain")
    assert chain.json()["count"] == 1
    verify = client.get("/api/v1/chain/verify")
    assert verify.json()["valid"] is True


def test_rtleg_events(client: TestClient) -> None:
    client.post("/api/v1/encode", json={"text": "Test RT-LEG event."})
    events = client.get("/api/v1/rtleg/events")
    assert events.status_code == 200
    assert events.json()["count"] >= 1


def test_wailly_demo_excerpt(client: TestClient) -> None:
    response = client.get("/api/v1/demo/wailly-excerpt", params={"max_pages": 1})
    if response.status_code == 404:
        pytest.skip("Wailly PDF not available")
    assert response.status_code == 200
    body = response.json()
    assert body["char_count"] > 20
    assert "text" in body
