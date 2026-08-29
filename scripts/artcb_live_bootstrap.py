#!/usr/bin/env python3
"""Activate the live ARTCB node for this agent process.

Order: Cursor env → Doppler → ~/.artcb/cursor_agent.env → SSH pull from OVH.
Prints metadata only. Never prints the API key.
Exit 0 if /health is reachable. Exit 3 if the key is missing but the node is up.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import (  # noqa: E402
    apply_key_to_environ,
    fetch_doppler_secret,
    http_json,
    pull_remote_agent_env,
    resolve_api_key,
    resolve_api_url,
    write_local_env,
)


def _load_key() -> tuple[str, str]:
    key = resolve_api_key()
    if key:
        return key, "env_or_local_file"
    doppler_key = fetch_doppler_secret("ARTCB_API_KEY") or fetch_doppler_secret("ARTCB_NODE_API_KEY")
    if doppler_key.startswith("artcb_"):
        write_local_env({"ARTCB_API_URL": resolve_api_url(), "ARTCB_API_KEY": doppler_key})
        return doppler_key, "doppler"
    pulled = pull_remote_agent_env()
    remote_key = pulled.get("ARTCB_API_KEY", "")
    if remote_key.startswith("artcb_"):
        return remote_key, "ssh_node"
    return "", "missing"


def main() -> int:
    url = resolve_api_url()
    os.environ["ARTCB_API_URL"] = url
    key, source = _load_key()
    if key:
        apply_key_to_environ(key)

    health_code, health = http_json("GET", f"{url}/health")
    me_code, me = (0, {})
    if key:
        me_code, me = http_json("GET", f"{url}/api/v1/api-keys/me", api_key=key)
    econ_code, econ = http_json("GET", f"{url}/api/v1/economics/params")
    proto_code, proto = http_json("GET", f"{url}/api/v1/mining/protocol/status")

    status = {
        "ok": health_code == 200,
        "live_url": url,
        "key_source": source,
        "key_present": bool(key),
        "health_http": health_code,
        "git_sha": health.get("git_sha") if isinstance(health, dict) else None,
        "git_branch": health.get("git_branch") if isinstance(health, dict) else None,
        "pqc": (health.get("pqc") or {}).get("algorithm") if isinstance(health, dict) else None,
        "me_http": me_code,
        "key_id": me.get("key_id") if isinstance(me, dict) else None,
        "scopes": me.get("scopes") if isinstance(me, dict) else None,
        "economics_http": econ_code,
        "protocol_http": proto_code,
        "h_adult": proto.get("h_adult") if isinstance(proto, dict) else None,
        "token_printed": False,
    }
    print(json.dumps(status, indent=2))
    if health_code != 200:
        return 2
    if not key or me_code != 200:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
