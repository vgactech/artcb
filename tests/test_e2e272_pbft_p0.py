"""R272 — P0: orphan PRE-PREPARE vs prepared obligation.

Same-view distinct digest stays equivocation. NEW-VIEW drops unprepared
locks and makes prepared(X) mandatory. Commit receive requires prepared.
"""

from __future__ import annotations

import json
from pathlib import Path

from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import PbftFinalityStore, verify_prepared_certificate
from artcb.consensus.pbft_view import PbftViewStore, primary_of
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS


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


def _block(chain, graph_id: str) -> dict:
    return json.loads(
        chain.append_block(
            graph_id=graph_id, graph_root="r", pol_score=0.1, visibility="public", source="pbft:272", dry_run=True
        ).to_json_line()
    )


def _prepare_quorum(stores, chains, block, pp) -> None:
    primary = primary_of(stores[next(iter(stores))].view)
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid != primary:
            assert stores[nid].accept_preprepare(pp)["ok"] is True
    view = stores[primary].view
    seq = int(block["index"])
    digest = str(block["hash"])
    prepares = [stores[n].emit_prepare(chains[n], view=view, seq=seq, digest=digest) for n in OFFICIAL_COMPUTE_NODE_IDS]
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for prep in prepares:
            if prep["replica_id"] != nid:
                stores[nid].accept_prepare(prep)


def test_same_view_distinct_digest_still_equivocation(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    a = _block(chains[primary], "A")
    b = dict(a)
    b["hash"] = "b" * 64
    b["graph_id"] = "B"
    stores[primary].emit_preprepare(chains[primary], block=a)
    try:
        stores[primary].emit_preprepare(chains[primary], block=b)
        raised = ""
    except ValueError as exc:
        raised = str(exc)
    assert raised == "equivocation"


def test_enter_view_drops_orphan_and_allows_new_digest(tmp_path: Path) -> None:
    stores, chains, views = _cluster(tmp_path)
    old_p = primary_of(0)
    a = _block(chains[old_p], "orphan")
    stores[old_p].emit_preprepare(chains[old_p], block=a)
    new_v = 1
    new_p = primary_of(new_v)
    dropped_any: list[str] = []
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        views[nid]._state["view"] = new_v
        views[nid]._state["primary"] = new_p
        entered = stores[nid].enter_view(new_v)
        assert entered["ok"] is True
        dropped_any.extend(entered["dropped"])
    assert any(k.startswith("0:") for k in dropped_any)
    y = _block(chains[new_p], "after-vc")
    # unprepared orphan must not force Y to 409
    pp = stores[new_p].emit_preprepare(chains[new_p], block=y)
    assert pp["digest"] == y["hash"]


def test_enter_view_binds_prepared_refuses_y_allows_x(tmp_path: Path) -> None:
    stores, chains, views = _cluster(tmp_path)
    old_p = primary_of(0)
    block = _block(chains[old_p], "prepared-x")
    pp = stores[old_p].emit_preprepare(chains[old_p], block=block)
    _prepare_quorum(stores, chains, block, pp)
    assert stores[old_p].prepared_set()
    new_v = 1
    new_p = primary_of(new_v)
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        views[nid]._state["view"] = new_v
        views[nid]._state["primary"] = new_p
        bound = stores[nid].enter_view(new_v)
        assert bound["bound"]["ok"] is True
        assert bound["bound"]["digest"] == block["hash"]
    y = dict(block)
    y["hash"] = "ab" * 32
    y["graph_id"] = "Y"
    try:
        stores[new_p].emit_preprepare(chains[new_p], block=y)
        raised = ""
    except ValueError as exc:
        raised = str(exc)
    assert raised == "must_repropose_prepared"
    again = stores[new_p].emit_preprepare(chains[new_p], block=block)
    assert again["digest"] == block["hash"]


def test_select_prepared_path_binds_without_extra_call(tmp_path: Path) -> None:
    stores, chains, views = _cluster(tmp_path)
    old_p = primary_of(0)
    block = _block(chains[old_p], "p8")
    pp = stores[old_p].emit_preprepare(chains[old_p], block=block)
    _prepare_quorum(stores, chains, block, pp)
    vcs = [stores[n].emit_view_change_265(chains[n], view=1) for n in OFFICIAL_COMPUTE_NODE_IDS]
    new_p = primary_of(1)
    views[new_p]._state["view"] = 1
    views[new_p]._state["primary"] = new_p
    chosen = stores[new_p].select_new_view_value(vcs)
    assert chosen is not None
    assert verify_prepared_certificate(chosen) is True
    bound = stores[new_p].bind_prepared_constraint(chosen)
    assert bound["ok"] is True
    y = dict(block)
    y["hash"] = "cd" * 32
    try:
        stores[new_p].emit_preprepare(chains[new_p], block=y)
        raised = ""
    except ValueError as exc:
        raised = str(exc)
    assert raised == "must_repropose_prepared"


def test_accept_commit_requires_prepared(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    primary = primary_of(0)
    block = _block(chains[primary], "commit-early")
    stores[primary].emit_preprepare(chains[primary], block=block)
    from artcb.consensus.pbft_finality import commit_message, verify_commit
    from artcb.consensus.tip_attest import producer_key_b64, sign_message

    msg = commit_message(view=0, seq=int(block["index"]), digest=str(block["hash"]), replica_id=primary)
    ed, pqc = producer_key_b64(chains[primary])
    row = {
        "kind": "commit",
        "protocol": "265-pbft-block-finality",
        "message": msg,
        "replica_id": primary,
        "signature": sign_message(chains[primary], msg),
        "producer_ed25519_b64": ed,
        "producer_pqc_b64": pqc,
        "view": 0,
        "seq": int(block["index"]),
        "digest": str(block["hash"]),
    }
    assert verify_commit(row) is True
    other = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != primary][0]
    got = stores[other].accept_commit(row)
    assert got.get("ok") is not True
    assert got.get("reason") == "not_prepared"
