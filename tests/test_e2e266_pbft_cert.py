"""266 — exclusive public PBFT, signed equivocation, dual-cert safety.

Nanosecond traces required. Complements 265 (path exists) with exclusivity
and Byzantine-valid contradiction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import (
    FIRST_LIVE_CERTIFIED_SEQ,
    PbftFinalityStore,
    exclusive_public_from,
    sign_preprepare,
    verify_certificate,
    verify_preprepare,
)
from artcb.consensus.pbft_view import PbftViewStore, primary_of
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS
from artcb.trace.ns import is_nanosecond_ts, list_traces

ROOT = Path(__file__).resolve().parents[1]


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


def test_exclusive_from_default_is_first_certified_seq(tmp_path: Path) -> None:
    assert exclusive_public_from(tmp_path) == FIRST_LIVE_CERTIFIED_SEQ


def test_v01_official_public_append_refused_without_quorum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-1")
    chain = ChainManager(tmp_path / "chain" / "blocks.jsonl", key_path=tmp_path / "k", enable_security=False)
    with pytest.raises(ValueError, match="pbft_required_for_public_append"):
        chain.append_block(graph_id="g", graph_root="r", pol_score=0.1, visibility="public", source="ai:memo")
    assert chain.height() == 0
    private = chain.append_block(graph_id="p", graph_root="r", pol_score=0.1, visibility="private", source="ai:memo")
    assert private.index == 0
    assert chain.height() == 1
    dry = chain.append_block(
        graph_id="d", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True
    )
    assert dry.index == 1
    assert chain.height() == 1


def test_v01_public_import_requires_cert_from_epoch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_PBFT_EXCLUSIVE_FROM", "0")
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    constructed = json.loads(
        chains[primary]
        .append_block(graph_id="e", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    victim = OFFICIAL_COMPUTE_NODE_IDS[1]
    assert chains[victim].import_extending_block(constructed, require_public=False, from_node_id="bare") is False
    assert chains[victim].height() == 0


def test_v01_certified_write_passes_exclusive_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_PBFT_EXCLUSIVE_FROM", "0")
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    block = json.loads(
        chains[primary]
        .append_block(graph_id="c", graph_root="r", pol_score=0.1, visibility="public", source="pbft:test", dry_run=True)
        .to_json_line()
    )
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    assert verify_preprepare(pp) is True
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid != primary:
            assert stores[nid].accept_preprepare(pp)["ok"] is True
    prepares = [
        stores[n].emit_prepare(chains[n], view=0, seq=int(block["index"]), digest=str(block["hash"]))
        for n in OFFICIAL_COMPUTE_NODE_IDS
    ]
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for prep in prepares:
            if prep["replica_id"] != nid:
                stores[nid].accept_prepare(prep)
    cert = None
    commits = []
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
        assert chains[nid].last_hash() == block["hash"]
    rows = list_traces(tmp_path / primary, limit=200)
    pbft = [r for r in rows if str(r.get("kind") or "").startswith("pbft_")]
    assert pbft
    assert all(is_nanosecond_ts(r.get("ts_ns")) for r in pbft)


def test_v02_two_valid_signed_preprepares_never_double_finalize(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    x = json.loads(
        chains[primary]
        .append_block(graph_id="X", graph_root="x", pol_score=0.1, visibility="public", source="pbft:v02", dry_run=True)
        .to_json_line()
    )
    y = json.loads(
        chains[primary]
        .append_block(graph_id="Y", graph_root="y", pol_score=0.1, visibility="public", source="pbft:v02", dry_run=True)
        .to_json_line()
    )
    assert x["index"] == y["index"] == 0
    assert x["hash"] != y["hash"]
    pp_x = sign_preprepare(chains[primary], view=0, replica_id=primary, block=x)
    pp_y = sign_preprepare(chains[primary], view=0, replica_id=primary, block=y)
    assert verify_preprepare(pp_x) is True
    assert verify_preprepare(pp_y) is True
    group_x = list(OFFICIAL_COMPUTE_NODE_IDS)[:2]
    group_y = list(OFFICIAL_COMPUTE_NODE_IDS)[2:]
    for nid in group_x:
        assert stores[nid].accept_preprepare(pp_x)["ok"] is True
    for nid in group_y:
        assert stores[nid].accept_preprepare(pp_y)["ok"] is True
    # Honest replica that saw X refuses Y.
    assert stores[group_x[0]].accept_preprepare(pp_y).get("reason") == "equivocation"
    prepares_x = [stores[n].emit_prepare(chains[n], view=0, seq=0, digest=x["hash"]) for n in group_x]
    prepares_y = [stores[n].emit_prepare(chains[n], view=0, seq=0, digest=y["hash"]) for n in group_y]
    for nid in group_x:
        for p in prepares_x:
            if p["replica_id"] != nid:
                stores[nid].accept_prepare(p)
    for nid in group_y:
        for p in prepares_y:
            if p["replica_id"] != nid:
                stores[nid].accept_prepare(p)
    for nid in group_x:
        with pytest.raises(ValueError):
            stores[nid].emit_commit(chains[nid], view=0, seq=0, digest=x["hash"])
    for nid in group_y:
        with pytest.raises(ValueError):
            stores[nid].emit_commit(chains[nid], view=0, seq=0, digest=y["hash"])
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        assert stores[nid].certificate(0) is None
        assert stores[nid].finalized_digest(0) is None


def test_v03_second_certificate_same_seq_conflict(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    block = json.loads(
        chains[primary]
        .append_block(graph_id="v03", graph_root="r", pol_score=0.1, visibility="public", source="pbft:v03", dry_run=True)
        .to_json_line()
    )
    pp = stores[primary].emit_preprepare(chains[primary], block=block)
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid != primary:
            stores[nid].accept_preprepare(pp)
    prepares = [
        stores[n].emit_prepare(chains[n], view=0, seq=0, digest=block["hash"]) for n in OFFICIAL_COMPUTE_NODE_IDS
    ]
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for p in prepares:
            if p["replica_id"] != nid:
                stores[nid].accept_prepare(p)
    cert = None
    commits = []
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        emitted = stores[nid].emit_commit(chains[nid], view=0, seq=0, digest=block["hash"])
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
    evil = dict(cert)
    evil["digest"] = "ab" * 32
    victim = OFFICIAL_COMPUTE_NODE_IDS[1]
    result = stores[victim].install_certificate(evil)
    assert result.get("ok") is False
    assert result.get("reason") in {"invalid_certificate", "certificate_conflict"}
    assert stores[victim].finalized_digest(0) == block["hash"]


def test_http_client_request_not_primary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-2")
    client = TestClient(create_app())
    fin = client.get("/api/v1/consensus/pbft/finality")
    assert fin.status_code == 200
    assert fin.json().get("public_append_exclusive_pbft") is True
    body = {
        "block": {
            "index": 0,
            "hash": "aa" * 32,
            "prev_hash": "0" * 64,
            "visibility": "public",
        }
    }
    req = client.post("/api/v1/consensus/pbft/client-request", json=body)
    assert req.status_code == 409
    assert req.json().get("detail") == "not_primary"


def test_rule_and_prompt_mention_exclusive_pbft() -> None:
    rule = (ROOT / ".cursor" / "rules" / "artcb-live-node.mdc").read_text(encoding="utf-8")
    prompt = (ROOT / "AUTO_PROMPT_ARTCB").read_text(encoding="utf-8")
    assert "nanoseconde" in rule.lower() or "nanosecond" in rule.lower()
    assert "266" in rule or "exclusif" in rule.lower() or "exclusive" in rule.lower()
    assert "266" in prompt or "exclusif" in prompt.lower() or "exclusive" in prompt.lower()
