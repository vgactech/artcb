"""R334-C — concept fan-out authz: replica peer-ingest closed without signature."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.artcb.memory.agent_channel import AgentChannel
from src.artcb.memory.concept_store import ConceptStore


def test_peer_ingest_rejects_missing_signature(tmp_path) -> None:
    client = TestClient(create_app())
    store = ConceptStore(tmp_path / "local")
    ch = AgentChannel(agent_id="t", store=store)
    learn = ch.learn_from_text("R334 peer ingest reject probe")
    bundle = ch.export_bundle(learn.concept_ids)
    r = client.post(
        "/api/v1/concepts/peer-ingest",
        content=bundle,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 401
    assert "peer_ingest_requires_replica_signature" in r.text


def test_peer_ingest_rejects_bad_signature(tmp_path) -> None:
    client = TestClient(create_app())
    store = ConceptStore(tmp_path / "local")
    ch = AgentChannel(agent_id="t", store=store)
    learn = ch.learn_from_text("R334 peer ingest bad sig")
    bundle = ch.export_bundle(learn.concept_ids)
    r = client.post(
        "/api/v1/concepts/peer-ingest",
        content=bundle,
        headers={
            "Content-Type": "application/octet-stream",
            "X-ARTCB-Replica-Id": "ovh-node-1",
            "X-ARTCB-Replica-Sig": "not-a-real-signature",
            "X-ARTCB-Concept-Ts-Ns": "1",
        },
    )
    assert r.status_code in (401, 403)


def test_fanout_requires_bearer(tmp_path) -> None:
    client = TestClient(create_app())
    r = client.post(
        "/api/v1/concepts/fanout",
        content=b"not-a-bundle",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 401


def test_peer_ingest_message_stable() -> None:
    from src.api.concept_routes import peer_ingest_message

    m = peer_ingest_message(sha="abc", from_replica_id="ovh-node-1", ts_ns=42)
    assert m == "concept-peer-ingest-v1|abc|ovh-node-1|42"
