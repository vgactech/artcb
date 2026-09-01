#!/usr/bin/env python3
"""Simulation 193 — OVH4 Eco measure + gated order.

Never invent SHA, TPM, or a 10 EUR prepaid.
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
from artcb.devnet_validation import DECISIONS_193, certification_gate, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402
from ovh4_baremetal_order import quote_ovh4  # noqa: E402

SIM_ID = "e2e193_ovh4_baremetal_order"


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{stamp}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="193-ovh4-baremetal-order",
        simulation_id=SIM_ID,
        seed=193,
        script_path=Path(__file__),
        extra={"branch_expected": "cursor/ovh4-baremetal-order-e867"},
    )
    _write(out_dir, "00_manifest.json", manifest)
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())

    quoted = quote_ovh4(want_order=True)
    _write(out_dir, "22_ovh4_order.json", quoted)

    gate = certification_gate(
        {letter: "PASS" for letter in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    failures: list[str] = []
    if quoted.get("order", {}).get("executed"):
        failures.append("order_executed_without_prepaid")
    if quoted.get("invented_balance"):
        failures.append("invented_balance")
    if quoted.get("invented_tpm"):
        failures.append("invented_tpm")
    if NODES["ovh-baremetal-1"].ssh_host is not None:
        failures.append("baremetal_ip_invented")
    if NODES["ovh-node-4"].ssh_host != "91.134.45.8":
        failures.append("ovh4_vm_moved")
    if quoted.get("nic") not in {None, "xy4589-ovh"}:
        failures.append("wrong_nic")
    if quoted.get("nic") == "vc491276-ovh":
        failures.append("ordered_on_ovh2")
    if gate.get("certified_distributed_mainnet"):
        failures.append("certified_true")
    prepaid = quoted.get("ovhAccount_prepaid_eur")

    summary = {
        "sim": SIM_ID,
        "decisions_193": DECISIONS_193,
        "nic": quoted.get("nic"),
        "me_http": quoted.get("me_http"),
        "dedicated_count": (quoted.get("dedicated_servers") or {}).get("count"),
        "prepaid_eur": prepaid,
        "cheapest_catalog": (quoted.get("sku_scan") or {}).get("cheapest_catalog"),
        "cheapest_in_stock": (quoted.get("sku_scan") or {}).get("cheapest_in_stock"),
        "order_executed": quoted.get("order", {}).get("executed"),
        "blocked_reason": quoted.get("order", {}).get("blocked_reason"),
        "certification_gate": gate,
        "failures": failures,
        "ovh4_vm_untouched": True,
        "install_sh": False,
        "init_genesis": False,
        "note": "D-047: Public Cloud 10 EUR is not Eco tender. No dedicated ordered.",
    }
    _write(out_dir, "24_summary.json", summary)
    _write(out_dir, "00_manifest.json", finish(manifest))
    print(dumps({"out_dir": str(out_dir), "failures": failures, "summary": summary}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
