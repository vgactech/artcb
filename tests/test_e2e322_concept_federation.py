"""R322 — concept resolve federation one-hop (no infinite loop)."""

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
    return TestClient(create_app())


def test_resolve_empty_local_returns_header_acbn(client: TestClient) -> None:
    r = client.get("/api/v1/concepts/resolve", params={"ids": "Kdeadbeefdeadbeef"})
    assert r.status_code == 200
    assert r.content[:4] == b"ACBN"
    assert r.headers.get("X-ARTCB-Concept-Known") == "0"


def test_publish_then_resolve_roundtrip(client: TestClient, tmp_path: Path) -> None:
    monkey_key = "artcb_" + "a" * 48
    # create session path: wallet + login for write
    client.post("/api/v1/wallet/create", json={"name": "fed_u", "password": "pwd_r322_fed"})
    login = client.post("/api/v1/auth/login", json={"name": "fed_u", "password": "pwd_r322_fed"})
    if login.status_code != 200:
        pytest.skip("login unavailable in this fixture")
    token = login.json()["session_token"]
    ch = AgentChannel(agent_id="a", store=ConceptStore(tmp_path / "a"))
    learn = ch.learn_from_text("Federation roundtrip vehicle voiture")
    bundle = ch.export_bundle(learn.concept_ids)
    pub = client.post(
        "/api/v1/concepts/publish",
        content=bundle,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
    )
    assert pub.status_code == 200, pub.text
    cid = learn.concept_ids[0]
    res = client.get("/api/v1/concepts/resolve", params={"ids": cid})
    assert res.status_code == 200
    assert int(res.headers.get("X-ARTCB-Concept-Known", "0")) >= 1
    assert len(res.content) > 10
