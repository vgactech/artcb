#!/usr/bin/env python3
"""Simulation 194 — OVH4 Eco GO measure (checkout only with --order --go).

Never invent SHA, TPM, IP, or a prepaid balance.
Does not run install.sh, init_genesis.py, or init-node.
Does not destroy 91.134.45.8. Does not deploy origin/main.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from artcb.crypto_policy import PROTOCOL_VERSION  # noqa: E402
from artcb.devnet_validation import DECISIONS_194, certification_gate, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402
from ovh_baremetal_quote import eco_catalog_intervals  # noqa: E402
from ovh4_baremetal_order import decide_order, pick_cheapest_combo, quote_ovh4  # noqa: E402

SIM_ID = "e2e194_ovh4_baremetal_go"


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{stamp}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="194-ovh4-baremetal-go",
        simulation_id=SIM_ID,
        seed=194,
        script_path=Path(__file__),
        extra={"branch_expected": "cursor/ovh4-baremetal-go-3c95"},
    )
    _write(out_dir, "00_manifest.json", manifest)
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())

    sku = {
        "planCode": "24sk50-v1",
        "total_eur": 26.99,
        "in_stock": True,
        "fqn": "24sk50-v1.ram-32g-ecc-2400.softraid-3x4000sa",
        "datacenter": "rbx",
    }
    dedicated_empty = {"http": 200, "count": 0, "servers": [], "eco_in_delivery": False}
    without_go = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=0.0,
        dedicated=dedicated_empty,
        sku=sku,
        want_order=True,
        operator_go=False,
    )
    with_go = decide_order(
        nic="xy4589-ovh",
        me_http=200,
        prepaid_eur=0.0,
        dedicated=dedicated_empty,
        sku=sku,
        want_order=True,
        operator_go=True,
    )
    picked = pick_cheapest_combo(
        [
            {"planCode": "syd", "total_eur": 18.99, "dcs_fr": [], "datacenter": "syd"},
            {"planCode": "24sk50-v1", "total_eur": 26.99, "dcs_fr": [{"dc": "rbx"}], "datacenter": "rbx"},
        ]
    )
    fixture_intervals = eco_catalog_intervals(
        {
            "plans": [
                {
                    "planCode": "25skb012",
                    "invoiceName": "KS-B",
                    "pricings": [
                        {
                            "interval": 1,
                            "intervalUnit": "month",
                            "capacities": ["renew"],
                            "price": 999000000,
                            "description": "rental for 1 month",
                        }
                    ],
                }
            ]
        }
    )
    # Live measure only. want_order=False — never POST checkout from this sim.
    live = quote_ovh4(want_order=False, operator_go=False)
    _write(
        out_dir,
        "22_gates.json",
        {
            "without_go": without_go,
            "with_go": with_go,
            "picked": picked,
            "fixture_intervals": fixture_intervals,
        },
    )
    _write(out_dir, "23_live_measure.json", live)

    gate = certification_gate(
        {letter: "PASS" for letter in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    failures: list[str] = []
    if without_go.get("executed") or with_go.get("executed"):
        failures.append("pure_gate_executed")
    if without_go.get("blocked_reason") != "prepaid_below_sku":
        failures.append("go_flag_not_required")
    if with_go.get("blocked_reason") is not None:
        failures.append("go_did_not_open_card_tender")
    if (with_go.get("would_order") or {}).get("tender") != "preferred_payment_method_CREDIT_CARD":
        failures.append("tender_not_card")
    if picked is None or picked.get("datacenter") != "rbx":
        failures.append("fr_not_preferred")
    if NODES["ovh-node-4"].ssh_host != "91.134.45.8":
        failures.append("ovh4_vm_moved")
    if NODES["ovh-baremetal-1"].ssh_host == "91.134.45.8":
        failures.append("baremetal_is_vm")
    if gate.get("certified_distributed_mainnet"):
        failures.append("certified_true")
    if live.get("order", {}).get("executed"):
        failures.append("live_measure_executed_order")
    if live.get("nic") not in {None, "xy4589-ovh"}:
        failures.append("wrong_nic")
    intervals = live.get("catalog_intervals") or {}
    existing = live.get("existing_eco_orders") or {}

    summary = {
        "sim": SIM_ID,
        "decisions_194": DECISIONS_194,
        "without_go": without_go.get("blocked_reason"),
        "with_go_tender": (with_go.get("would_order") or {}).get("tender"),
        "picked_dc": None if picked is None else picked.get("datacenter"),
        "live_nic": live.get("nic"),
        "live_me_http": live.get("me_http"),
        "live_dedicated_count": (live.get("dedicated_servers") or {}).get("count"),
        "live_prepaid_eur": live.get("ovhAccount_prepaid_eur"),
        "live_eco_order_ids": [r.get("orderId") for r in (existing.get("eco_orders") or [])],
        "live_billing": intervals.get("billing"),
        "live_hourly_exists": intervals.get("hourly_exists"),
        "live_order_executed": live.get("order", {}).get("executed"),
        "certification_gate": gate,
        "failures": failures,
        "ovh4_vm_untouched": True,
        "install_sh": False,
        "init_genesis": False,
        "note": (
            "D-048 GO checkout 258100013 then D-049: Eco is month_only; "
            "do not POST a second --order. This sim never POSTs checkout."
        ),
    }
    _write(out_dir, "24_summary.json", summary)
    _write(out_dir, "00_manifest.json", finish(manifest))
    print(dumps({"out_dir": str(out_dir), "failures": failures, "summary": summary}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
