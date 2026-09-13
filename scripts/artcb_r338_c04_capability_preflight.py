#!/usr/bin/env python3
"""R338 — C04 capability preflight (capability-first, no fake TPM)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from artcb.platform.capability_discovery import write_report  # noqa: E402

try:
    from artcb.rules.telemetry import RuleEvent, append_event
except Exception:  # noqa: BLE001
    RuleEvent = None  # type: ignore
    append_event = None  # type: ignore


def main() -> int:
    dest = ROOT / "logs" / "R338" / "mac_c04_capability.json"
    data = write_report(dest)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    if append_event and RuleEvent:
        append_event(
            RuleEvent(
                rule_id="RT-077-C04",
                kind="checked",
                turn_id=f"R338_{data['ts_ns']}",
                task_type="c04_capability_discovery",
                evidence_kind="measurement_json",
                evidence_ref=str(dest.relative_to(ROOT)),
                note=data.get("C04_verdict"),
            )
        )
        kind = "applied_confirmed" if data.get("C04_verdict") == "UNSUPPORTED_HARDWARE" else "not_proven"
        # UNSUPPORTED is a confirmed discovery result (not a C04 PASS)
        append_event(
            RuleEvent(
                rule_id="RT-077-C04",
                kind=kind if kind != "applied_confirmed" else "not_proven",
                turn_id=f"R338_{data['ts_ns']}",
                task_type="c04_capability_discovery",
                evidence_kind="measurement_json",
                evidence_ref=str(dest.relative_to(ROOT)),
                note="C04 itself remains unsatisfied; discovery confirmed UNSUPPORTED on this Mac",
            )
        )
        if data.get("C04_verdict") == "UNSUPPORTED_HARDWARE":
            append_event(
                RuleEvent(
                    rule_id="RT-CAPABILITY-FIRST",
                    kind="applied_confirmed",
                    turn_id=f"R338_{data['ts_ns']}",
                    task_type="c04_capability_discovery",
                    evidence_kind="measurement_json",
                    evidence_ref=str(dest.relative_to(ROOT)),
                    note="stopped_before_fake_tpm_workaround",
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
