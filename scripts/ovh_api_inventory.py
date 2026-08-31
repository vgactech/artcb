#!/usr/bin/env python3
"""OVH API inventory for a node env file. Prints public fields only (no keys)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import parse_env_file  # noqa: E402
from artcb.node_registry import local_env_path  # noqa: E402

OVH_BASE = "https://eu.api.ovh.com/1.0"


def _doppler_ovh_creds(node_id: str) -> dict[str, str]:
    """Load OVH keys from the node Doppler vault. Values never logged."""
    from artcb.node_registry import NODES, doppler_token_env_for  # noqa: PLC0415

    spec = NODES.get(node_id)
    if spec is None or spec.provider != "ovh":
        return {}
    token = (os.environ.get(doppler_token_env_for(node_id)) or os.environ.get("DOPPLER_TOKEN") or "").strip()
    if not token:
        return {}
    names = (
        "OVH_APPLICATION_KEY",
        "OVH_APPLICATION_SECRET",
        "OVH_CONSUMER_KEY",
        "OVH_ENDPOINT",
        "OVH_CLOUD_PROJECT_ID",
        "OVH_NIC",
    )
    out: dict[str, str] = {}
    req = Request(
        "https://api.doppler.com/v3/configs/config/secrets"
        f"?project={spec.doppler_project}&config={spec.doppler_config}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {}
    secrets = payload.get("secrets") if isinstance(payload, dict) else {}
    if not isinstance(secrets, dict):
        return {}
    for name in names:
        meta = secrets.get(name)
        raw = ""
        if isinstance(meta, dict):
            raw = str(meta.get("computed") or meta.get("raw") or meta.get("value") or "").strip()
        elif isinstance(meta, str):
            raw = meta.strip()
        if raw:
            out[name] = raw
    return out


def _creds_from(node_id: str | None) -> dict[str, str]:
    if node_id:
        parsed = parse_env_file(local_env_path(node_id))
        if parsed.get("OVH_APPLICATION_KEY"):
            return parsed
        doppler = _doppler_ovh_creds(node_id)
        if doppler.get("OVH_APPLICATION_KEY"):
            return doppler
        if node_id != "ovh-node-1":
            # Do not fall back to Cursor/shared OVH1 keys for another node.
            return doppler
    return {
        "OVH_APPLICATION_KEY": os.environ.get("OVH_APPLICATION_KEY", ""),
        "OVH_APPLICATION_SECRET": os.environ.get("OVH_APPLICATION_SECRET", ""),
        "OVH_CONSUMER_KEY": os.environ.get("OVH_CONSUMER_KEY", ""),
        "OVH_ENDPOINT": os.environ.get("OVH_ENDPOINT", "ovh-eu"),
        "OVH_CLOUD_PROJECT_ID": os.environ.get("OVH_CLOUD_PROJECT_ID", ""),
    }


def ovh_get(path: str, creds: dict[str, str]) -> tuple[int, object]:
    ak = creds.get("OVH_APPLICATION_KEY") or ""
    as_ = creds.get("OVH_APPLICATION_SECRET") or ""
    ck = creds.get("OVH_CONSUMER_KEY") or ""
    if not (ak and as_ and ck):
        return 0, {"error": "missing_ovh_creds"}
    with urlopen(f"{OVH_BASE}/auth/time", timeout=10) as resp:
        ts = str(int(json.loads(resp.read().decode())))
    url = f"{OVH_BASE}{path}"
    # Official OVH signature: AS+CK+METHOD+URL+BODY+TS (application key is a header only).
    sig_input = "+".join([as_, ck, "GET", url, "", ts])
    sig = "$1$" + hashlib.sha1(sig_input.encode("utf-8")).hexdigest()
    req = Request(
        url,
        headers={
            "X-Ovh-Application": ak,
            "X-Ovh-Timestamp": ts,
            "X-Ovh-Signature": sig,
            "X-Ovh-Consumer": ck,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:300]
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


def _prefix(value: str, n: int = 6) -> str:
    value = value or ""
    return f"{value[:n]}…len={len(value)}" if value else "absent"


def inventory(node_id: str | None) -> dict:
    creds = _creds_from(node_id)
    me_code, me = ovh_get("/me", creds)
    me_pub = {}
    if isinstance(me, dict) and me_code == 200:
        me_pub = {
            "nichandle": me.get("nichandle"),
            "email": me.get("email"),
            "state": me.get("state"),
            "country": me.get("country"),
        }
    proj_code, projects = ovh_get("/cloud/project", creds)
    instances: list[dict] = []
    project_ids = projects if isinstance(projects, list) else []
    env_pid = creds.get("OVH_CLOUD_PROJECT_ID") or ""
    if env_pid and env_pid not in project_ids:
        # Do not echo the project id (Cursor treats it as a secret).
        project_ids = list(project_ids) + ["<from_env>"]
    for pid in project_ids:
        icode, inst = ovh_get(f"/cloud/project/{pid}/instance", creds)
        if icode != 200 or not isinstance(inst, list):
            instances.append({"project": "<redacted>", "http": icode, "error": True})
            continue
        for it in inst:
            addresses = []
            for net, addrs in (it.get("ipAddresses") or []):
                if isinstance(addrs, list):
                    for a in addrs:
                        if isinstance(a, dict) and a.get("ip"):
                            addresses.append({"ip": a.get("ip"), "type": a.get("type"), "version": a.get("version")})
                elif isinstance(net, dict) and net.get("ip"):
                    addresses.append({"ip": net.get("ip"), "type": net.get("type"), "version": net.get("version")})
            # OVH sometimes returns ipAddresses as list of dicts
            if not addresses and isinstance(it.get("ipAddresses"), list):
                for a in it["ipAddresses"]:
                    if isinstance(a, dict) and a.get("ip"):
                        addresses.append({"ip": a.get("ip"), "type": a.get("type"), "version": a.get("version")})
            instances.append(
                {
                    "project": "<redacted>" if pid == "<from_env>" else pid,
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "region": it.get("region"),
                    "status": it.get("status"),
                    "addresses": addresses,
                }
            )
    okms_code, okms = ovh_get("/okms/resource", creds)
    return {
        "node_id": node_id or "env",
        "ak_prefix": _prefix(creds.get("OVH_APPLICATION_KEY") or ""),
        "me_http": me_code,
        "me": me_pub or {"raw_http": me_code, "error": True},
        "cloud_projects_http": proj_code,
        "cloud_projects": projects if isinstance(projects, list) else None,
        "instances": instances,
        "okms_http": okms_code,
        "okms": okms if isinstance(okms, list) else (okms if okms_code != 200 else None),
        "ts": int(time.time()),
        "secrets_printed": False,
    }


def main() -> int:
    node_id = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(inventory(node_id), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
