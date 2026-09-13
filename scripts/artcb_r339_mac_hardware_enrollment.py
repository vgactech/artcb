#!/usr/bin/env python3
"""R339 — collect Mac inventory + H1 NodeKey enrollment bundle (no H3 claim)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from artcb.platform.mac_hardware_inventory import (  # noqa: E402
    build_enrollment_bundle,
    collect_mac_hardware_inventory,
    persist_inventory,
)

try:
    from artcb.rules.telemetry import RuleEvent, append_event
except Exception:
    RuleEvent = None  # type: ignore
    append_event = None  # type: ignore


def main() -> int:
    inv = collect_mac_hardware_inventory()
    path = persist_inventory(inv)
    bundle = build_enrollment_bundle(inv)
    out_dir = ROOT / "logs" / "R339"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mac_inventory.json").write_text(json.dumps(inv.to_public_dict(), indent=2) + "\n")
    (out_dir / "enrollment_bundle.json").write_text(json.dumps(bundle, indent=2) + "\n")
    print(json.dumps({
        "assurance_h": inv.assurance_h,
        "native_c04": inv.native_c04,
        "fingerprint_v2_16": (inv.fingerprint_v2 or "")[:16],
        "platform": inv.platform,
        "security": inv.security,
        "node_pub_16": bundle["node_key"]["public_key_b64"][:16],
        "inventory_path": str(path),
        "certified_100": False,
        "c04_pass": False,
    }, indent=2))
    if append_event and RuleEvent:
        append_event(RuleEvent(
            rule_id="RT-HW-H1",
            kind="applied_confirmed",
            turn_id=f"R339_{inv.ts_ns}",
            task_type="mac_inventory",
            evidence_kind="measurement_json",
            evidence_ref="logs/R339/mac_inventory.json",
            note=f"assurance={inv.assurance_h}; native_c04={inv.native_c04}",
        ))
        append_event(RuleEvent(
            rule_id="RT-077-C04",
            kind="not_proven",
            turn_id=f"R339_{inv.ts_ns}",
            task_type="mac_inventory",
            evidence_kind="measurement_json",
            evidence_ref="logs/R339/mac_inventory.json",
            note="H1 inventory≠C04/H3",
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
