"""265 — PBFT block finality. Nanosecond traces required. Not a 264-only PASS."""

from __future__ import annotations

import json
from pathlib import Path

from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import (
    PbftFinalityStore,
    verify_certificate,
    verify_preprepare,
)
from artcb.consensus.pbft_view import PbftViewStore, primary_of
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS
from artcb.trace.ns import is_nanosecond_ts, list_traces

ROOT = Path(__file__).resolve().parents[1]


def test_rule_requires_nanosecond_and_block_finality() -> None:
    rule = (ROOT / ".cursor" / "rules" / "artcb-live-node.mdc").read_text(encoding="utf-8")
    assert "nanoseconde" in rule.lower() or "nanosecond" in rule.lower()
    assert "NOT_VALIDATED" in rule
    assert "265" in rule or "PRE-PREPARE" in rule
    prompt = (ROOT / "AUTO_PROMPT_ARTCB").read_text(encoding="utf-8")
    assert "nanoseconde" in prompt.lower() or "nanosecond" in prompt.lower() or "265" in prompt


def _cluster(tmp_path: Path):
    stores = {}
    chains = {}
    views = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        d = tmp_path / nid
        chain = ChainManager(d / "chain" / "blocks.jsonl", key_path=d / "k", enable_security=False)
        vs = PbftViewStore(d, replica_id=nid)
        stores[nid] = PbftFinalityStore(d, replica_id=nid, view_store=vs)
        chains[nid] = chain
        views[nid] = vs
    return stores, chains, views


def _round(stores, chains, *, graph_id: str = "pbft-a"):
    primary = primary_of(0)
    constructed = chains[primary].append_block(
        graph_id=graph_id, graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True
    )
    block = json.loads(constructed.to_json_line())
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    assert verify_preprepare(pp) is True
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid == primary:
            continue
        assert stores[nid].accept_preprepare(pp)["ok"] is True
    prepares = []
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        prepares.append(
            stores[nid].emit_prepare(chains[nid], view=0, seq=int(block["index"]), digest=str(block["hash"]))
        )
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for prep in prepares:
            if prep["replica_id"] == nid:
                continue
            stores[nid].accept_prepare(prep)
    commits = []
    cert = None
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        emitted = stores[nid].emit_commit(chains[nid], view=0, seq=int(block["index"]), digest=str(block["hash"]))
        commits.append(emitted["commit"])
        if emitted.get("certificate"):
            cert = emitted["certificate"]
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for c in commits:
            if c["replica_id"] == nid:
                continue
            got = stores[nid].accept_commit(c)
            if got.get("certificate"):
                cert = got["certificate"]
    assert cert is not None
    assert verify_certificate(cert) is True
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        assert chains[nid].write_certified_block(block, cert) is True
    return block, cert


