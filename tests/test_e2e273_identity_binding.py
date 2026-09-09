"""R273 — NodeID ↔ key binding (A1 / A3 / A7).

A3 and A7: K(ovh-node-1) must not speak as ovh-node-2.
Same-view 409 equivocation is unchanged and is not a bug.
"""

from __future__ import annotations

import json
from pathlib import Path

from artcb.chain.manager import ChainManager
from artcb.consensus.pbft_finality import (
    PbftFinalityStore,
    commit_message,
    prepare_message,
    verify_commit,
    verify_prepare,
    verify_signed,
    verify_signed_detailed,
)
from artcb.consensus.pbft_view import PbftViewStore, primary_of, verify_view_change
from src.artcb.consensus.replica_identity import (
    ReplicaKeyBinding,
    override_replica_registry,
    register_chain_replicas,
    verify_replica_key_binding,
)
from artcb.consensus.tip_attest import attest_tip, producer_key_b64, sign_message, verify_attest
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS


def _chain(tmp_path: Path, name: str) -> ChainManager:
    d = tmp_path / name
    return ChainManager(d / "blocks.jsonl", key_path=d / "k", enable_security=False)


def test_a1_correct_key_accepts(tmp_path: Path) -> None:
    chains = {nid: _chain(tmp_path, nid) for nid in ("ovh-node-1", "ovh-node-2")}
    register_chain_replicas(chains)
    msg = prepare_message(view=0, seq=1, digest="ab" * 32, replica_id="ovh-node-2")
    ed, pqc = producer_key_b64(chains["ovh-node-2"])
    row = {
        "kind": "prepare",
        "protocol": "265-pbft-block-finality",
        "message": msg,
        "replica_id": "ovh-node-2",
        "signature": sign_message(chains["ovh-node-2"], msg),
        "producer_ed25519_b64": ed,
        "producer_pqc_b64": pqc,
        "view": 0,
        "seq": 1,
        "digest": "ab" * 32,
    }
    assert verify_prepare(row) is True
    assert verify_signed_detailed(row, msg)[1] == "ok"


def test_a3_a7_k1_cannot_claim_ovh_node_2(tmp_path: Path) -> None:
    k1 = _chain(tmp_path, "ovh-node-1")
    k2 = _chain(tmp_path, "ovh-node-2")
    register_chain_replicas({"ovh-node-1": k1, "ovh-node-2": k2})
    msg = prepare_message(view=15, seq=500, digest="cd" * 32, replica_id="ovh-node-2")
    ed1, pqc1 = producer_key_b64(k1)
    row = {
        "kind": "prepare",
        "protocol": "265-pbft-block-finality",
        "message": msg,
        "replica_id": "ovh-node-2",
        "signature": sign_message(k1, msg),
        "producer_ed25519_b64": ed1,
        "producer_pqc_b64": pqc1,
        "view": 15,
        "seq": 500,
        "digest": "cd" * 32,
    }
    ok, reason = verify_signed_detailed(row, msg)
    assert ok is False
    assert reason == "invalid_replica_key_binding"
    assert verify_prepare(row) is False
    assert verify_signed(row, msg) is False
    bind_ok, bind_reason = verify_replica_key_binding("ovh-node-2", ed1, pqc1)
    assert bind_ok is False
    assert bind_reason == "invalid_replica_key_binding"


def test_a3_tip_attest_k1_as_ovh2(tmp_path: Path) -> None:
    k1 = _chain(tmp_path, "ovh-node-1")
    k2 = _chain(tmp_path, "ovh-node-2")
    register_chain_replicas({"ovh-node-1": k1, "ovh-node-2": k2})
    row = attest_tip(k1, git_sha="a" * 40, node_id="ovh-node-2")
    assert verify_attest(row) is False
    honest = attest_tip(k2, git_sha="a" * 40, node_id="ovh-node-2")
    assert verify_attest(honest) is True


def test_a5_revoked_key_rejected(tmp_path: Path) -> None:
    k2 = _chain(tmp_path, "ovh-node-2")
    ed, pqc = producer_key_b64(k2)
    with override_replica_registry(
        {
            "ovh-node-2": ReplicaKeyBinding(
                node_id="ovh-node-2",
                ed25519_b64=ed,
                pqc_b64=pqc,
                revoked=True,
            )
        }
    ):
        ok, reason = verify_replica_key_binding("ovh-node-2", ed, pqc)
        assert ok is False
        assert reason == "replica_key_revoked"


