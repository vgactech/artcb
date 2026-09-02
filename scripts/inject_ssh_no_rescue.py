#!/usr/bin/env python3
"""Inject or verify per-node SSH without rescue.

FORBID_RESCUE: never boot a rescue image, never mount a rescue
disk, never wipe the book. Prefer Doppler SSH_PRIVATE_KEY.

If KEY_API_ARTCB_DOPPLER_4 is present, this script may request an OVH
VNC URL (running instance, not rescue) and report it — it does not
type into the console automatically.

Never prints PEM material.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.node_registry import NODES  # noqa: E402

FORBID_RESCUE = True
OVH_BASE = "https://eu.api.ovh.com/1.0"

SSH_FILES = {
    "ovh-node-1": Path.home() / ".ssh" / "artcb_ovh_deploy",
    "ovh-node-2": Path.home() / ".ssh" / "artcb_ovh_node_2",
    "aws-node-3": Path.home() / ".ssh" / "artcb_aws_node_3",
    "ovh-node-4": Path.home() / ".ssh" / "artcb_ovh_node_4",
}


def _ssh_probe(node_id: str) -> dict[str, Any]:
    spec = NODES[node_id]
    key = SSH_FILES[node_id]
    host = spec.ssh_host
    if not host:
        return {"node_id": node_id, "ssh": False, "reason": "no_host"}
    if not key.is_file() or key.stat().st_size < 80:
        return {"node_id": node_id, "ssh": False, "reason": "missing_pem", "host": host}
    cmd = [
        "ssh",
        "-i",
        str(key),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{spec.ssh_user}@{host}",
        "echo ssh-ok; hostname; test ! -d /mnt/rescue -a ! -d /rescue; echo no_rescue_root=$?",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    ok = proc.returncode == 0 and "ssh-ok" in (proc.stdout or "")
    return {
        "node_id": node_id,
        "host": host,
        "ssh": ok,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-200:],
        "stderr_tail": (proc.stderr or "")[-160:],
        "rescue_forbidden": FORBID_RESCUE,
    }


def _ovh4_console_url() -> dict[str, Any]:
    """Request running-instance VNC (not rescue). Needs artcb-4 credentials."""
    token = (os.environ.get("KEY_API_ARTCB_DOPPLER_4") or "").strip()
    if not token:
        return {"ok": False, "reason": "KEY_API_ARTCB_DOPPLER_4_absent"}
    req = Request(
        "https://api.doppler.com/v3/configs/config/secrets?project=artcb-4&config=dev",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {"ok": False, "reason": "doppler_artcb4_unreachable"}
    secrets = payload.get("secrets") or {}

    def _sec(name: str) -> str:
        meta = secrets.get(name) or {}
        return str(meta.get("computed") or meta.get("raw") or "").strip() if isinstance(meta, dict) else ""

    ak, as_, ck = _sec("OVH_APPLICATION_KEY"), _sec("OVH_APPLICATION_SECRET"), _sec("OVH_CONSUMER_KEY")
    if not (ak and as_ and ck):
        return {"ok": False, "reason": "ovh4_api_keys_missing_in_doppler"}
    project = "926bb1d6755e4f2c98ae9db06ef44e4f"
    instance = "22dc6a47-5b79-4084-82d7-eabb4f5b2680"
    with urlopen(f"{OVH_BASE}/auth/time", timeout=10) as resp:
        ts = str(int(json.loads(resp.read().decode())))
    path = f"/cloud/project/{project}/instance/{instance}/vnc"
    url = OVH_BASE + path
    sig_input = "+".join([as_, ck, "POST", url, "", ts])
    sig = "$1$" + hashlib.sha1(sig_input.encode("utf-8")).hexdigest()
    headers = {
        "X-Ovh-Application": ak,
        "X-Ovh-Timestamp": ts,
        "X-Ovh-Signature": sig,
        "X-Ovh-Consumer": ck,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    req2 = Request(url, data=None, method="POST", headers=headers)
    try:
        with urlopen(req2, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return {
            "ok": True,
            "console": "vnc",
            "rescue": False,
            "url_present": bool(data.get("url") or data.get("access") or data.get("type")),
            "keys": sorted(data.keys()) if isinstance(data, dict) else [],
        }
    except HTTPError as exc:
        return {"ok": False, "http": exc.code, "reason": "vnc_failed"}


def main() -> int:
    loader = ROOT / "scripts" / "load_node_ssh_keys.py"
    if loader.is_file():
        subprocess.run([sys.executable, str(loader)], check=False)
    rows = [_ssh_probe(nid) for nid in ("ovh-node-1", "ovh-node-2", "aws-node-3", "ovh-node-4")]
    console = _ovh4_console_url()
    report = {
        "forbid_rescue": FORBID_RESCUE,
        "nodes": rows,
        "ovh4_console": console,
        "ssh_ok": [r["node_id"] for r in rows if r.get("ssh")],
        "ssh_blocked": [r["node_id"] for r in rows if not r.get("ssh")],
        "secrets_printed": False,
    }
    print(json.dumps(report, indent=2))
    ovh4 = next((r for r in rows if r["node_id"] == "ovh-node-4"), {})
    return 0 if ovh4.get("ssh") else 2


if __name__ == "__main__":
    raise SystemExit(main())
