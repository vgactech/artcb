#!/usr/bin/env python3
"""Quote the cheapest OVH Eco/bare-metal SKU. Never invent a balance.

Uses public catalog (no auth). OVH3 credit is read only from OVH3_* keys.
Does not fall back to OVH2 / OVH4 to place an order.
Does not POST an order unless --order AND measured credit >= price AND stock.

Never prints API keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

OVH_BASE = "https://eu.api.ovh.com/1.0"
ECO_CATALOG = f"{OVH_BASE}/order/catalog/public/eco?ovhSubsidiary=FR"
KNOWN_NICS_NOT_OVH3 = frozenset({"vc491276-ovh", "xy4589-ovh"})
CHEAPEST_HINT = "25skb012"


def _ovh_call(method: str, path: str, creds: dict[str, str], body: str = "") -> tuple[int, object]:
    ak = creds.get("application_key") or ""
    as_ = creds.get("application_secret") or ""
    ck = creds.get("consumer_key") or ""
    if not (ak and as_ and ck):
        return 0, {"error": "missing_ovh3_creds"}
    with urlopen(f"{OVH_BASE}/auth/time", timeout=10) as resp:
        ts = str(int(json.loads(resp.read().decode())))
    url = f"{OVH_BASE}{path}"
    sig = "$1$" + hashlib.sha1("+".join([as_, ck, method, url, body, ts]).encode()).hexdigest()
    req = Request(
        url,
        data=body.encode() if body else None,
        method=method,
        headers={
            "X-Ovh-Application": ak,
            "X-Ovh-Timestamp": ts,
            "X-Ovh-Signature": sig,
            "X-Ovh-Consumer": ck,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=25) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


def ovh3_creds() -> dict[str, str]:
    """Only the dedicated OVH3 nic. Cursor OVH_* is often OVH4 and is not OVH3."""
    return {
        "application_key": (os.environ.get("OVH3_APPLICATION_KEY") or "").strip(),
        "application_secret": (os.environ.get("OVH3_APPLICATION_SECRET") or "").strip(),
        "consumer_key": (os.environ.get("OVH3_CONSUMER_KEY") or "").strip(),
        "nic": (os.environ.get("OVH3_NIC") or "").strip(),
    }


def euro_from_raw(raw: int | float | None) -> float | None:
    if raw is None:
        return None
    return float(raw) / 1e8


def public_eco_catalog() -> dict[str, Any]:
    with urlopen(ECO_CATALOG, timeout=40) as resp:
        cat = json.loads(resp.read().decode())
    rows: list[dict[str, Any]] = []
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
        rows.append(
            {
                "planCode": plan.get("planCode"),
                "invoiceName": plan.get("invoiceName"),
                "price_raw": best.get("price"),
                "price_eur": euro_from_raw(best.get("price")),
            }
        )
    rows.sort(key=lambda r: r.get("price_eur") if r.get("price_eur") is not None else 10**18)
    return {
        "catalog": "eco",
        "subsidiary": "FR",
        "currency": "EUR",
        "plan_count": len(rows),
        "cheapest": rows[:5],
    }


def availability(plan_code: str) -> dict[str, Any]:
    url = f"{OVH_BASE}/dedicated/server/datacenter/availabilities?planCode={plan_code}"
    try:
        with urlopen(url, timeout=20) as resp:
            body = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"planCode": plan_code, "error": type(exc).__name__}
    dcs: list[dict[str, str]] = []
    in_stock = False
    if isinstance(body, list):
        for item in body:
            for dc in item.get("datacenters") or []:
                if not isinstance(dc, dict):
                    continue
                av = str(dc.get("availability") or "unknown")
                dcs.append({"datacenter": str(dc.get("datacenter")), "availability": av})
                if av not in {"unavailable", "unknown", "None"}:
                    in_stock = True
    return {"planCode": plan_code, "in_stock": in_stock, "datacenters": dcs[:20]}


def measure_ovh3_credit() -> dict[str, Any]:
    creds = ovh3_creds()
    present = {
        "OVH3_APPLICATION_KEY": bool(creds["application_key"]),
        "OVH3_APPLICATION_SECRET": bool(creds["application_secret"]),
        "OVH3_CONSUMER_KEY": bool(creds["consumer_key"]),
        "OVH3_NIC": bool(creds["nic"]),
    }
    if creds["nic"] in KNOWN_NICS_NOT_OVH3:
        return {
            "ok": False,
            "reason": "nic_is_existing_node_not_ovh3",
            "nic": creds["nic"],
            "vars_present": present,
            "balance_eur": None,
            "invented": False,
        }
    if not (creds["application_key"] and creds["application_secret"] and creds["consumer_key"]):
        return {
            "ok": False,
            "reason": "missing_ovh3_api_keys",
            "needed": [
                "OVH3_APPLICATION_KEY",
                "OVH3_APPLICATION_SECRET",
                "OVH3_CONSUMER_KEY",
                "OVH3_NIC",
            ],
            "not_ovh3": {
                "KEY_API_ARTCB_DOPPLER_3": "Doppler project artcb3 = AWS node, not an OVH nic",
                "OVH_* Cursor env": "currently the OVH4 nic xy4589-ovh (or stale 403)",
            },
            "vars_present": present,
            "balance_eur": None,
            "invented": False,
        }
    me_c, me = _ovh_call("GET", "/me", creds)
    nic = me.get("nichandle") if isinstance(me, dict) else None
    if nic in KNOWN_NICS_NOT_OVH3:
        return {
            "ok": False,
            "reason": "authenticated_nic_is_not_ovh3",
            "nic": nic,
            "me_http": me_c,
            "balance_eur": None,
            "invented": False,
        }
    acc_c, accs = _ovh_call("GET", "/me/ovhAccount", creds)
    balances: list[dict[str, Any]] = []
    if isinstance(accs, list):
        for ident in accs[:6]:
            _c, body = _ovh_call("GET", f"/me/ovhAccount/{ident}", creds)
            if isinstance(body, dict) and isinstance(body.get("balance"), dict):
                balances.append(
                    {
                        "value": body["balance"].get("value"),
                        "text": body["balance"].get("text"),
                        "currency": body["balance"].get("currencyCode"),
                    }
                )
    value = None
    if balances:
        value = balances[0].get("value")
    return {
        "ok": me_c == 200,
        "me_http": me_c,
        "ovhAccount_http": acc_c,
        "nic": nic or creds["nic"] or None,
        "balances": balances,
        "balance_eur": value,
        "invented": False,
    }


def quote(*, want_order: bool) -> dict[str, Any]:
    catalog = public_eco_catalog()
    cheapest = (catalog.get("cheapest") or [None])[0]
    plan = (cheapest or {}).get("planCode") or CHEAPEST_HINT
    price = (cheapest or {}).get("price_eur")
    stock = availability(plan)
    credit = measure_ovh3_credit()
    balance = credit.get("balance_eur")
    can_pay = isinstance(balance, (int, float)) and price is not None and float(balance) + 1e-9 >= float(price)
    order = {
        "requested": want_order,
        "executed": False,
        "blocked_reason": None,
    }
    if want_order:
        if not credit.get("ok"):
            order["blocked_reason"] = credit.get("reason") or "ovh3_unauthenticated"
        elif not can_pay:
            order["blocked_reason"] = "credit_below_sku_or_unmeasured"
        elif not stock.get("in_stock"):
            order["blocked_reason"] = "sku_unavailable"
        else:
            order["blocked_reason"] = "order_still_requires_operator_confirm_flag"
    return {
        "catalog": catalog,
        "selected": cheapest,
        "availability": stock,
        "ovh3_credit": credit,
        "can_pay_cheapest": can_pay,
        "order": order,
        "secrets_printed": False,
        "invented_balance": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Quote OVH Eco bare metal. No silent order.")
    parser.add_argument("--order", action="store_true", help="Attempt order (still blocked without funds/stock/OVH3).")
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()
    result = quote(want_order=args.order)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
