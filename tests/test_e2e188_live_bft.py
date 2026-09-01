"""Phase 188 — live BFT N/F/Q and local double-settle. No secrets."""

from __future__ import annotations

from pathlib import Path

from artcb.consensus.live_bft import LiveBftEngine, n_f_q
from artcb.consensus_spec import FOUR_NODE_BFT_F, FOUR_NODE_BFT_Q, LIVE_BFT_IMPLEMENTED
from artcb.devnet_validation import DECISIONS_188, certification_gate, public_lock

ROOT = Path(__file__).resolve().parents[1]


def test_n_f_q_four_nodes_is_f1_q3() -> None:
    n, f, q = n_f_q(4)
    assert n == 4
    assert f == FOUR_NODE_BFT_F == 1
    assert q == FOUR_NODE_BFT_Q == 3
    n3, f3, q3 = n_f_q(3)
    assert f3 is None
    assert q3 == 2


def test_local_double_proposal_second_fails(tmp_path: Path) -> None:
    engine = LiveBftEngine(tmp_path, node_id="n1")
    first = engine.propose(
        work_id="W-188",
        snapshot_digest="digest-a",
        peers=[],
        self_host="127.0.0.1",
    )
    assert first["ok"] is False
    assert first["reason"] == "n_lt_4_not_bft"
    assert engine.prepare_local("W-188", "sid-one") == "prepared"
    assert engine.prepare_local("W-188", "sid-two") == "reserved_other"
    committed = engine.commit_local("W-188", "sid-one", 1)
    assert committed["ok"] is True
    assert engine.prepare_local("W-188", "sid-one") == "already_settled"


def test_d042_does_not_invent_mainnet() -> None:
    assert LIVE_BFT_IMPLEMENTED is True
    text = DECISIONS_188["D-042"]
    assert "Not certified mainnet" in text
    assert "174-devnet-1" in text
    assert "D-026" in text
    lock = public_lock()
    assert lock["distributed_certified"] is False
    assert lock["economic_v_locked"] is True
    gate = certification_gate({"DV-03": "PASS", "DV-04": "PASS"})
    assert gate["certified_distributed_mainnet"] is False
    assert "DV-05" in gate["dv_not_pass"]


def test_sim188_refuses_invented_mainnet_rename() -> None:
    sim = (ROOT / "scripts" / "run_sim188_dv05_live_bft.py").read_text(encoding="utf-8")
    assert "Never invent SHA" in sim
    assert "certified_distributed_mainnet" in sim
    assert "honest" in sim
    assert "double-proposal" in sim or "double_proposal" in sim
