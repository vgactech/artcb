"""R273 — NEW-VIEW prepared must be carried by a VIEW-CHANGE quorum.

A single valid prepared certificate is not selectable. Missing reconstructable
prepared while VIEW-CHANGE claims one is fail-closed (state_incomplete).
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
            graph_id=graph_id, graph_root="r", pol_score=0.1, visibility="public", source="pbft:273", dry_run=True
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


def test_single_view_change_cannot_select_prepared(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    old_p = primary_of(0)
    block = _block(chains[old_p], "one-vc")
    pp = stores[old_p].emit_preprepare(chains[old_p], block=block)
    _prepare_quorum(stores, chains, block, pp)
    one = stores[old_p].emit_view_change_265(chains[old_p], view=1)
    assert verify_prepared_certificate((one.get("prepared") or [None])[0]) is True
    analysis = stores[old_p].analyze_new_view_certificate([one])
    assert analysis["quorum_ok"] is False
    assert analysis["claimed_prepared"] is True
    assert analysis["selected"] is None
    assert analysis["reason"] == "prepared_without_vc_quorum"
    assert stores[old_p].select_new_view_value([one]) is None


def test_quorum_view_changes_select_highest_prepared(tmp_path: Path) -> None:
    stores, chains, views = _cluster(tmp_path)
    old_p = primary_of(0)
    block = _block(chains[old_p], "q-vc")
    pp = stores[old_p].emit_preprepare(chains[old_p], block=block)
    _prepare_quorum(stores, chains, block, pp)
    vcs = [stores[n].emit_view_change_265(chains[n], view=1) for n in OFFICIAL_COMPUTE_NODE_IDS]
    new_p = primary_of(1)
    chosen = stores[new_p].select_new_view_value(vcs)
    assert chosen is not None
    assert verify_prepared_certificate(chosen) is True
    assert chosen["digest"] == block["hash"]
    analysis = stores[new_p].analyze_new_view_certificate(vcs)
    assert analysis["quorum_ok"] is True
    assert analysis["quorum_view_changes"] >= 3
    assert analysis["selected"]["digest"] == block["hash"]
    views[new_p]._state["view"] = 1
    views[new_p]._state["primary"] = new_p
    entered = stores[new_p].enter_view(1, vcs)
    assert entered["ok"] is True
    assert entered["bound"]["ok"] is True


def test_enter_view_fail_closed_when_prepared_claimed_without_quorum(tmp_path: Path) -> None:
    stores, chains, views = _cluster(tmp_path)
    old_p = primary_of(0)
    block = _block(chains[old_p], "incomplete")
    pp = stores[old_p].emit_preprepare(chains[old_p], block=block)
    _prepare_quorum(stores, chains, block, pp)
    one = stores[old_p].emit_view_change_265(chains[old_p], view=1)
    new_p = primary_of(1)
    views[new_p]._state["view"] = 1
    views[new_p]._state["primary"] = new_p
    # Follower that lost local prepared still sees one VC claiming X.
    follower = [n for n in OFFICIAL_COMPUTE_NODE_IDS if n != old_p][0]
    stores[follower]._state["prepared"] = {}
    entered = stores[follower].enter_view(1, [one])
    assert entered["ok"] is False
    assert entered["reason"] == "state_incomplete"
    assert stores[follower]._state.get("must_repropose") in (None, {})


def test_claimed_unreconstructable_prepared_is_state_incomplete(tmp_path: Path) -> None:
    stores, chains, _views = _cluster(tmp_path)
    fake = {
        "kind": "view-change-265",
        "protocol": "265-pbft-block-finality",
        "replica_id": "ovh-node-1",
        "view": 1,
        "from_view": 0,
        "prepared": [{"seq": 9, "digest": "aa" * 32, "preprepare": {}, "prepares": []}],
        "pset_digest": "",
        "message": "",
        "signature": "x",
        "producer_ed25519_b64": "eQ==",
        "producer_pqc_b64": "",
    }
    # Invalid VC (signature) that still claims a prepared list.
    from artcb.consensus.pbft_finality import pset_digest, vc265_message
    from artcb.consensus.tip_attest import producer_key_b64, sign_message

    prepared = [{"seq": 9, "digest": "aa" * 32}]
    digest = pset_digest(prepared)
    msg = vc265_message(view=1, from_view=0, replica_id="ovh-node-1", pset_digest=digest)
    ed, pqc = producer_key_b64(chains["ovh-node-1"])
    fake = {
        "kind": "view-change-265",
        "protocol": "265-pbft-block-finality",
        "replica_id": "ovh-node-1",
        "view": 1,
        "from_view": 0,
        "prepared": prepared,
        "pset_digest": digest,
        "message": msg,
        "signature": sign_message(chains["ovh-node-1"], msg),
        "producer_ed25519_b64": ed,
        "producer_pqc_b64": pqc,
    }
    assert stores["ovh-node-1"].verify_view_change_265(fake) is True
    analysis = stores["ovh-node-1"].analyze_new_view_certificate([fake])
    assert analysis["claimed_prepared"] is True
    assert analysis["reconstructable"] is False
    assert analysis["reason"] == "state_incomplete"
    entered = stores["ovh-node-1"].enter_view(1, [fake])
    assert entered["ok"] is False
    assert entered["reason"] == "state_incomplete"


def test_attempts_helper_does_not_flatten_recovery() -> None:
    from src.artcb.consensus.campaign_artifacts import final_status_from_attempts, record_attempt

    attempts: list[dict] = []
    record_attempt(attempts, result="FAIL", reason="equivocation")
    record_attempt(attempts, result="PASS", recovery="VIEW_CHANGE")
    assert final_status_from_attempts(attempts) == "PASS_AFTER_RECOVERY"
    assert attempts[0]["result"] == "FAIL"
    assert attempts[1]["result"] == "PASS"