def test_commit_and_view_change_also_bind(tmp_path: Path) -> None:
    k1 = _chain(tmp_path, "ovh-node-1")
    k2 = _chain(tmp_path, "ovh-node-2")
    register_chain_replicas({"ovh-node-1": k1, "ovh-node-2": k2})
    msg = commit_message(view=0, seq=1, digest="ee" * 32, replica_id="ovh-node-2")
    ed1, pqc1 = producer_key_b64(k1)
    row = {
        "kind": "commit",
        "protocol": "265-pbft-block-finality",
        "message": msg,
        "replica_id": "ovh-node-2",
        "signature": sign_message(k1, msg),
        "producer_ed25519_b64": ed1,
        "producer_pqc_b64": pqc1,
        "view": 0,
        "seq": 1,
        "digest": "ee" * 32,
    }
    assert verify_commit(row) is False
    store = PbftViewStore(tmp_path / "vc", replica_id="ovh-node-2")
    vc = store.emit_view_change(k1, view=1, height=1, last_hash="ff" * 32, reason="x")
    # emit uses chain K1 but replica_id ovh-node-2 — self-check should fail once bound
    assert verify_view_change(vc) is False


def test_accept_prepare_returns_binding_reason(tmp_path: Path) -> None:
    k1 = _chain(tmp_path, "k1")
    k2 = _chain(tmp_path, "k2")
    register_chain_replicas({"ovh-node-1": k1, "ovh-node-2": k2})
    d = tmp_path / "log"
    vs = PbftViewStore(d, replica_id="ovh-node-4")
    store = PbftFinalityStore(d, replica_id="ovh-node-4", view_store=vs)
    msg = prepare_message(view=0, seq=1, digest="11" * 32, replica_id="ovh-node-2")
    ed1, pqc1 = producer_key_b64(k1)
    row = {
        "kind": "prepare",
        "protocol": "265-pbft-block-finality",
        "message": msg,
        "replica_id": "ovh-node-2",
        "signature": sign_message(k1, msg),
        "producer_ed25519_b64": ed1,
        "producer_pqc_b64": pqc1,
        "view": 0,
        "seq": 1,
        "digest": "11" * 32,
    }
    got = store.accept_prepare(row)
    assert got.get("ok") is not True
    assert got.get("reason") == "invalid_replica_key_binding"


def test_binding_enforced_by_official_marker_not_ip(tmp_path: Path, monkeypatch) -> None:
    from src.artcb.consensus import replica_identity as rid

    monkeypatch.delenv("ARTCB_REQUIRE_REPLICA_BINDING", raising=False)
    monkeypatch.delenv("ARTCB_REPLICA_REGISTRY", raising=False)
    monkeypatch.setattr(rid, "on_official_compute", lambda: False)
    marker = tmp_path / "official_node"
    marker.write_text("aws-node-3\n", encoding="utf-8")
    monkeypatch.setattr(rid, "OFFICIAL_NODE_MARKER", marker)
    assert rid.binding_enforced() is True
    marker.write_text("not-a-node\n", encoding="utf-8")
    assert rid.binding_enforced() is False


def test_official_ids_still_four() -> None:
    from artcb.node_registry import official_pbft_replica_ids

    assert OFFICIAL_COMPUTE_NODE_IDS == ("ovh-node-1", "ovh-node-2", "aws-node-3", "ovh-node-4")
    ids = official_pbft_replica_ids()
    assert primary_of(15) == ids[15 % len(ids)]


def test_r272_equivocation_not_reopened(tmp_path: Path) -> None:
    """Same-view distinct digest stays equivocation — not an identity bug."""
    d = tmp_path / "ovh-node-1"
    chain = ChainManager(d / "blocks.jsonl", key_path=d / "k", enable_security=False)
    vs = PbftViewStore(d, replica_id="ovh-node-1")
    store = PbftFinalityStore(d, replica_id="ovh-node-1", view_store=vs)
    a = json.loads(
        chain.append_block(
            graph_id="A", graph_root="r", pol_score=0.1, visibility="public", source="273", dry_run=True
        ).to_json_line()
    )
    b = dict(a)
    b["hash"] = "b" * 64
    store.emit_preprepare(chain, block=a)
    try:
        store.emit_preprepare(chain, block=b)
        raised = ""
    except ValueError as exc:
        raised = str(exc)
    assert raised == "equivocation"
