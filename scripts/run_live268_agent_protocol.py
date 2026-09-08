#!/usr/bin/env python3
"""R268 live — Agent Memory Protocol bootstrap + idempotent event on OVH1."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import http_json, resolve_api_key, resolve_api_url  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "aws-node-3": "http://51.44.222.232:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}


def _plain(url: str) -> dict:
    import ssl
    from urllib.request import Request, urlopen

    t0 = time.perf_counter_ns()
    ctx = ssl._create_unverified_context() if url.startswith("https") else None
    try:
        with urlopen(Request(url), timeout=20, context=ctx) as resp:
            body = json.loads(resp.read().decode() or "{}")
            if isinstance(body, dict):
                body["http"] = resp.status
                body["dur_ns"] = time.perf_counter_ns() - t0
            return body if isinstance(body, dict) else {"http": resp.status}
    except Exception as exc:  # noqa: BLE001
        return {"http": 0, "error": type(exc).__name__}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    url = resolve_api_url()
    key = resolve_api_key()
    payload: dict = {"stamp": stamp, "protocol": "268-agent-memory", "live_url": url, "key_present": bool(key)}
    shas = {n: _plain(f"{HTTP[n]}/health").get("git_sha") for n in OFFICIAL_COMPUTE_NODE_IDS}
    payload["live_sha"] = shas
    payload["sha_equal"] = len(set(shas.values())) == 1 and None not in shas.values()
    if not key:
        payload["ok"] = False
        _write(payload, stamp)
        return 3
    boot_h, boot = http_json("GET", f"{url}/api/v1/agent/bootstrap", api_key=key, timeout=30)
    payload["bootstrap"] = {
        "http": boot_h,
        "protocol": boot.get("protocol") if isinstance(boot, dict) else None,
        "platform_hook": (boot or {}).get("ingest_platform_hook") if isinstance(boot, dict) else None,
        "caps": (boot or {}).get("capabilities") if isinstance(boot, dict) else None,
    }
    reg_h, reg = http_json(
        "POST",
        f"{url}/api/v1/agent/register",
        api_key=key,
        body={"provider": "cursor", "label": "cloud-agent-268", "capabilities": ["memory:read", "memory:write", "memo:write"]},
        timeout=30,
    )
    payload["register"] = {"http": reg_h, "agent_id": ((reg.get("agent") or {}) if isinstance(reg, dict) else {}).get("agent_id")}
    event_id = f"evt_268_{uuid.uuid4().hex[:12]}"
    content = f"268 agent event sha={shas.get('ovh-node-1')} stamp={stamp} no-thinking"
    body = {
        "event_id": event_id,
        "kind": "observation",
        "content": content,
        "visibility": "public",
        "tags": ["268", "agent_protocol"],
        "session_id": "268-agent",
    }
    t0 = time.perf_counter_ns()
    e1_h, e1 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body=body, timeout=180)
    e2_h, e2 = http_json("POST", f"{url}/api/v1/agent/events", api_key=key, body=body, timeout=180)
    payload["event"] = {
        "first_http": e1_h,
        "first_status": e1.get("status") if isinstance(e1, dict) else None,
        "block_index": ((e1.get("memo") or {}) if isinstance(e1, dict) else {}).get("block_index"),
        "block_hash": ((e1.get("memo") or {}) if isinstance(e1, dict) else {}).get("block_hash"),
        "second_http": e2_h,
        "second_status": e2.get("status") if isinstance(e2, dict) else None,
        "idempotent": isinstance(e2, dict) and e2.get("status") == "already_committed",
        "same_block": isinstance(e2, dict) and e2.get("block_index") == ((e1.get("memo") or {}) if isinstance(e1, dict) else {}).get("block_index"),
        "dur_ns": time.perf_counter_ns() - t0,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "includes_thinking": False,
    }
    after = {n: _plain(f"{HTTP[n]}/api/v1/chain/status") for n in OFFICIAL_COMPUTE_NODE_IDS}
    payload["after_height"] = {n: (after[n].get("height"), after[n].get("last_hash")) for n in OFFICIAL_COMPUTE_NODE_IDS}
    payload["ok"] = bool(
        boot_h == 200
        and payload["bootstrap"].get("protocol", "").startswith("268")
        and payload["bootstrap"].get("platform_hook") is False
        and e1_h == 200
        and payload["event"].get("idempotent")
        and payload["sha_equal"]
    )
    _write(payload, stamp)
    print(json.dumps({"ok": payload["ok"], "bootstrap": boot_h, "event": payload["event"].get("first_status"), "idempotent": payload["event"].get("idempotent"), "block": payload["event"].get("block_index")}, indent=2))
    return 0 if payload["ok"] else 4


def _write(payload: dict, stamp: str) -> None:
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"268_agent_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "268_agent_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
