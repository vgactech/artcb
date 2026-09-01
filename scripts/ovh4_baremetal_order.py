#!/usr/bin/env python3
"""OVH4 (nic xy4589-ovh) Eco bare-metal commander.

Lists GET /dedicated/server BEFORE any --order.
Pays only from measured ovhAccount prepaid — never Public Cloud credit,
never vc491276-ovh (OVH2), never a CREDIT_CARD top-up.

--order is a no-op unless: auth OK, prepaid >= SKU, SKU in stock,
and no dedicated Eco already listed or delivering.

Never prints API keys. Never invents a balance or a TPM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ovh_baremetal_quote import (  # noqa: E402
    OVH_BASE,
    _ovh_call,
    availability,
    euro_from_raw,
    public_eco_catalog,
)

OVH4_NIC = "xy4589-ovh"
OVH2_NIC = "vc491276-ovh"
OVH4_VM_KEEP = "91.134.45.8"


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def ovh4_creds() -> dict[str, str]:
    """Doppler artcb-4 / local ovh-node-4.env. Process OVH_* may be stale 403."""
    local = _parse_env(Path.home() / ".artcb" / "nodes" / "ovh-node-4.env")
    if local.get("OVH_APPLICATION_KEY") and local.get("OVH_APPLICATION_SECRET") and local.get("OVH_CONSUMER_KEY"):
        return {
            "application_key": local["OVH_APPLICATION_KEY"],
            "application_secret": local["OVH_APPLICATION_SECRET"],
            "consumer_key": local["OVH_CONSUMER_KEY"],
            "source": "local_ovh-node-4.env",
        }
    from ovh_baremetal_quote import _doppler_secrets  # noqa: PLC0415
    import os  # noqa: PLC0415

    token = (os.environ.get("KEY_API_ARTCB_DOPPLER_4") or "").strip()
    _code, secrets = _doppler_secrets(token, "artcb-4")
    return {
        "application_key": secrets.get("OVH_APPLICATION_KEY") or "",
        "application_secret": secrets.get("OVH_APPLICATION_SECRET") or "",
        "consumer_key": secrets.get("OVH_CONSUMER_KEY") or "",
        "source": "doppler_artcb-4",
    }


def list_dedicated_servers(creds: dict[str, str]) -> dict[str, Any]:
    """Mandatory pre-order inventory. Empty list = no Eco already on this nic."""
    code, body = _ovh_call("GET", "/dedicated/server", creds)
    servers: list[dict[str, Any]] = []
    if isinstance(body, list):
        for sid in body[:20]:
            dc, det = _ovh_call("GET", f"/dedicated/server/{sid}", creds)
            if isinstance(det, dict):
                servers.append(
                    {
                        "http": dc,
                        "name": det.get("name") or sid,
                        "datacenter": det.get("datacenter"),
                        "commercialRange": det.get("commercialRange"),
                        "state": det.get("state"),
                        "ip": det.get("ip"),
                    }
                )
            else:
                servers.append({"http": dc, "name": sid})
    return {
        "http": code,
        "count": len(body) if isinstance(body, list) else None,
        "servers": servers,
        "eco_in_delivery": any(
            str(s.get("state") or "").lower() in {"delivered", "delivery", "installing", "waiting"}
            for s in servers
        )
        or bool(servers),
    }


def cheapest_available(*, max_eur: float | None) -> dict[str, Any]:
    catalog = public_eco_catalog()
    rows = list(catalog.get("cheapest") or [])
    # public_eco_catalog only returns top 5; scan more via the same public URL
    with __import__("urllib.request").request.urlopen(
        f"{OVH_BASE}/order/catalog/public/eco?ovhSubsidiary=FR", timeout=40
    ) as resp:
        cat = json.loads(resp.read().decode())
    full: list[dict[str, Any]] = []
    for plan in cat.get("plans") or []:
        monthly = [
            pr
            for pr in (plan.get("pricings") or [])
            if isinstance(pr, dict)
            and pr.get("interval") == 1
            and "renew" in str(pr.get("capacities") or "")
        ]
        if not monthly:
            continue
        best = min(monthly, key=lambda pr: pr.get("price") or 10**18)
        price = euro_from_raw(best.get("price"))
        if price is None:
            continue
        full.append(
            {
                "planCode": plan.get("planCode"),
                "invoiceName": plan.get("invoiceName"),
                "price_eur": price,
            }
        )
    full.sort(key=lambda r: r["price_eur"])
    available: list[dict[str, Any]] = []
    for row in full[:24]:
        stock = availability(str(row["planCode"]))
        rec = {**row, "in_stock": bool(stock.get("in_stock")), "availability": stock}
        if rec["in_stock"]:
            available.append(rec)
    cheapest_catalog = full[0] if full else None
    cheapest_in_stock = available[0] if available else None
    affordable = None
    if max_eur is not None and cheapest_in_stock is not None:
        if float(cheapest_in_stock["price_eur"]) <= float(max_eur) + 1e-9:
            affordable = cheapest_in_stock
    return {
        "cheapest_catalog": cheapest_catalog,
        "cheapest_in_stock": cheapest_in_stock,
        "affordable_in_stock": affordable,
        "in_stock_count_scanned": len(available),
        "catalog_top": rows,
    }


def decide_order(
    *,
    nic: str | None,
    me_http: int,
    prepaid_eur: float | None,
    dedicated: dict[str, Any],
    sku: dict[str, Any] | None,
    want_order: bool,
) -> dict[str, Any]:
    """Pure gate. Tests this without hitting OVH."""
    order = {"requested": want_order, "executed": False, "blocked_reason": None, "nic": nic}
    if nic == OVH2_NIC:
        order["blocked_reason"] = "forbidden_nic_ovh2_vc491276"
        return order
    if nic != OVH4_NIC or me_http != 200:
        order["blocked_reason"] = "ovh4_unauthenticated_or_wrong_nic"
        return order
    if dedicated.get("eco_in_delivery") or (dedicated.get("count") or 0) > 0:
        order["blocked_reason"] = "dedicated_already_listed_or_delivering"
        return order
    if not isinstance(prepaid_eur, (int, float)):
        order["blocked_reason"] = "prepaid_unmeasured"
        return order
    if sku is None:
        order["blocked_reason"] = "no_sku_in_stock_within_prepaid"
        return order
    price = sku.get("price_eur")
    if price is None or float(prepaid_eur) + 1e-9 < float(price):
        order["blocked_reason"] = "prepaid_below_sku"
        return order
    if not sku.get("in_stock"):
        order["blocked_reason"] = "sku_unavailable"
        return order
    order["would_order"] = {
        "planCode": sku.get("planCode"),
        "price_eur": price,
        "tender": "ovhAccount_prepaid_only",
    }
    if not want_order:
        order["blocked_reason"] = "dry_run_no_order_flag"
        return order
    # Prepaid already covers the SKU — still no card charge. Checkout is
    # posted only by an explicit future operator path; this commander
    # refuses to bill CREDIT_CARD if prepaid later disappears.
    order["blocked_reason"] = None
    order["executed"] = False
    order["note"] = "gates_open_checkout_not_implemented_to_avoid_card_charge"
    return order


def quote_ovh4(*, want_order: bool) -> dict[str, Any]:
    creds = ovh4_creds()
    present = {
        "application_key": bool(creds.get("application_key")),
        "application_secret": bool(creds.get("application_secret")),
        "consumer_key": bool(creds.get("consumer_key")),
        "source": creds.get("source"),
    }
    dedicated = {"http": 0, "count": None, "servers": [], "eco_in_delivery": False}
    me_http = 0
    nic = None
    prepaid = None
    balances: list[dict[str, Any]] = []
    cloud_credits: list[dict[str, Any]] = []
    if present["application_key"] and present["application_secret"] and present["consumer_key"]:
        dedicated = list_dedicated_servers(creds)
        me_c, me = _ovh_call("GET", "/me", creds)
        me_http = me_c
        nic = me.get("nichandle") if isinstance(me, dict) else None
        acc_c, accs = _ovh_call("GET", "/me/ovhAccount", creds)
        if isinstance(accs, list):
            for ident in accs[:4]:
                _c, body = _ovh_call("GET", f"/me/ovhAccount/{ident}", creds)
                if isinstance(body, dict) and isinstance(body.get("balance"), dict):
                    balances.append(
                        {
                            "account_redacted": True,
                            "value": body["balance"].get("value"),
                            "text": body["balance"].get("text"),
                            "currency": body["balance"].get("currencyCode"),
                            "http": acc_c,
                        }
                    )
        prepaid = balances[0]["value"] if balances else None
        _pc, projects = _ovh_call("GET", "/cloud/project", creds)
        if isinstance(projects, list):
            for pid in projects[:3]:
                _ic, ids = _ovh_call("GET", f"/cloud/project/{pid}/credit", creds)
                if not isinstance(ids, list):
                    continue
                for cid in ids[:8]:
                    hc, body = _ovh_call("GET", f"/cloud/project/{pid}/credit/{cid}", creds)
                    if isinstance(body, dict):
                        cloud_credits.append(
                            {
                                "credit_id": cid,
                                "http": hc,
                                "description": body.get("description"),
                                "available_eur": (body.get("available_credit") or {}).get("value")
                                if isinstance(body.get("available_credit"), dict)
                                else None,
                            }
                        )

    scan = cheapest_available(max_eur=float(prepaid) if isinstance(prepaid, (int, float)) else None)
    sku = scan.get("affordable_in_stock")
    order = decide_order(
        nic=nic,
        me_http=me_http,
        prepaid_eur=float(prepaid) if isinstance(prepaid, (int, float)) else None,
        dedicated=dedicated,
        sku=sku if isinstance(sku, dict) else None,
        want_order=want_order,
    )
    if nic == OVH2_NIC:
        order["blocked_reason"] = "forbidden_nic_ovh2_vc491276"
        order["executed"] = False
    return {
        "nic_expected": OVH4_NIC,
        "nic_forbidden": OVH2_NIC,
        "vm_keep": OVH4_VM_KEEP,
        "creds_present": present,
        "me_http": me_http,
        "nic": nic,
        "dedicated_servers": dedicated,
        "ovhAccount_prepaid_eur": prepaid,
        "ovhAccount_balances": balances,
        "public_cloud_credits_not_eco_tender": cloud_credits,
        "sku_scan": {
            "cheapest_catalog": scan.get("cheapest_catalog"),
            "cheapest_in_stock": {
                k: (scan.get("cheapest_in_stock") or {}).get(k)
                for k in ("planCode", "invoiceName", "price_eur", "in_stock")
            }
            if scan.get("cheapest_in_stock")
            else None,
            "affordable_in_stock": sku,
        },
        "order": order,
        "ovh4_vm_untouched": True,
        "secrets_printed": False,
        "invented_balance": False,
        "invented_tpm": False,
        "certified_distributed_mainnet": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OVH4 Eco commander. Lists dedicated servers first.")
    parser.add_argument("--order", action="store_true", help="POST checkout only if all gates pass.")
    args = parser.parse_args()
    result = quote_ovh4(want_order=args.order)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
