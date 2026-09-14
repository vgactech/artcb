"""R344 — document telemetry counter semantics (applied vs applied_confirmed)."""

from pathlib import Path

from src.artcb.rules.telemetry import CONFIRMED_EVIDENCE, RuleEvent, append_event, summarize


def test_applied_confirmed_independent_of_applied(tmp_path: Path) -> None:
    usage = tmp_path / "usage.jsonl"
    # Confirm without any prior "applied" event — allowed by design
    append_event(
        RuleEvent(
            rule_id="RT-CORPUS-MAP",
            kind="applied_confirmed",
            turn_id="r344",
            evidence_kind="measurement_json",
            evidence_ref=str(usage),
            note="independent evidence path",
        ),
        path=usage,
    )
    s = summarize(path=usage)
    counts = s["counts"]["RT-CORPUS-MAP"]
    assert counts.get("applied", 0) == 0
    assert counts.get("applied_confirmed", 0) == 1
    assert "measurement_json" in CONFIRMED_EVIDENCE


def test_thinking_only_cannot_confirm(tmp_path: Path) -> None:
    usage = tmp_path / "usage.jsonl"
    try:
        append_event(
            RuleEvent(
                rule_id="RT-TELEMETRY",
                kind="applied_confirmed",
                turn_id="r344",
                agent_claim_only=True,
                evidence_kind="measurement_json",
                evidence_ref="x",
            ),
            path=usage,
        )
        raised = False
    except ValueError:
        raised = True
    assert raised is True
