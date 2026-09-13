#!/usr/bin/env python3
"""R337 — CLI for rule telemetry (local). Never invents applied_confirmed."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from artcb.rules.telemetry import (  # noqa: E402
    RuleEvent,
    append_event,
    badge_snapshot,
    coverage_gap,
    load_registry,
    mark_turn_seen,
    summarize,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="ARTCB rule telemetry")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("summary")
    sub.add_parser("badge")
    p_seen = sub.add_parser("seen")
    p_seen.add_argument("--rules", required=True, help="comma rule ids")
    p_seen.add_argument("--turn", default="")
    p_seen.add_argument("--task", default="")

    p_ev = sub.add_parser("event")
    p_ev.add_argument("--rule", required=True)
    p_ev.add_argument("--kind", required=True)
    p_ev.add_argument("--turn", default="")
    p_ev.add_argument("--task", default="")
    p_ev.add_argument("--evidence-kind", default="")
    p_ev.add_argument("--evidence-ref", default="")
    p_ev.add_argument("--note", default="")
    p_ev.add_argument("--claim-only", action="store_true")

    p_gap = sub.add_parser("coverage-gap")
    p_gap.add_argument("--expected", required=True)
    p_gap.add_argument("--checked", default="")
    p_gap.add_argument("--turn", default="")
    p_gap.add_argument("--task", default="")

    args = ap.parse_args()
    if args.cmd == "summary":
        print(json.dumps(summarize(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "badge":
        print(json.dumps(badge_snapshot(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "seen":
        ids = [x.strip() for x in args.rules.split(",") if x.strip()]
        turn = args.turn or f"turn_{time.time_ns()}"
        rows = mark_turn_seen(ids, turn_id=turn, task_type=args.task)
        print(json.dumps({"wrote": len(rows), "turn_id": turn}, indent=2))
        return 0
    if args.cmd == "event":
        row = append_event(
            RuleEvent(
                rule_id=args.rule,
                kind=args.kind,
                turn_id=args.turn or f"turn_{time.time_ns()}",
                task_type=args.task,
                evidence_kind=args.evidence_kind,
                evidence_ref=args.evidence_ref,
                note=args.note,
                agent_claim_only=bool(args.claim_only),
            )
        )
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "coverage-gap":
        exp = [x.strip() for x in args.expected.split(",") if x.strip()]
        chk = [x.strip() for x in args.checked.split(",") if x.strip()]
        row = coverage_gap(
            expected=exp,
            checked=chk,
            turn_id=args.turn or f"turn_{time.time_ns()}",
            task_type=args.task,
        )
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
