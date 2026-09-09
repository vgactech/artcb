#!/usr/bin/env python3
"""R287 live — RFC1918 Mac is not reachable from cloud; tunnel must exist.

Does not start ngrok on this cloud VM (that would not reach the Mac).
Does not invent a Mac health SHA. CERTIFIED_100 stays false. N04 last.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.mac_node_access import json_contains_private_key, probe_mac_tunnel  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402
from artcb.p2p.public_url import public_register_url_ok  # noqa: E402

HTTP = l265.HTTP


def _ngrok_api_key() -> str:
    token = (os.environ.get("DOPPLER_TOKEN") or "").strip()
    if not token:
        return ""
    url = (
        "https://api.doppler.com/v3/configs/config/secret"
        "?project=artcb-blockchain&config=dev&name=" + quote("NGROK_API_KEY")
    )
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return ""
    return str(((payload.get("value") or {}).get("computed") or "")).strip()


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    key = _ngrok_api_key()
    mac = probe_mac_tunnel(ngrok_api_key=key)
    lan_url = mac.get("lan_health_http") or "http://10.234.49.2:8001"
    p2p_ok, p2p_reason = public_register_url_ok(lan_url)
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    chain = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/chain/status", timeout=12)
    payload = {
        "run": "287_mac_tunnel",
        "stamp": stamp,
        "certified_100": False,
        "official_shas": shas,
        "ovh1_height": chain.get("height"),
        "ovh1_last_hash": chain.get("last_hash"),
        "p2p_register_lan": {"url": lan_url, "ok": p2p_ok, "reason": p2p_reason},
        "mac": mac,
        "honesty": {
            "did_not_start_ngrok_on_cloud_vm": True,
            "mac_not_official_compute": mac.get("official_compute") is False,
            "no_invented_mac_sha": mac.get("verdict", {}).get("mac_health_sha") is None,
            "no_secret_in_json": not json_contains_private_key(mac),
        },
    }
    if json_contains_private_key(payload):
        print(json.dumps({"ok": False, "error": "refusing_to_print_secret_material"}))
        return 2
    out = ROOT / "logs" / "287_mac_tunnel_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if p2p_ok or mac.get("official_compute"):
        return 2
    if (mac.get("verdict") or {}).get("tunnel") == "PASS":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
