"""Simulation 164 e2e protocol — live modules, no economic mocks."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.artcb.chain.manager import ChainManager
from src.artcb.economics.economic_root import economic_root
from src.artcb.economics.human_binding import HumanBindingError
from src.artcb.economics.identity import IdentityError
from src.artcb.economics.owner_decay import fleet_owner_share
from src.artcb.economics.settlement import OwnerCannotCutPaymentError, reject_owner_payment_cut
from src.artcb.mining.identity import enrich_contributors_with_identity
from src.artcb.mining.pipeline import build_contributors
from src.artcb.mining.protocol import ProtocolEngine, ProtocolReject, REJECT_DOUBLE_SETTLEMENT
from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI


def _engine(tmp_path: Path) -> ProtocolEngine:
    chain = ChainManager(
        tmp_path / "blocks.jsonl",
        key_path=tmp_path / "chain.key",
        enable_security=False,
    )
    return ProtocolEngine(tmp_path, chain=chain)


def _people(engine: ProtocolEngine) -> None:
    engine.humans.bootstrap_creator(human_id="H-A", address="A")
    for hid, addr in (("H-B", "B"), ("H-C", "C"), ("H-D", "D")):
        engine.humans.register_candidate(human_id=hid, address=addr)
        engine.humans.creator_direct_validate(hid, creator_id="H-A")
    engine.machines.register(machine_id="M1", owner_address="A")
    engine.machines.register(machine_id="M2", owner_address="A", bound_human_address="B")
    engine.machines.register(machine_id="M3", owner_address="A", bound_human_address="C")
    engine.machines.register(machine_id="M4", owner_address="A", bound_human_address="D")


def test_full_pipeline_conservation_and_21m(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    result = engine.execute_block(
        graph_id="g1",
        graph_root="a" * 64,
        pol_score=0.85,
        work_id="W-1",
        machine_ids=["M1", "M2", "M3", "M4"],
        provider_scores={"A": 1.0},
        interval_seconds=600.0,
    )
    assert result.total_paid_satoshi == result.r_block_satoshi
    assert result.supply_satoshi <= MAX_SUPPLY_SATOSHI
    assert result.h_adult == 4
    assert result.hash_version == 2
    assert len(result.economic_root) == 64
    verify = engine.chain.verify()
    assert verify["valid"] is True


def test_m5_changes_p_n(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    p4 = fleet_owner_share(engine.n_economic("A"))
    engine.humans.register_candidate(human_id="H-E", address="E")
    engine.humans.creator_direct_validate("H-E", creator_id="H-A")
    engine.machines.register(machine_id="M5", owner_address="A", bound_human_address="E")
    p5 = fleet_owner_share(engine.n_economic("A"))
    assert engine.n_economic("A") == 5
    assert p5 < p4


def test_attack_double_binding(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    with pytest.raises(HumanBindingError):
        engine.machines.register(machine_id="MX", owner_address="A", bound_human_address="B")


def test_attack_double_settlement(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    engine.execute_block(
        graph_id="g1",
        graph_root="a" * 64,
        pol_score=0.8,
        work_id="W-dup",
        machine_ids=["M1"],
        interval_seconds=600.0,
    )
    with pytest.raises(ProtocolReject) as exc:
        engine.execute_block(
            graph_id="g2",
            graph_root="b" * 64,
            pol_score=0.8,
            work_id="W-dup",
            machine_ids=["M1"],
            interval_seconds=600.0,
        )
    assert exc.value.code == REJECT_DOUBLE_SETTLEMENT
    assert "REJECT_DOUBLE_SETTLEMENT" in str(exc.value)


def test_attack_owner_cannot_cut(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    with pytest.raises(OwnerCannotCutPaymentError, match="IMPOSSIBLE"):
        reject_owner_payment_cut()
    with pytest.raises(ProtocolReject) as exc:
        engine.execute_block(
            graph_id="g-cut",
            graph_root="c" * 64,
            pol_score=0.8,
            work_id="W-cut",
            machine_ids=["M2"],
            owner_redirect={"M2": "A"},
            interval_seconds=600.0,
        )
    assert "IMPOSSIBLE" in str(exc.value) or exc.value.code.endswith("CUT_PAYMENT")


def test_offline_does_not_shrink_n(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    n0 = engine.n_economic("A")
    engine.heartbeat("M2", online=False, missed_beats=1)
    assert engine.machines.get("M2").status == "GRACE"
    engine.heartbeat("M2", online=False, missed_beats=3)
    assert engine.machines.get("M2").status == "OFFLINE"
    assert engine.n_economic("A") == n0


def test_transfer_recalc_n_and_p(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    n0 = engine.n_economic("A")
    p0 = fleet_owner_share(n0)
    engine.machines.transfer("M2", new_owner="Z")
    assert engine.n_economic("A") == n0 - 1
    assert engine.n_economic("Z") == 1
    assert fleet_owner_share(engine.n_economic("A")) != p0


def test_fake_human_rejected(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    with pytest.raises(IdentityError, match="FAKE_HUMAN"):
        engine.humans.register_candidate(human_id="H-X", address="B")
    with pytest.raises(IdentityError):
        engine.humans.register_candidate(human_id="H-B", address="other")


def test_tamper_economic_root_changes_hash(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    result = engine.execute_block(
        graph_id="g1",
        graph_root="a" * 64,
        pol_score=0.8,
        work_id="W-tamper",
        machine_ids=["M1", "M2"],
        interval_seconds=600.0,
    )
    from src.artcb.chain import ffi

    other = economic_root({"tamper": True})
    assert other != result.economic_root
    recomputed = ffi.build_block_hash(
        result.block_index,
        engine.chain.list_blocks()[-1]["timestamp"],
        engine.chain.list_blocks()[-1]["prev_hash"],
        "a" * 64,
        engine.chain.list_blocks()[-1]["merkle_root"],
        0.8,
        economic_root=other,
    )
    assert recomputed != result.block_hash
    assert engine.chain.verify()["valid"] is True


def test_missing_preblock_requeue_and_jobs(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    small = engine.jobs.submit(provider_address="A", payload="small")
    large = engine.jobs.submit(provider_address="A", payload="large " * 50)
    cancelled = engine.jobs.submit(provider_address="B", payload="bye")
    engine.jobs.cancel(cancelled.job_id)
    assert engine.jobs.get(cancelled.job_id).status == "cancelled"
    result = engine.execute_block(
        graph_id="g-miss",
        graph_root="d" * 64,
        pol_score=0.8,
        work_id="W-miss",
        machine_ids=["M1", "M2"],
        job_id=small.job_id,
        missing_preblock_ids=["pb2"],
        n_partitions=4,
        interval_seconds=600.0,
    )
    assert result.missing_preblocks == ["pb2"]
    assert result.requeued_work_ids
    assert result.total_paid_satoshi == result.r_block_satoshi
    assert result.r_block_satoshi < 50 * 100_000_000
    del large


def test_mining_contributors_carry_identity(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    raw = build_contributors(actor_address="A", pol_score=0.9)
    wired = enrich_contributors_with_identity(
        raw,
        machine_registry=engine.machines,
        human_registry=engine.humans,
        work_registry=engine.works,
        graph_id="g-wire",
    )
    assert all("machine_index" in c and "owner_address" in c for c in wired)
    assert any(c.get("human_id") == "H-A" for c in wired)
    assert all(c.get("work_id") for c in wired)


def test_job_payment_does_not_mint(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    _people(engine)
    before = engine.chain._issued_so_far_satoshi()
    result = engine.execute_block(
        graph_id="g-pay",
        graph_root="e" * 64,
        pol_score=0.8,
        work_id="W-pay",
        machine_ids=["M1"],
        job_payment={"kind": "JobPayment", "mints": False, "payment_intent_id": "pi_test"},
        interval_seconds=600.0,
    )
    assert result.job_payment["mints"] is False
    assert engine.chain._issued_so_far_satoshi() == before + result.r_block_satoshi
    with pytest.raises(ProtocolReject):
        engine.execute_block(
            graph_id="g-pay2",
            graph_root="f" * 64,
            pol_score=0.8,
            work_id="W-pay2",
            machine_ids=["M1"],
            job_payment={"kind": "JobPayment", "mints": True},
            interval_seconds=600.0,
        )


def test_native_c_economic_root_versioning() -> None:
    from src.artcb.chain import ffi
    from src.artcb.economics.economic_root import native_economic_root_available

    assert ffi.has_economic_root_abi() is True
    assert native_economic_root_available() is True
    assert ffi.hash_abi_version() == 2
    h1 = ffi.build_block_hash(0, "ts", "p" * 64, "g" * 64, "m" * 64, 0.81)
    h2 = ffi.build_block_hash(0, "ts", "p" * 64, "g" * 64, "m" * 64, 0.81, economic_root="")
    assert h1 == h2
    a = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7, economic_root="a" * 64)
    b = ffi.build_block_hash(1, "ts", "p" * 64, "g" * 64, "m" * 64, 0.7, economic_root="b" * 64)
    assert a != b


def test_v1_block_still_verifies(tmp_path: Path) -> None:
    chain = ChainManager(tmp_path / "blocks.jsonl", enable_security=False)
    block = chain.append_block(graph_id="g", graph_root="abc", pol_score=0.8)
    assert block.hash_version == 1
    assert chain.verify()["valid"] is True


def test_v2_tamper_economic_root_fails_c_verify(tmp_path: Path) -> None:
    import json

    chain = ChainManager(tmp_path / "blocks.jsonl", enable_security=False)
    chain.append_block(
        graph_id="g",
        graph_root="abc",
        pol_score=0.8,
        h_adult=4,
        contributors=[
            {
                "address": "A",
                "pol_score": 1.0,
                "signature": "s",
                "machine_id": "A1",
                "owner_address": "A",
                "machine_index": 1,
            }
        ],
    )
    assert chain.verify()["valid"] is True
    lines = chain.blocks_path.read_text(encoding="utf-8").strip().splitlines()
    row = json.loads(lines[0])
    assert row.get("hash_version") == 2
    row["economic_root"] = "f" * 64
    chain.blocks_path.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")
    assert chain.verify()["valid"] is False


def test_stripe_webhook_idempotent(tmp_path: Path) -> None:
    from src.artcb.payments.stripe_jobs import (
        BLOCK_REWARD_KIND,
        JOB_PAYMENT_KIND,
        StripeJobError,
        StripeJobLedger,
        create_priority_job_payment,
        handle_stripe_webhook,
    )

    ledger = StripeJobLedger(tmp_path / "stripe.json")
    event = {
        "id": "evt_1",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_1",
                "status": "succeeded",
                "metadata": {
                    "artcb_kind": JOB_PAYMENT_KIND,
                    "artcb_job_id": "job_1",
                    "artcb_mints": "false",
                },
            }
        },
    }
    first = handle_stripe_webhook(event, ledger=ledger)
    second = handle_stripe_webhook(event, ledger=ledger)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert first["mints"] is False
    assert first["distinct_from"] == BLOCK_REWARD_KIND
    with pytest.raises(StripeJobError, match="anti-spam"):
        create_priority_job_payment(job_id="j", amount_cents=1)


def test_oracle_zero_rejected_and_explicit_price_converts() -> None:
    from src.artcb.economics.fees import quote_fee_satoshi, usd_to_artcb_satoshi
    from src.artcb.economics.oracle import OracleError

    with pytest.raises((ValueError, OracleError)):
        usd_to_artcb_satoshi(0.000311, artcb_usd_price=0)
    fee = quote_fee_satoshi(congestion=0.0, artcb_usd_price=1.0)
    assert fee["artcb_usd"] == 1.0
    assert fee["fee_satoshi"] >= 0
    assert fee["mints"] is False
