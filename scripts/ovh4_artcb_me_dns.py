#!/usr/bin/env python3
"""OVH4 (nic xy4589-ovh) — GET domaine + PUT/POST zone DNS pour artcb.me.

INTERDIT : achat, panier, checkout domaine. L'opérateur a DÉJÀ acheté artcb.me.
Aucun achat, aucun panier. Secrets jamais affichés. Pas de fallback process OVH_*
(l'env Cursor est le nic OVH4 — ne pas le prendre pour OVH1/OVH2).

Si artcb.me n'est pas sur ce nic : GET /domain sur les autres nics du repo, puis
arrêter avec « pas sur OVH4, cherche dans le manager ».
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.config import ARTCB_DNS_A_RECORDS, ARTCB_DOMAIN  # noqa: E402
from artcb.live import parse_env_file  # noqa: E402
from artcb.node_registry import local_env_path  # noqa: E402

OVH_BASE = "https://eu.api.ovh.com/1.0"
EXPECTED_NIC = "xy4589-ovh"
DOMAIN = ARTCB_DOMAIN
FORBIDDEN_PATH = re.compile(
    r"^/order(?:/|$)|/cart(?:/|$)|checkout|orderCart|newOrder",
    re.IGNORECASE,
)
OTHER_NICS = ("ovh-node-1", "ovh-node-2")


def _doppler_ovh(node_id: str, token_env: str, project: str) -> dict[str, str]:
    token = (os.environ.get(token_env) or "").strip()
    if not token:
        return {}
    req = Request(
        "https://api.doppler.com/v3/configs/config/secrets"
        f"?project={project}&config=dev",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {}
    secrets = payload.get("secrets") if isinstance(payload, dict) else {}
    if not isinstance(secrets, dict):
        return {}
    out: dict[str, str] = {}
    for name in (
        "OVH_APPLICATION_KEY",
        "OVH_APPLICATION_SECRET",
        "OVH_CONSUMER_KEY",
        "OVH_NIC",
    ):
        meta = secrets.get(name)
        raw = ""
        if isinstance(meta, dict):
            raw = str(meta.get("computed") or meta.get("raw") or "").strip()
        elif isinstance(meta, str):
            raw = meta.strip()
        if raw:
            out[name] = raw
    return out


def _creds(node_id: str) -> dict[str, str]:
    """Node-scoped creds only. Never copies process OVH_* (wrong nic)."""
    local = parse_env_file(local_env_path(node_id))
    out = {
        "OVH_APPLICATION_KEY": local.get("OVH_APPLICATION_KEY") or "",
        "OVH_APPLICATION_SECRET": local.get("OVH_APPLICATION_SECRET") or "",
        "OVH_CONSUMER_KEY": local.get("OVH_CONSUMER_KEY") or "",
        "OVH_NIC": local.get("OVH_NIC") or "",
    }
    mapping = {
        "ovh-node-4": ("KEY_API_ARTCB_DOPPLER_4", "artcb-4"),
        "ovh-node-2": ("KEY_API_ARTCB_DOPPLER_2", "artcb-2"),
        "ovh-node-1": ("DOPPLER_TOKEN", "artcb-blockchain"),
    }
    token_env, project = mapping[node_id]
    doppler = _doppler_ovh(node_id, token_env, project)
    for key, value in doppler.items():
        if value:
            out[key] = value
    return out


def ovh(method: str, path: str, body: dict | None = None, *, creds: dict[str, str] | None = None) -> tuple[int, Any]:
    if FORBIDDEN_PATH.search(path or ""):
        return 0, {"error": "forbidden_order_cart_checkout", "path": path}
    payload = None if body is None else json.dumps(body, separators=(",", ":"))
    if payload and FORBIDDEN_PATH.search(payload):
        return 0, {"error": "forbidden_order_cart_checkout", "path": path}
    use = creds if creds is not None else _creds("ovh-node-4")
    ak = use.get("OVH_APPLICATION_KEY") or ""
    as_ = use.get("OVH_APPLICATION_SECRET") or ""
    ck = use.get("OVH_CONSUMER_KEY") or ""
    if not (ak and as_ and ck):
        return 0, {"error": "missing_ovh_creds"}
    with urlopen(f"{OVH_BASE}/auth/time", timeout=10) as resp:
        ts = str(int(json.loads(resp.read().decode())))
    url = OVH_BASE + path
    sig_input = "+".join([as_, ck, method, url, payload or "", ts])
    sig = "$1$" + hashlib.sha1(sig_input.encode("utf-8")).hexdigest()
    headers = {
        "X-Ovh-Application": ak,
        "X-Ovh-Timestamp": ts,
        "X-Ovh-Signature": sig,
        "X-Ovh-Consumer": ck,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    req = Request(url, data=None if payload is None else payload.encode(), method=method, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        try:
            parsed: Any = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"http": exc.code, "detail": detail}
        return exc.code, parsed
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__, "where": path}


def _public_records(ids: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rid in ids:
        http, detail = ovh("GET", f"/domain/zone/{DOMAIN}/record/{rid}")
        if http == 200 and isinstance(detail, dict):
            rows.append(
                {
                    "id": rid,
                    "fieldType": detail.get("fieldType"),
                    "subDomain": detail.get("subDomain") or "",
                    "target": detail.get("target"),
                    "ttl": detail.get("ttl"),
                }
            )
        else:
            rows.append({"id": rid, "http": http, "error": True})
    return rows


def inventory_other_nics() -> list[dict[str, Any]]:
    """GET /me + GET /domain only. No order. No process-env fallback."""
    rows: list[dict[str, Any]] = []
    for node_id in OTHER_NICS:
        creds = _creds(node_id)
        present = all(creds.get(k) for k in ("OVH_APPLICATION_KEY", "OVH_APPLICATION_SECRET", "OVH_CONSUMER_KEY"))
        row: dict[str, Any] = {
            "node_id": node_id,
            "creds_present": bool(present),
            "note": "GET only — pas d'order",
        }
        if not present:
            row["reason"] = "creds_absentes_pas_de_fallback_process"
            rows.append(row)
            continue
        me_http, me = ovh("GET", "/me", creds=creds)
        row["me_http"] = me_http
        if isinstance(me, dict) and me_http == 200:
            row["nichandle"] = me.get("nichandle")
        dom_http, domains = ovh("GET", "/domain", creds=creds)
        row["domain_http"] = dom_http
        row["domains"] = domains if isinstance(domains, list) else None
        row["has_artcb_me"] = isinstance(domains, list) and DOMAIN in domains
        rows.append(row)
    return rows


def probe() -> dict[str, Any]:
    out: dict[str, Any] = {
        "domain": DOMAIN,
        "expected_nic": EXPECTED_NIC,
        "ordered": False,
        "order_attempted": False,
        "secrets_printed": False,
    }
    me_http, me = ovh("GET", "/me")
    out["me_http"] = me_http
    nic = me.get("nichandle") if isinstance(me, dict) else None
    out["nichandle"] = nic
    out["nic_ok"] = nic == EXPECTED_NIC
    if not out["nic_ok"]:
        out["ok"] = False
        out["reason"] = "nic_mismatch"
        out["message"] = "pas sur OVH4, cherche dans le manager"
        out["other_nics"] = inventory_other_nics()
        return out
    dom_http, domains = ovh("GET", "/domain")
    out["domain_list_http"] = dom_http
    out["domains"] = domains if isinstance(domains, list) else None
    out["already_ours"] = isinstance(domains, list) and DOMAIN in domains
    zone_http, zones = ovh("GET", "/domain/zone")
    out["zone_list_http"] = zone_http
    out["zones"] = zones if isinstance(zones, list) else None
    out["zone_ours"] = isinstance(zones, list) and DOMAIN in zones
    if not out["already_ours"]:
        out["ok"] = False
        out["reason"] = "not_on_ovh4"
        out["message"] = "pas sur OVH4, cherche dans le manager"
        out["other_nics"] = inventory_other_nics()
        return out
    rec_http, ids = ovh("GET", f"/domain/zone/{DOMAIN}/record")
    out["records_http"] = rec_http
    out["records"] = _public_records(ids) if isinstance(ids, list) else None
    out["ok"] = True
    out["reason"] = "owned_on_ovh4"
    return out


def _wanted() -> dict[str, str]:
    wanted = dict(ARTCB_DNS_A_RECORDS)
    # www is already an A (OVH parking). Point it at OVH1 with the apex; no extra CNAME.
    wanted.setdefault("www", wanted[""])
    return wanted


def configure_dns(*, apply: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "domain": DOMAIN,
        "records_wanted": _wanted(),
        "apply": apply,
        "order_attempted": False,
        "aaaa_note": "no AAAA: live nodes documented IPv4 only; none invented",
    }
    probe_state = probe()
    result["probe"] = {
        k: probe_state.get(k)
        for k in (
            "me_http",
            "nichandle",
            "nic_ok",
            "already_ours",
            "zone_ours",
            "reason",
            "message",
            "other_nics",
        )
        if k in probe_state
    }
    if not probe_state.get("already_ours"):
        result["ok"] = False
        result["reason"] = probe_state.get("reason")
        result["message"] = probe_state.get("message") or "pas sur OVH4, cherche dans le manager"
        return result
    existing = probe_state.get("records") or []
    result["existing"] = existing
    actions: list[dict[str, Any]] = []
    for sub, ip in _wanted().items():
        matches = [
            r
            for r in existing
            if isinstance(r, dict) and r.get("fieldType") == "A" and (r.get("subDomain") or "") == sub
        ]
        exact = [r for r in matches if r.get("target") == ip]
        if exact:
            actions.append({"op": "skip", "subDomain": sub, "target": ip, "id": exact[0].get("id")})
            continue
        if matches:
            rid = matches[0].get("id")
            body = {"subDomain": sub, "target": ip, "ttl": 300}
            if apply:
                http, resp = ovh("PUT", f"/domain/zone/{DOMAIN}/record/{rid}", body)
                actions.append(
                    {
                        "op": "put",
                        "subDomain": sub,
                        "target": ip,
                        "id": rid,
                        "http": http,
                        "ok": http in {200, 201, 204},
                        "body": None if http in {200, 201, 204} else resp,
                    }
                )
            else:
                actions.append({"op": "put_dry", "subDomain": sub, "target": ip, "id": rid})
            continue
        body = {"fieldType": "A", "subDomain": sub, "target": ip, "ttl": 300}
        if apply:
            http, resp = ovh("POST", f"/domain/zone/{DOMAIN}/record", body)
            rec_id = resp.get("id") if isinstance(resp, dict) else None
            actions.append(
                {
                    "op": "post",
                    "subDomain": sub,
                    "target": ip,
                    "http": http,
                    "ok": http in {200, 201},
                    "id": rec_id if http in {200, 201} else None,
                    "body": None if http in {200, 201} else resp,
                }
            )
        else:
            actions.append({"op": "post_dry", "subDomain": sub, "target": ip})
    result["actions"] = actions
    if apply:
        ref_http, ref_body = ovh("POST", f"/domain/zone/{DOMAIN}/refresh")
        result["refresh_http"] = ref_http
        result["refresh_ok"] = ref_http in {200, 201, 204}
        if not result["refresh_ok"]:
            result["refresh_body"] = ref_body
        rec_http, ids = ovh("GET", f"/domain/zone/{DOMAIN}/record")
        result["records_after"] = _public_records(ids) if isinstance(ids, list) else None
        result["records_after_http"] = rec_http
    result["ok"] = True if not apply else (
        all(a.get("ok", True) for a in actions if a.get("op") in {"put", "post"})
        and bool(result.get("refresh_ok"))
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="OVH4 artcb.me DNS only — never order")
    parser.add_argument("--apply", action="store_true", help="PUT/POST zone records + refresh")
    parser.add_argument("--probe", action="store_true", help="GET /me /domain /zone only")
    args = parser.parse_args()
    if args.probe and not args.apply:
        print(json.dumps(probe(), indent=2, ensure_ascii=False, default=str))
        return 0
    print(json.dumps(configure_dns(apply=args.apply), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
