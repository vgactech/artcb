#!/usr/bin/env python3
"""R286 live — Cursor → mac-node-local via Doppler SSH.

Fail-closed. Never prints CURSOR_SSH_PRIVATE_KEY / Doppler tokens.
Does not add the Mac to OFFICIAL_COMPUTE. Does not invent a Mac health SHA.
CERTIFIED_100 stays false. N04 last. PRE_R273 GAP kept.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.mac_node_access import json_contains_private_key, probe_mac_access  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    mac = probe_mac_access()
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    chain = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/chain/status", timeout=12)
    payload = {
        "run": "286_mac_ssh",
        "stamp": stamp,
        "certified_100": False,
        "official_shas": shas,
        "ovh1_height": chain.get("height"),
        "ovh1_last_hash": chain.get("last_hash"),
        "ovh1_last_index": chain.get("last_index"),
        "mac": mac,
        "honesty": {
            "mac_not_official_compute": mac.get("official_compute") is False,
            "no_invented_mac_sha": mac.get("verdict", {}).get("mac_health_sha") is None,
            "no_private_key_in_json": not json_contains_private_key(mac),
        },
    }
    if json_contains_private_key(payload):
        print(json.dumps({"ok": False, "error": "refusing_to_print_secret_material"}))
        return 2
    out = ROOT / "logs" / "286_mac_ssh_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    latest = ROOT / "logs" / "286_mac_ssh_latest.json"
    latest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    v = mac.get("verdict") or {}
    # Success of the *probe* (honest FAIL is ok). Leak or official-compute recast is not.
    if mac.get("official_compute") or json_contains_private_key(payload):
        return 2
    if v.get("ssh_login") == "PASS" and v.get("lan_path") == "PASS":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
