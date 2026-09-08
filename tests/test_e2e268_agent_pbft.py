"""R268 — prepared certificates, replay, agent protocol."""

from __future__ import annotations

import json
from pathlib import Path

from artcb.agent_runtime import AgentRuntime, PROTOCOL_VERSION, capabilities_for_scopes
from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import (
    PbftFinalityStore,
    verify_certificate,
    verify_commit,
    verify_prepared_certificate,
    verify_preprepare,
)
from artcb.consensus.pbft_view import primary_of
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS

ROOT = Path(__file__).resolve().parents[1]


def _cluster(tmp_path: Path):
    stores = {}
    chains = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        d = tmp_path / nid
        chain = ChainManager(d / "chain" / "blocks.jsonl", key_path=d / "k", enable_security=False)
        stores[nid] = PbftFinalityStore(d, replica_id=nid)
        chains[nid] = chain
    return stores, chains


def _prepare_only(stores, chains, graph_id: str = "p8"):
    primary = primary_of(0)
    block = json.loads(
        chains[primary]
        .append_block(graph_id=graph_id, graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid != primary:
            assert stores[nid].accept_preprepare(pp)["ok"] is True
    prepares = [
        stores[n].emit_prepare(chains[n], view=0, seq=int(block["index"]), digest=str(block["hash"]))
        for n in OFFICIAL_COMPUTE_NODE_IDS
    ]
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for p in prepares:
            if p["replica_id"] != nid:
                stores[nid].accept_prepare(p)
    return block, pp


def test_prepared_certificate_has_pp_and_q_prepares(tmp_path: Path) -> None:
    stores, chains = _cluster(tmp_path)
    block, _pp = _prepare_only(stores, chains)
    pset = stores[primary_of(0)].prepared_set()
    assert pset
    item = pset[0]
    assert verify_prepared_certificate(item) is True
    assert item["digest"] == block["hash"]
    assert len(item.get("replica_ids") or []) >= 3


def test_weak_pset_without_proofs_is_rejected(tmp_path: Path) -> None:
    stores, chains = _cluster(tmp_path)
    block, _pp = _prepare_only(stores, chains)
    primary = primary_of(0)
    weak = {
        "kind": "view-change-265",
        "protocol": "265-pbft-block-finality",
        "view": 1,
        "from_view": 0,
        "replica_id": primary,
        "prepared": [{"seq": 0, "digest": block["hash"], "view": 0}],
        "pset_digest": "",
        "message": "",
        "signature": "00",
        "producer_ed25519_b64": "",
        "producer_pqc_b64": "",
    }
    from artcb.consensus.pbft_finality import pset_digest

    weak["pset_digest"] = pset_digest(weak["prepared"])
    assert stores[primary].select_new_view_value([weak]) is None


def test_view_change_selects_verified_prepared(tmp_path: Path) -> None:
    stores, chains = _cluster(tmp_path)
    block, _pp = _prepare_only(stores, chains)
    majority = list(OFFICIAL_COMPUTE_NODE_IDS)[:3]
    vcs = [stores[n].emit_view_change_265(chains[n], view=1) for n in majority]
    chosen = stores[majority[1]].select_new_view_value(vcs)
    assert chosen is not None
    assert verify_prepared_certificate(chosen) is True
    assert chosen["digest"] == block["hash"]
    new_p = primary_of(1)

    class _View:
        view = 1

    stores[new_p].view_store = _View()
    bound = stores[new_p].bind_prepared_constraint(chosen)
    assert bound["ok"] is True
    evil = dict(block)
    evil["hash"] = "ab" * 32
    evil["index"] = int(chosen["seq"])
    try:
        stores[new_p].emit_preprepare(chains[new_p], block=evil)
        raised = ""
    except ValueError as exc:
        raised = str(exc)
    assert raised == "must_repropose_prepared", raised


def test_commit_replay_wrong_view_rejected(tmp_path: Path) -> None:
    stores, chains = _cluster(tmp_path)
    block, _pp = _prepare_only(stores, chains)
    primary = primary_of(0)
    emitted = stores[primary].emit_commit(chains[primary], view=0, seq=0, digest=block["hash"])
    commit = dict(emitted["commit"])
    commit["view"] = 6
    assert verify_commit(commit) is False
    other = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary][0]
    got = stores[other].accept_commit(commit)
    assert got.get("ok") is not True


def test_certificate_duplicate_replica_not_q(tmp_path: Path) -> None:
    stores, chains = _cluster(tmp_path)
    block, _pp = _prepare_only(stores, chains)
    primary = primary_of(0)
    c1 = stores[primary].emit_commit(chains[primary], view=0, seq=0, digest=block["hash"])["commit"]
    fake = {
        "protocol": "265-pbft-block-finality",
        "kind": "commit-certificate",
        "view": 0,
        "seq": 0,
        "digest": block["hash"],
        "q": 3,
        "commits": [c1, dict(c1), dict(c1)],
    }
    assert verify_certificate(fake) is False


def test_agent_runtime_idempotent_event(tmp_path: Path) -> None:
    rt = AgentRuntime(tmp_path)
    first = rt.commit_event(
        event_id="evt_test_268",
        agent_id="agent_cursor",
        kind="observation",
        content_sha256="ab" * 32,
        block_index=1,
        block_hash="cd" * 32,
        graph_id="g1",
    )
    second = rt.commit_event(
        event_id="evt_test_268",
        agent_id="agent_cursor",
        kind="observation",
        content_sha256="ab" * 32,
        block_index=99,
        block_hash="ff" * 32,
        graph_id="g2",
    )
    assert first["status"] == "committed"
    assert second["status"] == "already_committed"
    assert second["block_index"] == 1
    boot = rt.bootstrap({"agent_id": "agent_cursor", "scopes": ["read", "write"], "kind": "agent"})
    assert boot["protocol"] == PROTOCOL_VERSION
    assert boot["platform_hook"] is False
    assert "memory:write" in capabilities_for_scopes(["write"])
    assert boot["includes_thinking"] is False


def test_agent_events_http_idempotent_private(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-1")
    client = TestClient(create_app())
    body = {
        "event_id": "evt_unit_268_private",
        "kind": "observation",
        "content": "268 private unit event no-thinking",
        "visibility": "private",
        "tags": ["268", "unit"],
        "session_id": "268-unit",
    }
    first = client.post("/api/v1/agent/events", json=body)
    second = client.post("/api/v1/agent/events", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "committed"
    assert second.status_code == 200
    assert second.json()["status"] == "already_committed"
    assert second.json()["block_index"] == first.json()["memo"]["block_index"]


def test_agent_bootstrap_http(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-1")
    client = TestClient(create_app())
    r = client.get("/api/v1/agent/bootstrap")
    assert r.status_code == 200
    body = r.json()
    assert body["protocol"].startswith("268")
    assert body["ingest_platform_hook"] is False
    assert "artcb_agent_bootstrap" in body["mcp"]["tools"]
    reg = client.post("/api/v1/agent/register", json={"provider": "cursor", "label": "test", "capabilities": ["memory:read"]})
    assert reg.status_code == 200
    assert reg.json()["agent"]["provider"] == "cursor"
