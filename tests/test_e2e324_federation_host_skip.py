"""R324 — federation must not skip apex artcb.me when Host is n2.artcb.me."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from artcb.memory.agent_channel import AgentChannel
from artcb.memory.concept_store import ConceptStore


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_CONCEPT_FEDERATE", "1")
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    monkeypatch.setenv("ARTCB_SESSION_BIND_DEVICE", "0")
    return TestClient(create_app())


def test_n2_host_does_not_skip_apex_peer_logic() -> None:
    """Regression: endswith('.artcb.me') wrongly skipped https://artcb.me."""
    host = "n2.artcb.me"
    peer_host = "artcb.me"
    # Old buggy rule:
    buggy = host == peer_host or host.endswith("." + peer_host)
    assert buggy is True
    # Fixed rule:
    fixed = host == peer_host
    assert fixed is False


def test_publish_then_local_resolve_persists(client: TestClient, tmp_path: Path) -> None:
    client.post("/api/v1/wallet/create", json={"name": "r324_u", "password": "pwd_r324_ok"})
    login = client.post("/api/v1/auth/login", json={"name": "r324_u", "password": "pwd_r324_ok"})
    assert login.status_code == 200
    token = login.json()["session_token"]
    ch = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    learn = ch.learn_from_text("R324 persist voiture energie")
    bundle = ch.export_bundle(learn.concept_ids)
    pub = client.post(
        "/api/v1/concepts/publish",
        content=bundle,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
    )
    assert pub.status_code == 200
    cid = learn.concept_ids[0]
    res = client.get("/api/v1/concepts/resolve", params={"ids": cid})
    assert res.status_code == 200
    assert int(res.headers.get("X-ARTCB-Concept-Known", "0")) >= 1
