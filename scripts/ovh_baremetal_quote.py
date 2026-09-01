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


def _ovh_call(
    method: str,
    path: str,
    creds: dict[str, str],
    body: str = "",
    timeout: int = 25,
) -> tuple[int, object]:
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
        with urlopen(req, timeout=timeout) as resp:
            raw_ok = resp.read().decode()
            if not raw_ok:
                return resp.status, {}
            return resp.status, json.loads(raw_ok)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:800]
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
            and pr.get("intervalUnit") == "month"
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
                "interval": best.get("interval"),
                "intervalUnit": best.get("intervalUnit"),
            }
        )
    rows.sort(key=lambda r: r.get("price_eur") if r.get("price_eur") is not None else 10**18)
    return {
        "catalog": "eco",
        "subsidiary": "FR",
        "currency": "EUR",
        "plan_count": len(rows),
        "cheapest": rows[:5],
        "intervals": eco_catalog_intervals(cat),
    }


def eco_catalog_intervals(cat: dict[str, Any] | None = None) -> dict[str, Any]:
    """Measure real Eco renew intervals from the catalog. Do not assume hour.

    horaire = intervalUnit hour (each hour). mensuel = intervalUnit month (each month).
    Availability strings like 1H-low are stock/delivery, not a billing interval.
    """
    if cat is None:
        with urlopen(ECO_CATALOG, timeout=40) as resp:
            cat = json.loads(resp.read().decode())
    if not isinstance(cat, dict):
        return {"ok": False, "invented": False, "error": "catalog_not_object"}
    unit_counts: dict[str, int] = {}
    hourly_plans: list[dict[str, Any]] = []
    monthly_plans: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    want_samples = {"25skb012", "24sk50-v1", "25skc012"}
    for plan in cat.get("plans") or []:
        if not isinstance(plan, dict):
            continue
        renew_units: set[str] = set()
        renew_rows: list[dict[str, Any]] = []
        for pr in plan.get("pricings") or []:
            if not isinstance(pr, dict):
                continue
            if "renew" not in str(pr.get("capacities") or ""):
                continue
            unit = str(pr.get("intervalUnit") or "missing")
            unit_counts[unit] = unit_counts.get(unit, 0) + 1
            renew_units.add(unit)
            renew_rows.append(
                {
                    "interval": pr.get("interval"),
                    "intervalUnit": pr.get("intervalUnit"),
                    "price_eur": euro_from_raw(pr.get("price")),
                    "description": pr.get("description"),
                    "pricingMode": pr.get("mode") or pr.get("pricingMode"),
                }
            )
        rec = {
            "planCode": plan.get("planCode"),
            "invoiceName": plan.get("invoiceName"),
            "renew_units": sorted(renew_units),
        }
        if "hour" in renew_units:
            hourly_plans.append(rec)
        if "month" in renew_units:
            monthly_plans.append(rec)
        if plan.get("planCode") in want_samples:
            samples.append({**rec, "renew": renew_rows})
    hourly_n = len(hourly_plans)
    monthly_n = len(monthly_plans)
    if hourly_n and monthly_n:
        billing = "mixed_hour_and_month"
    elif hourly_n:
        billing = "hour_only"
    elif monthly_n:
        billing = "month_only"
    else:
        billing = "no_renew_interval"
    return {
        "ok": True,
        "catalog": "eco",
        "subsidiary": "FR",
        "plan_count": len(cat.get("plans") or []),
        "renew_interval_units": unit_counts,
        "hourly_plan_count": hourly_n,
        "monthly_plan_count": monthly_n,
        "hourly_exists": hourly_n > 0,
        "billing": billing,
        "samples": samples,
        "invented": False,
        "note": (
            "1H-low on /dedicated/server/datacenter/availabilities is stock, "
            "not intervalUnit=hour. Public Cloud d2-8 consumption is hourly VM, not Eco."
        ),
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


def _doppler_secrets(token: str, project: str, config: str = "dev") -> tuple[int, dict[str, str]]:
    if not token:
        return 0, {}
    req = Request(
        "https://api.doppler.com/v3/configs/config/secrets"
        f"?project={project}&config={config}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except HTTPError as exc:
        return exc.code, {}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        return 0, {}
    secrets: dict[str, str] = {}
    for name, meta in (payload.get("secrets") or {}).items():
        raw = ""
        if isinstance(meta, dict):
            raw = str(meta.get("computed") or meta.get("raw") or "").strip()
        elif isinstance(meta, str):
            raw = meta.strip()
        if raw:
            secrets[name] = raw
    return 200, secrets


def measure_named_ovh(creds: dict[str, str], *, source: str) -> dict[str, Any]:
    """Measure /me + prepaid + Public Cloud credits. Never prints keys."""
    mapped = {
        "application_key": creds.get("application_key") or creds.get("OVH_APPLICATION_KEY") or "",
        "application_secret": creds.get("application_secret") or creds.get("OVH_APPLICATION_SECRET") or "",
        "consumer_key": creds.get("consumer_key") or creds.get("OVH_CONSUMER_KEY") or "",
    }
    me_c, me = _ovh_call("GET", "/me", mapped)
    nic = me.get("nichandle") if isinstance(me, dict) else None
    email = me.get("email") if isinstance(me, dict) else None
    out: dict[str, Any] = {
        "source": source,
        "me_http": me_c,
        "nic": nic,
        "email": email,
        "invented": False,
    }
    if me_c != 200:
        if isinstance(me, dict):
            out["me_error"] = {
                "class": me.get("class"),
                "message": me.get("message"),
                "errorCode": me.get("errorCode"),
            }
        out["balance_eur"] = None
        return out
    acc_c, accs = _ovh_call("GET", "/me/ovhAccount", mapped)
    balances: list[dict[str, Any]] = []
    if isinstance(accs, list):
        for ident in accs[:6]:
            _c, body = _ovh_call("GET", f"/me/ovhAccount/{ident}", mapped)
            if isinstance(body, dict) and isinstance(body.get("balance"), dict):
                balances.append(
                    {
                        "account_redacted": True,
                        "value": body["balance"].get("value"),
                        "text": body["balance"].get("text"),
                        "currency": body["balance"].get("currencyCode"),
                    }
                )
    out["ovhAccount_http"] = acc_c
    out["balances"] = balances
    out["balance_eur"] = balances[0]["value"] if balances else None
    ds_c, ds = _ovh_call("GET", "/dedicated/server", mapped)
    out["dedicated_http"] = ds_c
    out["dedicated_count"] = len(ds) if isinstance(ds, list) else None
    cp_c, projects = _ovh_call("GET", "/cloud/project", mapped)
    out["cloud_projects_http"] = cp_c
    cloud_credits: list[dict[str, Any]] = []
    if isinstance(projects, list):
        for pid in projects[:4]:
            ic, ids = _ovh_call("GET", f"/cloud/project/{pid}/credit", mapped)
            credit_ids = ids if isinstance(ids, list) else []
            for cid in credit_ids[:8]:
                hc, body = _ovh_call("GET", f"/cloud/project/{pid}/credit/{cid}", mapped)
                if not isinstance(body, dict):
                    continue
                cloud_credits.append(
                    {
                        "project": pid,
                        "credit_id": cid,
                        "http": hc,
                        "description": body.get("description"),
                        "available_eur": (body.get("available_credit") or {}).get("value")
                        if isinstance(body.get("available_credit"), dict)
                        else None,
                        "total_eur": (body.get("total_credit") or {}).get("value")
                        if isinstance(body.get("total_credit"), dict)
                        else None,
                        "used_eur": (body.get("used_credit") or {}).get("value")
                        if isinstance(body.get("used_credit"), dict)
                        else None,
                        "products": body.get("products"),
                    }
                )
    out["cloud_credits"] = cloud_credits
    return out


def hunt_all_ovh_accounts() -> dict[str, Any]:
    """Every Doppler/process OVH key set. Does not invent a 10 EUR prepaid."""
    sources: list[dict[str, Any]] = []
    token_map = [
        ("DOPPLER_TOKEN", "artcb-blockchain", "doppler:artcb-blockchain"),
        ("KEY_API_ARTCB_DOPPLER_2", "artcb-2", "doppler:artcb-2"),
        ("KEY_API_ARTCB_DOPPLER_4", "artcb-4", "doppler:artcb-4"),
    ]
    for env_name, project, label in token_map:
        token = (os.environ.get(env_name) or "").strip()
        if not token:
            sources.append({"source": label, "token_present": False, "me_http": 0, "invented": False})
            continue
        code, secrets = _doppler_secrets(token, project)
        if not secrets.get("OVH_APPLICATION_KEY"):
            sources.append(
                {
                    "source": label,
                    "token_present": True,
                    "doppler_http": code,
                    "ovh_keys_present": False,
                    "invented": False,
                }
            )
            continue
        sources.append(measure_named_ovh(secrets, source=label))
    proc = {
        "OVH_APPLICATION_KEY": os.environ.get("OVH_APPLICATION_KEY") or "",
        "OVH_APPLICATION_SECRET": os.environ.get("OVH_APPLICATION_SECRET") or "",
        "OVH_CONSUMER_KEY": os.environ.get("OVH_CONSUMER_KEY") or "",
    }
    if proc["OVH_APPLICATION_KEY"]:
        sources.append(measure_named_ovh(proc, source="process_env_OVH_*"))
    node4_env = Path.home() / ".artcb" / "nodes" / "ovh-node-4.env"
    if node4_env.is_file():
        parsed: dict[str, str] = {}
        for line in node4_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip().strip('"').strip("'")
        if parsed.get("OVH_APPLICATION_KEY"):
            sources.append(measure_named_ovh(parsed, source="local_ovh-node-4.env"))
    ovh3 = ovh3_creds()
    sources.append(
        {
            "source": "process_env_OVH3_*",
            "keys_present": bool(ovh3["application_key"] and ovh3["application_secret"] and ovh3["consumer_key"]),
            "nic_hint": ovh3["nic"] or None,
            "invented": False,
        }
    )
    return {
        "sources": sources,
        "invented_balance": False,
        "secrets_printed": False,
        "note": (
            "Public Cloud credit is not ovhAccount prepaid and cannot pay Eco dedicated."
        ),
    }


def eco_ksb_stock() -> dict[str, Any]:
    stock = availability("25skb012")
    gra = [
        dc
        for dc in (stock.get("datacenters") or [])
        if str(dc.get("datacenter", "")).lower().startswith("gra")
    ]
    return {
        "planCode": "25skb012",
        "availability": stock,
        "gra": gra,
        "in_stock": bool(stock.get("in_stock")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Quote OVH Eco bare metal. No silent order.")
    parser.add_argument("--order", action="store_true", help="Attempt order (still blocked without funds/stock).")
    parser.add_argument("--hunt", action="store_true", help="Measure every known OVH nic (prepaid + cloud credit).")
    parser.add_argument("--ovh4", action="store_true", help="Quote on nic xy4589-ovh (lists dedicated servers first).")
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()
    if args.ovh4:
        from ovh4_baremetal_order import quote_ovh4  # noqa: PLC0415

        result = quote_ovh4(want_order=args.order)
    else:
        result = quote(want_order=args.order)
        if args.hunt:
            result["hunt"] = hunt_all_ovh_accounts()
            result["ksb_stock"] = eco_ksb_stock()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
