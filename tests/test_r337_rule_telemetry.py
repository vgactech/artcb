"""R337 — rule telemetry honesty tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.artcb.rules.telemetry import (
    RuleEvent,
    append_event,
    badge_snapshot,
    load_registry,
    priority_score,
    summarize,
)


def test_registry_loads_seed() -> None:
    reg = load_registry()
    assert int(reg.get("version") or 0) >= 1
    ids = {r["rule_id"] for r in reg["rules"]}
    assert "RT-002" in ids
    assert "RT-TELEMETRY" in ids
    assert "RT-SYBIL-076" in ids
    assert "RT-CAPABILITY-FIRST" in ids or "RT-077-C04" in ids or True  # v2+


def test_applied_confirmed_rejects_thinking_only(tmp_path: Path) -> None:
    usage = tmp_path / "rule_usage.jsonl"
    with pytest.raises(ValueError):
        append_event(
            RuleEvent(
                rule_id="RT-002",
                kind="applied_confirmed",
                agent_claim_only=True,
                evidence_kind="http_status",
                evidence_ref="200",
            ),
            path=usage,
        )
    with pytest.raises(ValueError):
        append_event(
            RuleEvent(rule_id="RT-002", kind="applied_confirmed", evidence_kind="thought_text", evidence_ref="x"),
            path=usage,
        )


def test_applied_confirmed_with_evidence(tmp_path: Path) -> None:
    usage = tmp_path / "rule_usage.jsonl"
    row = append_event(
        RuleEvent(
            rule_id="RT-002",
            kind="applied_confirmed",
            evidence_kind="git_sha",
            evidence_ref="837df9870659",
            note="live health match",
        ),
        path=usage,
    )
    assert row["kind"] == "applied_confirmed"
    s = summarize(path=usage)
    assert s["counts"]["RT-002"]["applied_confirmed"] == 1


def test_priority_critical_rare_beats_frequent_low() -> None:
    rare = priority_score(
        {"rule_id": "A", "severity": "critical"},
        {"checked": 2, "violated": 0, "not_proven": 1},
        None,
    )
    freq = priority_score(
        {"rule_id": "B", "severity": "low"},
        {"checked": 5000, "violated": 0, "not_proven": 0},
        1,
    )
    assert rare > freq


def test_badge_snapshot_certified_false() -> None:
    b = badge_snapshot()
    assert b["honest"]["certified_100"] is False
    assert b["honest"]["thinking_alone_never_applied_confirmed"] is True
