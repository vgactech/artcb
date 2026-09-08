"""R269 — P9…P18 campaign: mutation, binding, Byzantine PREPARE, replay, agent, storage."""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path

from artcb.agent_runtime import AgentRuntime, capabilities_for_scopes
from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import (
    PbftFinalityStore,
    verify_certificate,
    verify_prepared_certificate,
)
from artcb.consensus.pbft_view import PbftViewStore, primary_of
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS

ROOT = Path(__file__).resolve().parents[1]


def _cluster(tmp_path: Path):
    stores, chains, views = {}, {}, {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        d = tmp_path / nid
        chain = ChainManager(d / "chain" / "blocks.jsonl", key_path=d / "k", enable_security=False)
        vs = PbftViewStore(d, replica_id=nid)
        stores[nid] = PbftFinalityStore(d, replica_id=nid, view_store=vs)
        chains[nid] = chain
        views[nid] = vs
    return stores, chains, views


def _round(stores, chains, *, graph_id: str = "p9"):
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
    cert = None
    commits = []
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        emitted = stores[nid].emit_commit(chains[nid], view=0, seq=int(block["index"]), digest=str(block["hash"]))
        commits.append(emitted["commit"])
        if emitted.get("certificate"):
            cert = emitted["certificate"]
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for c in commits:
            if c["replica_id"] != nid:
                got = stores[nid].accept_commit(c)
                if got.get("certificate"):
                    cert = got["certificate"]
    assert cert is not None
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        assert chains[nid].write_certified_block(block, cert) is True
    return block, cert


def _mutate(cert: dict, kind: str) -> dict:
    row = copy.deepcopy(cert)
    commits = list(row.get("commits") or [])
    if kind == "view":
        row["view"] = int(row.get("view") or 0) + 7
    elif kind == "seq":
        row["seq"] = int(row.get("seq") or 0) + 99
    elif kind == "digest":
        row["digest"] = "ab" * 32
    elif kind == "replica_id_all" and commits:
        row["commits"] = [dict(c, replica_id="evil-node") for c in commits]
    elif kind == "signature_all" and commits:
        row["commits"] = [dict(c, signature="00" * 32) for c in commits]
    elif kind == "drop_commit" and commits:
        row["commits"] = commits[:1]
    elif kind == "dup_commit" and commits:
        row["commits"] = [commits[0], dict(commits[0]), dict(commits[0])]
    elif kind == "pubkey_all" and commits:
        row["commits"] = [dict(c, producer_ed25519_b64="AAAA") for c in commits]
    elif kind == "mix_digest" and len(commits) >= 3:
        row["commits"] = [dict(c, digest="cd" * 32) for c in commits]
    elif kind == "header_seq_keep_commits":
        row["seq"] = 999
    return row


def test_p9_certificate_mutations_all_rejected(tmp_path: Path) -> None:
    stores, chains, _ = _cluster(tmp_path)
    _block, cert = _round(stores, chains)
    kinds = ["view", "seq", "digest", "replica_id_all", "signature_all", "drop_commit", "dup_commit", "pubkey_all", "mix_digest", "header_seq_keep_commits"]
    for kind in kinds:
        mutated = _mutate(cert, kind)
        assert verify_certificate(mutated) is False, kind
        victim = OFFICIAL_COMPUTE_NODE_IDS[1]
        got = stores[victim].install_certificate(mutated)
        assert got.get("ok") is not True, kind


def test_p9_one_faulty_commit_among_four_still_quorum(tmp_path: Path) -> None:
    """N=4 F=1: corrupting one commit must not invalidate a Q=3 certificate."""
    stores, chains, _ = _cluster(tmp_path)
    _block, cert = _round(stores, chains, graph_id="f1")
    assert len(cert.get("commits") or []) >= 3
    one = copy.deepcopy(cert)
    one["commits"] = list(one["commits"])
    one["commits"][0] = dict(one["commits"][0], signature="00" * 32)
    assert verify_certificate(one) is True


def test_p17_cert_block_binding_and_sidecar_hash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_PBFT_EXCLUSIVE_FROM", "0")
    stores, chains, _ = _cluster(tmp_path)
    block, cert = _round(stores, chains, graph_id="bind")
    h1 = block["hash"]
    sidecar = dict(block, pbft_cert=cert)
    assert sidecar["hash"] == h1
    other = dict(block)
    other["hash"] = "ee" * 32
    other["index"] = int(block["index"])
    victim = OFFICIAL_COMPUTE_NODE_IDS[1]
    assert chains[victim].import_extending_block({**other, "pbft_cert": cert}, require_public=False, from_node_id="x") is False
    evil_cert = dict(cert, digest="ee" * 32)
    assert chains[victim].import_extending_block({**block, "pbft_cert": evil_cert}, require_public=False, from_node_id="x") is False


def test_p11_byzantine_prepare_xy_no_dual_cert(tmp_path: Path) -> None:
    stores, chains, _ = _cluster(tmp_path)
    primary = primary_of(0)
    block_x = json.loads(
        chains[primary]
        .append_block(graph_id="x", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    block_y = dict(block_x)
    block_y["hash"] = "ff" * 32
    block_y["graph_id"] = "y"
    pp_x = stores[primary].emit_preprepare(chains[primary], block=block_x)
    left = list(OFFICIAL_COMPUTE_NODE_IDS)[:2]
    right = list(OFFICIAL_COMPUTE_NODE_IDS)[2:]
    for nid in left:
        if nid != primary:
            assert stores[nid].accept_preprepare(pp_x)["ok"] is True
    for nid in right:
        got = stores[nid].accept_preprepare(pp_x)
        assert got.get("ok") is True
    y_prepare_attempts = []
    for nid in right:
        try:
            stores[nid].emit_prepare(chains[nid], view=0, seq=int(block_x["index"]), digest=str(block_y["hash"]))
            y_prepare_attempts.append("emitted")
        except ValueError as exc:
            y_prepare_attempts.append(str(exc))
    assert all(x == "not_accepted" for x in y_prepare_attempts)
    fake_y = dict(pp_x)
    fake_y["digest"] = block_y["hash"]
    for nid in left:
        got = stores[nid].accept_prepare(fake_y)
        assert got.get("ok") is not True
    certs = [stores[n].certificate(int(block_x["index"])) for n in OFFICIAL_COMPUTE_NODE_IDS]
    assert all(c is None or verify_certificate(c) for c in certs)
    assert not any(c and c.get("digest") == block_y["hash"] for c in certs if c)


def test_p12_prepare_and_commit_replay_wrong_view(tmp_path: Path) -> None:
    stores, chains, _ = _cluster(tmp_path)
    block, _cert = _round(stores, chains, graph_id="replay")
    primary = primary_of(0)
    other = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary][0]
    prep = stores[primary].emit_prepare(chains[primary], view=0, seq=0, digest=block["hash"])
    replay = dict(prep, view=7)
    assert stores[other].accept_prepare(replay).get("ok") is not True
    commit = stores[primary].emit_commit(chains[primary], view=0, seq=0, digest=block["hash"])["commit"]
    replay_c = dict(commit, view=7)
    assert stores[other].accept_commit(replay_c).get("ok") is not True


def test_p14_truncated_state_does_not_invent_certificate(tmp_path: Path) -> None:
    stores, chains, _ = _cluster(tmp_path)
    block, cert = _round(stores, chains, graph_id="disk")
    nid = OFFICIAL_COMPUTE_NODE_IDS[0]
    path = stores[nid].path
    path.write_text("{truncated", encoding="utf-8")
    reloaded = PbftFinalityStore(tmp_path / nid, replica_id=nid)
    assert reloaded.certificate(int(block["index"])) is None
    assert verify_certificate(cert) is True
    path.write_text(json.dumps({"certificates": {"0": {"digest": "dead", "commits": []}}}), encoding="utf-8")
    reloaded2 = PbftFinalityStore(tmp_path / nid, replica_id=nid)
    assert reloaded2.certificate(0) is None


def test_p15_agent_identity_conflict(tmp_path: Path) -> None:
    rt = AgentRuntime(tmp_path)
    first = rt.register_agent(provider="cursor", label="a", owner_address="artcb1aaa", capabilities=["memory:read"], agent_id="agent_fixed")
    again = rt.register_agent(provider="cursor", label="a2", owner_address="artcb1aaa", capabilities=["memory:write"], agent_id="agent_fixed")
    assert again["agent_id"] == first["agent_id"]
    try:
        rt.register_agent(provider="claude", label="b", owner_address="artcb1aaa", capabilities=["memory:read"], agent_id="agent_fixed")
        raised = ""
    except ValueError as exc:
        raised = str(exc)
    assert raised == "agent_identity_conflict"
    try:
        rt.register_agent(provider="cursor", label="c", owner_address="artcb1bbb", capabilities=["memory:read"], agent_id="agent_fixed")
        raised2 = ""
    except ValueError as exc:
        raised2 = str(exc)
    assert raised2 == "agent_identity_conflict"


def test_p16_idempotency_conflict_different_payload(tmp_path: Path) -> None:
    rt = AgentRuntime(tmp_path)
    first = rt.commit_event(event_id="evt_x", agent_id="a", kind="observation", content_sha256="aa" * 32, block_index=1, block_hash="bb" * 32, graph_id="g")
    clash = rt.commit_event(event_id="evt_x", agent_id="a", kind="observation", content_sha256="cc" * 32, block_index=2, block_hash="dd" * 32, graph_id="g2")
    assert first["status"] == "committed"
    assert clash["status"] == "idempotency_conflict"
    assert clash["block_index"] == 1
    assert "wallet:export" not in capabilities_for_scopes(["read", "write"])


def test_p16_http_idempotency_conflict(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-1")
    client = TestClient(create_app())
    body = {"event_id": "evt_conflict_269", "kind": "observation", "content": "payload-A", "visibility": "private", "tags": ["269"], "session_id": "269"}
    first = client.post("/api/v1/agent/events", json=body)
    assert first.status_code == 200, first.text
    clash = client.post("/api/v1/agent/events", json={**body, "content": "payload-B"})
    assert clash.status_code == 409
    assert "idempotency_conflict" in clash.text
    same = client.post("/api/v1/agent/events", json=body)
    assert same.status_code == 200
    assert same.json()["status"] == "already_committed"
    reg = client.post("/api/v1/agent/register", json={"provider": "cursor", "label": "one", "agent_id": "agent_p15", "capabilities": ["memory:read"]})
    assert reg.status_code == 200
    clash_reg = client.post("/api/v1/agent/register", json={"provider": "claude", "label": "two", "agent_id": "agent_p15", "capabilities": ["memory:read"]})
    assert clash_reg.status_code == 409


def test_p18_random_cert_mutations(tmp_path: Path) -> None:
    stores, chains, _ = _cluster(tmp_path)
    _block, cert = _round(stores, chains, graph_id="p18")
    kinds = ["view", "seq", "digest", "replica_id_all", "signature_all", "drop_commit", "dup_commit", "pubkey_all", "mix_digest", "header_seq_keep_commits"]
    rng = random.Random(269)
    rejected = 0
    for i in range(200):
        kind = kinds[rng.randrange(len(kinds))]
        mutated = _mutate(cert, kind)
        assert verify_certificate(mutated) is False
        rejected += 1
    assert rejected == 200
    assert verify_certificate(cert) is True
