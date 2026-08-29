"""Simulation 167 units — snapshot, SettlementID, HBP ratio, oracle quorum."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.artcb.chain.manager import ChainManager
from src.artcb.economics.economic_snapshot import (
    AlreadySettled,
    EpochCoordinator,
    SettlementLedger,
    settlement_id,
)
from src.artcb.economics.hbp import hbp_rate, hbp_rate_from_ratio
from src.artcb.economics.oracle import oracle_median_or_unavailable
from src.artcb.economics.owner_decay import payout_owner_share
from src.artcb.mining.protocol import ProtocolEngine, ProtocolReject, REJECT_DOUBLE_SETTLEMENT


def _engine(tmp_path: Path) -> ProtocolEngine:
    chain = ChainManager(
        tmp_path / "blocks.jsonl",
        key_path=tmp_path / "chain.key",
        enable_security=True,
    )
    return ProtocolEngine(tmp_path, chain=chain)


def _people(engine: ProtocolEngine) -> None:
    engine.humans.bootstrap_creator(human_id="H-A", address="A")
    engine.humans.register_candidate(human_id="H-B", address="B")
    engine.humans.creator_direct_validate("H-B", creator_id="H-A")
    engine.machines.register(machine_id="M1", owner_address="A")
    engine.machines.register(machine_id="M2", owner_address="A", bound_human_address="B")


def test_settlement_id_deterministic() -> None:
    a = settlement_id(work_id="W", snapshot_digest="abc", protocol_version="167")
    b = settlement_id(work_id="W", snapshot_digest="abc", protocol_version="167")
    c = settlement_id(work_id="W", snapshot_digest="abd", protocol_version="167")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_ledger_rejects_second_consume(tmp_path: Path) -> None:
    ledger = SettlementLedger(tmp_path / "s.json")
    ledger.consume("sid1", work_id="W-X", node_id="A", epoch=1)
    with pytest.raises(AlreadySettled):
        ledger.consume("sid1", work_id="W-X", node_id="B", epoch=1)
    with pytest.raises(AlreadySettled):
        ledger.consume("sid2-different-snapshot", work_id="W-X", node_id="C", epoch=1)
    assert ledger.count_for_work("W-X") == 1


def test_snapshot_freezes_n_across_queued_transfer(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    coord = EpochCoordinator(grace_seconds=1)
    snap1 = coord.begin_epoch(
        machines=engine.machines,
        humans=engine.humans,
        parent_root="0" * 64,
        work_ids_open=[],
        demographic_digest="d" * 64,
    )
    n1 = snap1.n_economic("A")
    assert n1 == 2
    assert payout_owner_share(is_first_machine=True, n_economic=n1) == 1.0
    coord.queue_transfer("M2", new_owner="B", bound_human_address="B")
    assert engine.n_economic("A") == n1
    assert snap1.n_economic("A") == n1
    snap2 = coord.begin_epoch(
        machines=engine.machines,
        humans=engine.humans,
        parent_root="1" * 64,
        work_ids_open=[],
        demographic_digest="d" * 64,
    )
    assert snap2.n_economic("A") < n1
    assert snap1.n_economic("A") == n1


def test_protocol_engine_uses_snapshot_and_rejects_dup(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    coord = EpochCoordinator()
    snap = coord.begin_epoch(
        machines=engine.machines,
        humans=engine.humans,
        parent_root="0" * 64,
        work_ids_open=["W-1"],
        demographic_digest="d" * 64,
    )
    ledger = SettlementLedger(tmp_path / "led.json")
    first = engine.execute_block(
        graph_id="g1",
        graph_root="a" * 64,
        pol_score=0.8,
        work_id="W-1",
        machine_ids=["M1", "M2"],
        interval_seconds=600.0,
        epoch_snapshot=snap,
        settlement_ledger=ledger,
        node_id="A",
    )
    assert first.total_paid_satoshi == first.r_block_satoshi
    assert first.phases["snapshot"]["settlement_id"]
    with pytest.raises(ProtocolReject) as exc:
        engine.execute_block(
            graph_id="g2",
            graph_root="b" * 64,
            pol_score=0.8,
            work_id="W-1",
            machine_ids=["M1", "M2"],
            interval_seconds=600.0,
            epoch_snapshot=snap,
            settlement_ledger=ledger,
            node_id="B",
        )
    assert exc.value.code == REJECT_DOUBLE_SETTLEMENT


def test_hbp_ratio_provisional_does_not_change_live_zero() -> None:
    live = hbp_rate(h_adult=0)
    ratio = hbp_rate_from_ratio(h_verified=0, h_adult_max=5_820_000_000)
    assert live == pytest.approx(0.10)
    assert ratio == pytest.approx(0.10)


def test_oracle_unavailable_never_invents() -> None:
    c = oracle_median_or_unavailable([None, 0, None], min_sources=2)
    assert c.status == "OracleUnavailable"
    assert c.median is None
    assert c.invented is False
    q = oracle_median_or_unavailable([2.0, 4.0], min_sources=2)
    assert q.status == "quorum"
    assert q.median == 3.0
