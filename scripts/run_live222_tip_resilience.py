#!/usr/bin/env python3
"""Live 222 — V-01-B: OVH1 stopped after the 221 tip, others still serve it.

Does not wipe blocks.jsonl. Restarts OVH1. Does not flip certification.
Does not create a new org (that would be a concurrent producer).
"""

from __future__ import annotations

import json
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTX = ssl._create_unverified_context()
OVH1_SSH = Path.home() / ".ssh" / "artcb_ovh_deploy"
KNOWN = ROOT / "deploy" / "ovh_artcb_node_1.known_hosts"
NODES = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "aws-node-3": "http://51.44.222.232:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}


def _http(url: str, timeout: int = 8) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    ctx = CTX if url.startswith("https") else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except Exception as exc:
        return 0, {"error": type(exc).__name__}


def _tip(node_id: str) -> dict:
    base = NODES[node_id]
    h_code, health = _http(f"{base}/health")
    s_code, status = _http(f"{base}/api/v1/p2p/status")
    return {
        "node_id": node_id,
        "health_http": h_code,
        "git_sha": health.get("git_sha") if isinstance(health, dict) else None,
        "certified": health.get("certified_distributed_mainnet") if isinstance(health, dict) else None,
        "status_http": s_code,
        "last_hash": status.get("last_hash") if isinstance(status, dict) else None,
        "public_state_digest": status.get("public_state_digest") if isinstance(status, dict) else None,
        "public_blocks_local": status.get("public_blocks_local") if isinstance(status, dict) else None,
    }


def _ssh(remote: str, timeout: int = 40) -> dict:
    proc = subprocess.run(
        [
            "ssh", "-i", str(OVH1_SSH),
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={KNOWN}",
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "ubuntu@152.228.144.34", remote,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-400:],
        "stderr_class": (proc.stderr or "")[:80],
    }


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    before = {nid: _tip(nid) for nid in NODES}
    hashes = {nid: before[nid].get("last_hash") for nid in NODES}
    want_tip = before["ovh-node-2"].get("last_hash")
    stop = _ssh("sudo systemctl stop artcb; echo STOPPED; systemctl is-active artcb || true")
    time.sleep(2)
    ovh1_down = _tip("ovh-node-1")
    others_during = {nid: _tip(nid) for nid in ("ovh-node-2", "aws-node-3", "ovh-node-4")}
    start = _ssh("sudo systemctl start artcb; echo STARTED")
    recovered = None
    for _ in range(24):
        time.sleep(3)
        recovered = _tip("ovh-node-1")
        if recovered.get("health_http") == 200 and recovered.get("last_hash"):
            break
    after = {nid: _tip(nid) for nid in NODES}
    others_same = all(
        row.get("last_hash") == want_tip and row.get("health_http") == 200
        for row in others_during.values()
    )
    payload = {
        "stamp": stamp,
        "scenario": "V-01-B_ovh1_stopped_others_keep_tip",
        "before": before,
        "stop": {"returncode": stop["returncode"], "active": "inactive" in stop["stdout"] or "STOPPED" in stop["stdout"]},
        "ovh1_during": {"health_http": ovh1_down.get("health_http"), "reachable": ovh1_down.get("health_http") == 200},
        "others_during": others_during,
        "start_returncode": start["returncode"],
        "ovh1_recovered": recovered,
        "after": after,
        "four_same_before": len(set(hashes.values())) == 1 and all(hashes.values()),
        "others_kept_tip_while_ovh1_down": others_same,
        "ovh1_book_restored": (recovered or {}).get("last_hash") == want_tip,
        "certified_others_during": all(row.get("certified") is True for row in others_during.values()),
        "ovh1_wiped": False,
        "token_printed": False,
    }
    dest = ROOT / "logs" / f"222_live_{stamp}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    evidence = ROOT / "rapports" / "evidence" / f"222_live_{stamp}.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({
        "wrote": str(dest),
        "evidence": str(evidence),
        "others_kept_tip_while_ovh1_down": payload["others_kept_tip_while_ovh1_down"],
        "ovh1_book_restored": payload["ovh1_book_restored"],
        "ovh1_during_reachable": payload["ovh1_during"]["reachable"],
        "token_printed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