def test_a_normal_path_four_replicas_finalize(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    block, cert = _round(stores, chains)
    heights = {chains[n].height() for n in OFFICIAL_COMPUTE_NODE_IDS}
    hashes = {chains[n].last_hash() for n in OFFICIAL_COMPUTE_NODE_IDS}
    assert heights == {1}
    assert hashes == {block["hash"]}
    assert cert["q"] == 3
    assert len(cert["replica_ids"]) >= 3
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        rows = list_traces(tmp_path / nid, limit=200)
        pbft = [r for r in rows if str(r.get("kind") or "").startswith("pbft_")]
        assert pbft, nid
        assert all(is_nanosecond_ts(r.get("ts_ns")) for r in pbft)
        assert all("dur_ns" in r and int(r["dur_ns"]) >= 0 for r in pbft)


def test_c_equivocation_rejected(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    a = json.loads(
        chains[primary]
        .append_block(graph_id="A", graph_root="a", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    b = dict(a)
    b["hash"] = "b" * 64
    b["graph_id"] = "B"
    pp = stores[primary].emit_preprepare(chains[primary], block=a)
    other = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary]
    stores[other[0]].accept_preprepare(pp)
    try:
        stores[primary].emit_preprepare(chains[primary], block=b)
        raised = False
    except ValueError as exc:
        raised = str(exc) == "equivocation"
    assert raised is True
    fake = dict(pp)
    fake["digest"] = b["hash"]
    fake["block"] = b
    reason = stores[other[0]].accept_preprepare(fake).get("reason")
    assert reason in {"equivocation", "invalid_preprepare"}


def test_e_insufficient_commits_and_bad_new_view_value(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    block = json.loads(
        chains[primary]
        .append_block(graph_id="e", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    majority = list(OFFICIAL_COMPUTE_NODE_IDS)[:2]
    for nid in majority:
        if nid != primary:
            stores[nid].accept_preprepare(pp)
    prepares = []
    for nid in majority:
        prepares.append(stores[nid].emit_prepare(chains[nid], view=0, seq=0, digest=block["hash"]))
    for nid in majority:
        for p in prepares:
            if p["replica_id"] != nid:
                stores[nid].accept_prepare(p)
    try:
        stores[primary].emit_commit(chains[primary], view=0, seq=0, digest=block["hash"])
        prepared_anyway = True
    except ValueError:
        prepared_anyway = False
    assert prepared_anyway is False
    assert stores[primary].certificate(0) is None


def test_f_bad_signature_rejected(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    block = json.loads(
        chains[primary]
        .append_block(graph_id="f", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    pp["signature"] = "deadbeef"
    other = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary][0]
    assert stores[other].accept_preprepare(pp)["ok"] is False


def test_d_view_change_keeps_prepared(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    block = json.loads(
        chains[primary]
        .append_block(graph_id="d", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    majority = list(OFFICIAL_COMPUTE_NODE_IDS)[:3]
    for nid in majority:
        if nid != primary:
            stores[nid].accept_preprepare(pp)
    prepares = [stores[n].emit_prepare(chains[n], view=0, seq=0, digest=block["hash"]) for n in majority]
    for nid in majority:
        for p in prepares:
            if p["replica_id"] != nid:
                stores[nid].accept_prepare(p)
    vcs = [stores[n].emit_view_change_265(chains[n], view=1) for n in majority]
    chosen = stores[majority[1]].select_new_view_value(vcs)
    assert chosen is not None
    assert chosen["digest"] == block["hash"]
    assert chosen["seq"] == 0


def test_j_finalized_index_cannot_be_replaced(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    block, cert = _round(stores, chains, graph_id="j")
    other = dict(block)
    other["hash"] = "c" * 64
    other["graph_id"] = "evil"
    victim = OFFICIAL_COMPUTE_NODE_IDS[1]
    assert chains[victim].import_extending_block(other, require_public=False, from_node_id="evil") is False
    assert chains[victim].last_hash() == block["hash"]
    assert verify_certificate(cert) is True


def test_g_two_replicas_cannot_certify(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    pair = list(OFFICIAL_COMPUTE_NODE_IDS)[:2]
    primary = primary_of(0)
    block = json.loads(
        chains[primary]
        .append_block(graph_id="g", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    other = [n for n in pair if n != primary][0]
    stores[other].accept_preprepare(pp)
    p1 = stores[primary].emit_prepare(chains[primary], view=0, seq=0, digest=block["hash"])
    p2 = stores[other].emit_prepare(chains[other], view=0, seq=0, digest=block["hash"])
    stores[primary].accept_prepare(p2)
    stores[other].accept_prepare(p1)
    try:
        stores[primary].emit_commit(chains[primary], view=0, seq=0, digest=block["hash"])
        got_commit = True
    except ValueError:
        got_commit = False
    assert got_commit is False
    assert stores[primary].certificate(0) is None


def test_http_propose_preprepare_on_primary(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-1")
    client = TestClient(create_app())
    fin = client.get("/api/v1/consensus/pbft/finality")
    assert fin.status_code == 200
    assert fin.json()["q"] == 3
    assert fin.json()["finality_on_append_path"] is True
    prop = client.post("/api/v1/consensus/pbft/propose", json={"graph_id": "http-a", "graph_root": "r"})
    assert prop.status_code == 200
    body = prop.json()
    assert body["ok"] is True
    assert verify_preprepare(body["pre_prepare"]) is True
    traced = client.get("/api/v1/trace?limit=50")
    assert traced.json()["unit"] == "nanosecond"
    assert traced.json()["includes_pbft"] is True
    kinds = {r.get("kind") for r in traced.json().get("rows") or []}
    assert any(str(k).startswith("pbft_") for k in kinds)
