"""GO-E runtime : câblé, interrupteurs off, aucun append."""

from __future__ import annotations

from src.artcb.p2p.producer_runtime import (
    ProducerFailoverRuntime,
    failover_live_enabled,
    failover_produce_enabled,
)


def test_defaults_are_off() -> None:
    assert failover_live_enabled({}) is False
    assert failover_produce_enabled({}) is False


def test_produce_requires_live() -> None:
    env = {"ARTCB_PRODUCER_FAILOVER_PRODUCE": "true"}
    assert failover_produce_enabled(env) is False
    env["ARTCB_PRODUCER_FAILOVER_LIVE"] = "true"
    assert failover_produce_enabled(env) is True


def test_runtime_default_has_no_monitor() -> None:
    rt = ProducerFailoverRuntime("artcb1node_x", env={})
    assert rt.monitor is None
    assert rt.status()["will_append_blocks"] is False
    assert rt.status()["append_implemented"] is False
    assert rt.maybe_produce() == {"appended": False, "reason": "failover_live_off"}


def test_live_observe_still_refuses_append() -> None:
    rt = ProducerFailoverRuntime(
        "artcb1node_x",
        env={"ARTCB_PRODUCER_FAILOVER_LIVE": "true"},
    )
    assert rt.monitor is not None
    assert rt.maybe_produce()["reason"] == "failover_produce_off"
    rt.note_public_block(node_id="artcb1node_y", block_hash="abc", block_index=4)
    assert rt.monitor.current_producer() == "artcb1node_y"


def test_both_flags_still_refuse_append() -> None:
    rt = ProducerFailoverRuntime(
        "artcb1node_x",
        env={
            "ARTCB_PRODUCER_FAILOVER_LIVE": "true",
            "ARTCB_PRODUCER_FAILOVER_PRODUCE": "true",
        },
    )
    out = rt.maybe_produce()
    assert out["appended"] is False
    assert out["reason"] == "append_not_implemented"
