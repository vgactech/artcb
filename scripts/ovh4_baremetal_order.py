#!/usr/bin/env python3
"""OVH4 (nic xy4589-ovh) Eco bare-metal commander.

Lists GET /dedicated/server BEFORE any --order.
Default (no --go): pays only from measured ovhAccount prepaid — never
Public Cloud credit, never vc491276-ovh (OVH2), never a CREDIT_CARD top-up.

--order --go is the operator-GO path: cheapest currently available Eco/Kimsufi
FQN, including the nic's preferred payment method (CREDIT_CARD) when prepaid
is 0. One server. No retry loop on HTTP 400/402.

Never prints API keys. Never invents a balance or a TPM.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.request import urlopen

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ovh_baremetal_quote import (  # noqa: E402
    OVH_BASE,
    _ovh_call,
    eco_catalog_intervals,
    euro_from_raw,
    public_eco_catalog,
)

OVH4_NIC = "xy4589-ovh"
OVH2_NIC = "vc491276-ovh"
OVH4_VM_KEEP = "91.134.45.8"
FR_DC = ("gra", "rbx", "sbg")
CART_DESCRIPTION = "artcb-194-go"


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


def _monthly_eur(plan: dict[str, Any]) -> float | None:
    monthly = [
        pr
        for pr in (plan.get("pricings") or [])
        if isinstance(pr, dict)
        and pr.get("interval") == 1
        and pr.get("intervalUnit") == "month"
        and "renew" in str(pr.get("capacities") or "")
    ]
    if not monthly:
        return None
    best = min(monthly, key=lambda pr: pr.get("price") or 10**18)
    return euro_from_raw(best.get("price"))


def _public_catalog() -> dict[str, Any]:
    with urlopen(f"{OVH_BASE}/order/catalog/public/eco?ovhSubsidiary=FR", timeout=40) as resp:
        return json.loads(resp.read().decode())


def _in_stock_av(av: str) -> bool:
    return av not in {"unavailable", "unknown", "None", "null", ""}


def pick_cheapest_combo(combos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer a FR datacenter (GRA/RBX/SBG) when any combo has one, then min €."""
    if not combos:
        return None
    fr = [c for c in combos if c.get("dcs_fr")]
    pool = fr if fr else combos

    def sort_key(row: dict[str, Any]) -> tuple[float, int, int, int]:
        total = float(row.get("total_eur") if row.get("total_eur") is not None else 10**9)
        dcs = {str(d.get("dc")) for d in (row.get("dcs_fr") or [])}
        return (
            total,
            0 if "gra" in dcs else 1,
            0 if "rbx" in dcs else 1,
            0 if "sbg" in dcs else 1,
        )

    return min(pool, key=sort_key)


