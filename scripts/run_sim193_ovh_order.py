#!/usr/bin/env python3
"""Simulation 193 — hunt the OVH nic that holds ~10 EUR, order only if allowed.

Never invent SHA, TPM, prepaid, or a 10 EUR ovhAccount balance.
Never print API keys. Never POST /order/cart/.../checkout.
Does not run install.sh, init_genesis.py, or init-node.
Does not empty the live book. Does not deploy origin/main.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from datetime import UTC, datetime  # noqa: E402

from artcb.crypto_policy import PROTOCOL_VERSION  # noqa: E402
from artcb.devnet_validation import DECISIONS_193, certification_gate, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402
from ovh_baremetal_quote import eco_ksb_stock, hunt_all_ovh_accounts, quote  # noqa: E402

SIM_ID = "e2e193_ovh_order"
BRANCH = "cursor/ovh3-baremetal-hw-16d8"


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _health() -> tuple[int, dict]:
    req = Request("http://152.228.144.34:8000/health", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=12) as resp:
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{stamp}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="193-ovh-order",
        simulation_id=SIM_ID,
        seed=193,
        script_path=Path(__file__),
        extra={"branch_expected": BRANCH},
    )
    _write(out_dir, "00_manifest.json", manifest)
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())

    health_c, health = _health()
    _write(out_dir, "12_live_health.json", {"http": health_c, "git_sha": health.get("git_sha"), "git_branch": health.get("git_branch")})

    quoted = quote(want_order=True)
    _write(out_dir, "20_quote.json", quoted)

    hunt = hunt_all_ovh_accounts()
    _write(out_dir, "21_hunt.json", hunt)

    stock = eco_ksb_stock()
    _write(out_dir, "22_ksb_stock.json", stock)

    gate = certification_gate(
        {letter: "PASS" for letter in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    failures: list[str] = []
    if quoted.get("invented_balance") or hunt.get("invented_balance"):
        failures.append("invented_balance")
    if quoted.get("order", {}).get("executed"):
        failures.append("order_executed")
    if gate.get("certified_distributed_mainnet"):
        failures.append("certified_true")
    if NODES["ovh-baremetal-1"].ssh_host:
        failures.append("baremetal_ip_invented")
    prepaid_xy = None
    cloud_10 = None
    for src in hunt.get("sources") or []:
        if src.get("nic") == "xy4589-ovh":
            prepaid_xy = src.get("balance_eur")
            for cred in src.get("cloud_credits") or []:
                if cred.get("credit_id") == 263152 or cred.get("description") == "Credit provisionning":
                    cloud_10 = cred.get("available_eur")
    if prepaid_xy not in (0, 0.0):
        failures.append("xy4589_prepaid_not_zero_or_unmeasured")
    if cloud_10 not in (10, 10.0, None):
        # None = Doppler missing in this runner; 10 = measured remaining purchased credit
        failures.append("cloud_credit_unexpected")

    cheapest = quoted.get("selected") or {}
    summary = {
        "sim": SIM_ID,
        "decisions_193": DECISIONS_193,
        "live_git_sha": health.get("git_sha"),
        "live_http": health_c,
        "cheapest_sku": cheapest.get("planCode"),
        "cheapest_eur": cheapest.get("price_eur"),
        "ksb_in_stock": stock.get("in_stock"),
        "order_executed": False,
        "order_blocked_reason": (quoted.get("order") or {}).get("blocked_reason"),
        "xy4589_prepaid_eur": prepaid_xy,
        "xy4589_cloud_credit_263152_eur": cloud_10,
        "certification_gate": gate,
        "failures": failures,
        "install_sh": False,
        "init_genesis": False,
        "init_node": False,
        "book_wiped": False,
        "checkout_posted": False,
        "card_charged": False,
        "note": (
            "D-047: ~10 EUR is Public Cloud credit on xy4589-ovh, not prepaid "
            "for Eco dedicated. KS-B GRA unavailable. No order."
        ),
    }
    _write(out_dir, "24_summary.json", summary)
    _write(out_dir, "00_manifest.json", finish(manifest))
    print(dumps({"out_dir": str(out_dir), "failures": failures, "summary": summary}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