def scan_in_stock_combos(*, catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every in-stock Eco FQN with real monthly total (base + RAM/disk extras)."""
    cat = catalog if isinstance(catalog, dict) else _public_catalog()
    addons = {a.get("planCode"): a for a in (cat.get("addons") or []) if isinstance(a, dict)}
    plans: list[dict[str, Any]] = []
    for plan in cat.get("plans") or []:
        if not isinstance(plan, dict):
            continue
        base = _monthly_eur(plan)
        if base is None:
            continue
        families = {f.get("name"): f for f in (plan.get("addonFamilies") or []) if isinstance(f, dict)}
        mem_f = families.get("memory") or {}
        sto_f = families.get("storage") or {}
        bw_f = families.get("bandwidth") or {}
        plans.append(
            {
                "planCode": plan.get("planCode"),
                "invoiceName": plan.get("invoiceName"),
                "base_eur": base,
                "memory_addons": list(mem_f.get("addons") or []),
                "storage_addons": list(sto_f.get("addons") or []),
                "bandwidth_default": bw_f.get("default"),
            }
        )
    plans.sort(key=lambda r: float(r["base_eur"]))
    combos: list[dict[str, Any]] = []

    def addon_price(code: str | None) -> float:
        if not code:
            return 0.0
        addon = addons.get(code)
        if not isinstance(addon, dict):
            return 0.0
        price = _monthly_eur(addon)
        return float(price) if price is not None else 0.0

    for plan in plans[:30]:
        code = str(plan["planCode"])
        url = f"{OVH_BASE}/dedicated/server/datacenter/availabilities?planCode={code}"
        try:
            with urlopen(url, timeout=20) as resp:
                rows = json.loads(resp.read().decode())
        except (OSError, TimeoutError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            dcs_all = []
            dcs_fr = []
            for dc in item.get("datacenters") or []:
                if not isinstance(dc, dict):
                    continue
                av = str(dc.get("availability") or "unknown")
                name = str(dc.get("datacenter") or "")
                rec = {"datacenter": name, "availability": av}
                if _in_stock_av(av):
                    dcs_all.append(rec)
                    if name in FR_DC:
                        dcs_fr.append(rec)
            if not dcs_all:
                continue
            mem = str(item.get("memory") or "")
            sto = str(item.get("storage") or "")
            mem_code = next((a for a in plan["memory_addons"] if mem and mem in str(a)), None)
            sto_code = next((a for a in plan["storage_addons"] if sto and sto in str(a)), None)
            bw_code = plan.get("bandwidth_default")
            mem_extra = addon_price(mem_code)
            sto_extra = addon_price(sto_code)
            bw_extra = addon_price(bw_code)
            total = float(plan["base_eur"]) + mem_extra + sto_extra + bw_extra
            combos.append(
                {
                    "planCode": code,
                    "invoiceName": plan["invoiceName"],
                    "base_eur": plan["base_eur"],
                    "fqn": item.get("fqn"),
                    "memory": mem,
                    "storage": sto,
                    "memory_addon": mem_code,
                    "storage_addon": sto_code,
                    "bandwidth_addon": bw_code,
                    "mem_extra_eur": mem_extra,
                    "sto_extra_eur": sto_extra,
                    "bw_extra_eur": bw_extra,
                    "total_eur": total,
                    "in_stock": True,
                    "dcs_fr": dcs_fr,
                    "dcs_all": dcs_all,
                    "datacenter": next(
                        (d["datacenter"] for d in dcs_fr if d["datacenter"] == "gra"),
                        next(
                            (d["datacenter"] for d in dcs_fr if d["datacenter"] == "rbx"),
                            next((d["datacenter"] for d in dcs_fr), (dcs_all[0]["datacenter"] if dcs_all else None)),
                        ),
                    ),
                }
            )
    combos.sort(key=lambda r: float(r.get("total_eur") or 10**9))
    return combos


def cheapest_available(*, max_eur: float | None) -> dict[str, Any]:
    catalog = public_eco_catalog()
    rows = list(catalog.get("cheapest") or [])
    cat = _public_catalog()
    full: list[dict[str, Any]] = []
    for plan in cat.get("plans") or []:
        price = _monthly_eur(plan) if isinstance(plan, dict) else None
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
    combos = scan_in_stock_combos(catalog=cat)
    cheapest_in_stock = pick_cheapest_combo(combos)
    affordable = None
    if max_eur is not None and cheapest_in_stock is not None:
        if float(cheapest_in_stock["total_eur"]) <= float(max_eur) + 1e-9:
            affordable = cheapest_in_stock
    return {
        "cheapest_catalog": full[0] if full else None,
        "cheapest_in_stock": cheapest_in_stock,
        "affordable_in_stock": affordable,
        "in_stock_count_scanned": len(combos),
        "catalog_top": rows,
        "in_stock_top": [
            {
                "planCode": c.get("planCode"),
                "total_eur": c.get("total_eur"),
                "fqn": c.get("fqn"),
                "datacenter": c.get("datacenter"),
            }
            for c in combos[:8]
        ],
    }


def decide_order(
    *,
    nic: str | None,
    me_http: int,
    prepaid_eur: float | None,
    dedicated: dict[str, Any],
    sku: dict[str, Any] | None,
    want_order: bool,
    operator_go: bool = False,
) -> dict[str, Any]:
    """Pure gate. Tests this without hitting OVH."""
    order = {
        "requested": want_order,
        "executed": False,
        "blocked_reason": None,
        "nic": nic,
        "operator_go": operator_go,
    }
    if nic == OVH2_NIC:
        order["blocked_reason"] = "forbidden_nic_ovh2_vc491276"
        return order
    if nic != OVH4_NIC or me_http != 200:
        order["blocked_reason"] = "ovh4_unauthenticated_or_wrong_nic"
        return order
    if dedicated.get("eco_in_delivery") or (dedicated.get("count") or 0) > 0:
        order["blocked_reason"] = "dedicated_already_listed_or_delivering"
        return order
    if sku is None or not sku.get("in_stock"):
        order["blocked_reason"] = "sku_unavailable" if sku else "no_sku_in_stock"
        return order
    price = sku.get("total_eur", sku.get("price_eur"))
    if price is None:
        order["blocked_reason"] = "sku_price_unmeasured"
        return order
    prepaid_ok = isinstance(prepaid_eur, (int, float)) and float(prepaid_eur) + 1e-9 >= float(price)
    if not prepaid_ok and not operator_go:
        if not isinstance(prepaid_eur, (int, float)):
            order["blocked_reason"] = "prepaid_unmeasured"
            return order
        order["blocked_reason"] = "prepaid_below_sku"
        return order
    tender = "ovhAccount_prepaid" if prepaid_ok else "preferred_payment_method_CREDIT_CARD"
    order["would_order"] = {
        "planCode": sku.get("planCode"),
        "fqn": sku.get("fqn"),
        "price_eur": price,
        "datacenter": sku.get("datacenter"),
        "tender": tender,
    }
    if not want_order:
        order["blocked_reason"] = "dry_run_no_order_flag"
        return order
    order["blocked_reason"] = None
    return order


def _json_body(obj: dict[str, Any]) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def _ovh_post(
    path: str, creds: dict[str, str], obj: dict[str, Any] | None = None, *, timeout: int = 25
) -> tuple[int, object]:
    body = "" if obj is None else _json_body(obj)
    return _ovh_call("POST", path, creds, body, timeout=timeout)


def _public_err(http: int, body: object) -> dict[str, Any]:
    out: dict[str, Any] = {"http": http}
    if isinstance(body, dict):
        out["class"] = body.get("class")
        out["message"] = body.get("message")
        out["errorCode"] = body.get("errorCode")
        if body.get("raw"):
            out["raw"] = str(body.get("raw"))[:400]
    else:
        out["type"] = type(body).__name__
    return out


def list_recent_eco_orders(creds: dict[str, str]) -> dict[str, Any]:
    """Detect an Eco already ordered even if /dedicated/server is still empty."""
    code, orders = _ovh_call("GET", "/me/order", creds)
    found: list[dict[str, Any]] = []
    markers = ("kimsufi", "eco", "ks-", "ks-5", "ks-b", "dedicated server", "serveur dédié")
    if isinstance(orders, list):
        for oid in list(reversed(orders))[:12]:
            _oc, od = _ovh_call("GET", f"/me/order/{oid}", creds)
            _dc, dets = _ovh_call("GET", f"/me/order/{oid}/details", creds)
            descs: list[str] = []
            if isinstance(dets, list):
                for did in dets[:8]:
                    _xc, xb = _ovh_call("GET", f"/me/order/{oid}/details/{did}", creds)
                    if isinstance(xb, dict):
                        descs.append(str(xb.get("description") or xb.get("domain") or ""))
            blob = " ".join(descs).lower()
            if any(m in blob for m in markers):
                price = None
                if isinstance(od, dict) and isinstance(od.get("priceWithTax"), dict):
                    price = od["priceWithTax"].get("text")
                found.append({"orderId": oid, "priceWithTax": price, "details": descs[:6]})
    return {"http": code, "eco_orders": found, "count": len(found)}


def payment_means_public(creds: dict[str, str]) -> dict[str, Any]:
    code, body = _ovh_call("GET", "/me/payment/method", creds)
    means: list[dict[str, Any]] = []
    if isinstance(body, list):
        for ident in body[:4]:
            hc, det = _ovh_call("GET", f"/me/payment/method/{ident}", creds)
            if isinstance(det, dict):
                means.append(
                    {
                        "http": hc,
                        "paymentType": det.get("paymentType"),
                        "status": det.get("status"),
                        "default": det.get("default"),
                        "label_printed": False,
                    }
                )
    return {"http": code, "count": len(body) if isinstance(body, list) else None, "means": means}


def sku_public(sku: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(sku, dict):
        return None
    keys = (
        "planCode",
        "invoiceName",
        "price_eur",
        "total_eur",
        "base_eur",
        "in_stock",
        "fqn",
        "datacenter",
        "memory_addon",
        "storage_addon",
        "bandwidth_addon",
        "mem_extra_eur",
        "sto_extra_eur",
    )
    return {k: sku.get(k) for k in keys if k in sku or sku.get(k) is not None}


def _checkout_prices(body: dict[str, Any]) -> dict[str, Any]:
    prices = body.get("prices") if isinstance(body.get("prices"), dict) else body
    out: dict[str, Any] = {}
    if not isinstance(prices, dict):
        return out
    for key in ("withTax", "withoutTax", "tax", "priceWithTax", "priceWithoutTax"):
        val = prices.get(key)
        if isinstance(val, dict):
            out[key] = {"text": val.get("text"), "value": val.get("value"), "currency": val.get("currencyCode")}
    return out


def place_eco_order(creds: dict[str, str], sku: dict[str, Any]) -> dict[str, Any]:
    """Create one Eco cart and checkout once. No retry loop on 400/402."""
    trace: list[dict[str, Any]] = []
    plan = str(sku.get("planCode") or "")
    dc = str(sku.get("datacenter") or "rbx")
    mem = sku.get("memory_addon")
    sto = sku.get("storage_addon")
    bw = sku.get("bandwidth_addon")
    if not plan or not mem or not sto or not bw:
        return {"executed": False, "blocked_reason": "sku_addons_incomplete", "trace": trace}

    cc, cart = _ovh_post(
        "/order/cart",
        creds,
        {"ovhSubsidiary": "FR", "description": CART_DESCRIPTION},
    )
    trace.append({"step": "post_cart", **_public_err(cc, cart)})
    cart_id = cart.get("cartId") if isinstance(cart, dict) else None
    if cc not in {200, 201} or not cart_id:
        return {"executed": False, "blocked_reason": "cart_create_failed", "trace": trace, "http": cc}

    ac, _ab = _ovh_post(f"/order/cart/{cart_id}/assign", creds)
    trace.append({"step": "assign", "http": ac})
    if ac not in {200, 201, 204}:
        return {
            "executed": False,
            "blocked_reason": "cart_assign_failed",
            "cartId": cart_id,
            "trace": trace,
            "http": ac,
        }

    ec, eco = _ovh_post(
        f"/order/cart/{cart_id}/eco",
        creds,
        {"duration": "P1M", "planCode": plan, "pricingMode": "default", "quantity": 1},
    )
    trace.append({"step": "post_eco", **_public_err(ec, eco)})
    item_id = eco.get("itemId") if isinstance(eco, dict) else None
    if ec not in {200, 201} or not item_id:
        return {
            "executed": False,
            "blocked_reason": "eco_item_failed",
            "cartId": cart_id,
            "trace": trace,
            "http": ec,
        }

    for opt in (mem, sto, bw):
        oc, ob = _ovh_post(
            f"/order/cart/{cart_id}/eco/options",
            creds,
            {
                "duration": "P1M",
                "itemId": int(item_id),
                "planCode": str(opt),
                "pricingMode": "default",
                "quantity": 1,
            },
        )
        trace.append({"step": "post_option", "planCode": opt, **_public_err(oc, ob)})
        if oc not in {200, 201}:
            return {
                "executed": False,
                "blocked_reason": "eco_option_failed",
                "cartId": cart_id,
                "itemId": item_id,
                "trace": trace,
                "http": oc,
            }

    for label, value in (
        ("dedicated_datacenter", dc),
        ("dedicated_os", "none_64.en"),
        ("region", "europe"),
    ):
        kc, kb = _ovh_post(
            f"/order/cart/{cart_id}/item/{item_id}/configuration",
            creds,
            {"label": label, "value": value},
        )
        trace.append({"step": "configuration", "label": label, "value": value, **_public_err(kc, kb)})
        if kc not in {200, 201}:
            return {
                "executed": False,
                "blocked_reason": "configuration_failed",
                "cartId": cart_id,
                "itemId": item_id,
                "trace": trace,
                "http": kc,
            }

    pc, preview = _ovh_call("GET", f"/order/cart/{cart_id}/checkout", creds)
    preview_err = _public_err(pc, preview)
    preview_prices = _checkout_prices(preview) if isinstance(preview, dict) else {}
    trace.append({"step": "get_checkout", **preview_err, "prices": preview_prices})
    if pc == 400:
        return {
            "executed": False,
            "blocked_reason": "checkout_preview_400_unavailable",
            "cartId": cart_id,
            "itemId": item_id,
            "http": 400,
            "error": preview_err,
            "trace": trace,
        }
    if pc not in {200, 201}:
        return {
            "executed": False,
            "blocked_reason": "checkout_preview_failed",
            "cartId": cart_id,
            "itemId": item_id,
            "http": pc,
            "error": preview_err,
            "trace": trace,
        }

    xc, xbody = _ovh_post(
        f"/order/cart/{cart_id}/checkout",
        creds,
        {"autoPayWithPreferredPaymentMethod": True, "waiveRetractationPeriod": True},
        timeout=60,
    )
    xerr = _public_err(xc, xbody)
    trace.append({"step": "post_checkout", **xerr})
    if xc in {400, 402}:
        return {
            "executed": False,
            "blocked_reason": "checkout_refused",
            "cartId": cart_id,
            "itemId": item_id,
            "http": xc,
            "error": xerr,
            "preview_prices": preview_prices,
            "trace": trace,
            "operator_sentence": (
                f"Go donné, checkout refusé, code HTTP {xc}, "
                f"raison {xerr.get('class') or ''} {xerr.get('message') or ''}".strip()
            ),
        }
    if xc not in {200, 201} or not isinstance(xbody, dict):
        return {
            "executed": False,
            "blocked_reason": "checkout_failed",
            "cartId": cart_id,
            "itemId": item_id,
            "http": xc,
            "error": xerr,
            "trace": trace,
        }

    order_id = xbody.get("orderId")
    prices = _checkout_prices(xbody)
    return {
        "executed": True,
        "blocked_reason": None,
        "cartId": cart_id,
        "itemId": item_id,
        "http": xc,
        "orderId": order_id,
        "prices": prices,
        "url_redacted": True,
        "planCode": plan,
        "fqn": sku.get("fqn"),
        "datacenter": dc,
        "tender": "preferred_payment_method_CREDIT_CARD",
        "trace": trace,
    }


def quote_ovh4(*, want_order: bool, operator_go: bool = False) -> dict[str, Any]:
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
    eco_orders = {"http": 0, "eco_orders": [], "count": 0}
    pays = {"http": 0, "count": None, "means": []}
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
        eco_orders = list_recent_eco_orders(creds)
        pays = payment_means_public(creds)

    intervals = eco_catalog_intervals()
    scan = cheapest_available(max_eur=float(prepaid) if isinstance(prepaid, (int, float)) else None)
    sku = scan.get("cheapest_in_stock") if operator_go else scan.get("affordable_in_stock")
    if isinstance(eco_orders, dict) and (eco_orders.get("count") or 0) > 0:
        dedicated = {**dedicated, "eco_in_delivery": True, "existing_eco_orders": eco_orders.get("eco_orders")}
    order = decide_order(
        nic=nic,
        me_http=me_http,
        prepaid_eur=float(prepaid) if isinstance(prepaid, (int, float)) else None,
        dedicated=dedicated,
        sku=sku if isinstance(sku, dict) else None,
        want_order=want_order,
        operator_go=operator_go,
    )
    if nic == OVH2_NIC:
        order["blocked_reason"] = "forbidden_nic_ovh2_vc491276"
        order["executed"] = False
    checkout = None
    if (
        want_order
        and operator_go
        and order.get("blocked_reason") is None
        and isinstance(sku, dict)
        and nic == OVH4_NIC
    ):
        # Re-list dedicated servers immediately before the only POST checkout.
        dedicated_again = list_dedicated_servers(creds)
        eco_again = list_recent_eco_orders(creds)
        if dedicated_again.get("eco_in_delivery") or (dedicated_again.get("count") or 0) > 0 or (
            eco_again.get("count") or 0
        ) > 0:
            order["blocked_reason"] = "dedicated_already_listed_or_delivering"
            order["executed"] = False
            dedicated = dedicated_again
        else:
            checkout = place_eco_order(creds, sku)
            order["executed"] = bool(checkout.get("executed"))
            order["http"] = checkout.get("http")
            order["orderId"] = checkout.get("orderId")
            order["checkout"] = {
                k: checkout.get(k)
                for k in (
                    "executed",
                    "blocked_reason",
                    "http",
                    "orderId",
                    "prices",
                    "planCode",
                    "fqn",
                    "datacenter",
                    "tender",
                    "operator_sentence",
                    "error",
                    "trace",
                    "cartId",
                    "itemId",
                    "preview_prices",
                )
                if k in checkout
            }
            if not checkout.get("executed"):
                order["blocked_reason"] = checkout.get("blocked_reason")
    return {
        "nic_expected": OVH4_NIC,
        "nic_forbidden": OVH2_NIC,
        "vm_keep": OVH4_VM_KEEP,
        "creds_present": present,
        "me_http": me_http,
        "nic": nic,
        "dedicated_servers": dedicated,
        "existing_eco_orders": eco_orders,
        "payment_means": pays,
        "ovhAccount_prepaid_eur": prepaid,
        "ovhAccount_balances": balances,
        "public_cloud_credits_not_eco_tender": cloud_credits,
        "sku_scan": {
            "cheapest_catalog": scan.get("cheapest_catalog"),
            "cheapest_in_stock": sku_public(scan.get("cheapest_in_stock") if isinstance(scan.get("cheapest_in_stock"), dict) else None),
            "affordable_in_stock": sku_public(scan.get("affordable_in_stock") if isinstance(scan.get("affordable_in_stock"), dict) else None),
            "in_stock_top": scan.get("in_stock_top"),
            "in_stock_count_scanned": scan.get("in_stock_count_scanned"),
        },
        "selected_sku": sku_public(sku if isinstance(sku, dict) else None),
        "catalog_intervals": {
            "billing": intervals.get("billing"),
            "hourly_exists": intervals.get("hourly_exists"),
            "hourly_plan_count": intervals.get("hourly_plan_count"),
            "monthly_plan_count": intervals.get("monthly_plan_count"),
            "renew_interval_units": intervals.get("renew_interval_units"),
            "plan_count": intervals.get("plan_count"),
            "samples": intervals.get("samples"),
            "note": intervals.get("note"),
            "invented": False,
        },
        "order": order,
        "ovh4_vm_untouched": True,
        "secrets_printed": False,
        "invented_balance": False,
        "invented_tpm": False,
        "certified_distributed_mainnet": False,
        "CREDIT_CARD": "preferred_mean_only_with_operator_go",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OVH4 Eco commander. Lists dedicated servers first.")
    parser.add_argument("--order", action="store_true", help="POST checkout only if all gates pass.")
    parser.add_argument(
        "--go",
        action="store_true",
        dest="operator_go",
        help="Operator GO: allow the nic preferred payment method (CREDIT_CARD).",
    )
    args = parser.parse_args()
    result = quote_ovh4(want_order=args.order, operator_go=args.operator_go)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
