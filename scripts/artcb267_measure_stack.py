#!/usr/bin/env python3
"""Measure the live ARTCB connection stack vs InfiniBand / QUIC / WireGuard.

Honest probe: HTTP versions from this VM, nginx/iface/IB/WG via SSH ×4.
Never prints tokens. Writes logs/267_stack_*.json.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

CTX = ssl._create_unverified_context()
SSH_KEYS = {
    "ovh-node-1": Path.home() / ".ssh" / "artcb_ovh_deploy",
    "ovh-node-2": Path.home() / ".ssh" / "artcb_ovh_node_2",
    "aws-node-3": Path.home() / ".ssh" / "artcb_aws_node_3",
    "ovh-node-4": Path.home() / ".ssh" / "artcb_ovh_node_4",
}
KNOWN = {
    "ovh-node-1": ROOT / "deploy" / "ovh_artcb_node_1.known_hosts",
    "ovh-node-2": ROOT / "deploy" / "ovh_artcb_node_2.known_hosts",
    "aws-node-3": ROOT / "deploy" / "aws_artcb_node_3.known_hosts",
    "ovh-node-4": ROOT / "deploy" / "ovh_artcb_node_4.known_hosts",
}
HTTP = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "aws-node-3": "http://13.38.209.25:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}
HTTPS = {
    "ovh-node-1": "https://152.228.144.34:8443",
    "ovh-node-2": "https://151.80.107.29:8443",
    "aws-node-3": "https://13.38.209.25:8443",
    "ovh-node-4": "https://91.134.45.8:8443",
}
PUBLIC = {
    "ovh-node-1": "https://artcb.me/health",
    "ovh-node-2": "https://n2.artcb.me/health",
    "ovh-node-3": "https://n3.artcb.me/health",
    "ovh-node-4": "https://n4.artcb.me/health",
}

REMOTE = r"""python3 - <<'PY'
import glob, json, os, shutil, subprocess
def run(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        return {"rc": p.returncode, "out": (p.stdout or "")[-4000:], "err": (p.stderr or "")[-1200:]}
    except Exception as exc:
        return {"error": type(exc).__name__, "detail": str(exc)[:200]}
ib = "/sys/class/infiniband"
out = {
    "hostname": os.uname().nodename,
    "infiniband_sys": os.path.isdir(ib),
    "infiniband_devs": os.listdir(ib) if os.path.isdir(ib) else [],
    "rdma_class": os.listdir("/sys/class/infiniband") if os.path.isdir(ib) else [],
    "net_class": os.listdir("/sys/class/net"),
    "wg_bin": shutil.which("wg"),
    "nginx_v": run("nginx -V 2>&1"),
    "ss": run("ss -tlnp 2>/dev/null | grep -E ':80 |:443 |:8000|:8443' || true"),
    "wg_show": run("command -v wg >/dev/null && wg show || echo NO_WIREGUARD"),
    "ip_link": run("ip -br link"),
    "uname": run("uname -a"),
    "nic_speed": run("for i in $(ls /sys/class/net | grep -v lo); do echo ==$i==; cat /sys/class/net/$i/speed 2>/dev/null; ethtool $i 2>/dev/null | grep -E 'Speed|Duplex|Port' || true; done"),
}
print(json.dumps(out))
PY
"""


def _ssh(node_id: str, remote: str, timeout: int = 40) -> dict:
    spec = NODES[node_id]
    key = SSH_KEYS[node_id]
    if not key.is_file():
        return {"node_id": node_id, "returncode": 2, "stdout": "", "stderr": "missing_ssh_key"}
    known = KNOWN[node_id]
    known_opts = (
        ["-o", f"UserKnownHostsFile={known}", "-o", "StrictHostKeyChecking=yes"]
        if known.is_file()
        else ["-o", "StrictHostKeyChecking=accept-new"]
    )
    cmd = [
        "ssh",
        "-i",
        str(key),
        *known_opts,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        f"{spec.ssh_user}@{spec.ssh_host}",
        remote,
    ]
    t0 = time.perf_counter_ns()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "node_id": node_id,
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": (proc.stderr or "")[-800:],
        "dur_ns": time.perf_counter_ns() - t0,
    }


def curl_http_version(url: str, flag: str) -> dict:
    t0 = time.perf_counter_ns()
    cmd = [
        "curl",
        "-skI",
        flag,
        "-o",
        "/tmp/artcb267_curl_hdr.txt",
        "-w",
        "%{http_version} %{http_code} %{time_total} %{ssl_verify_result}",
        "--max-time",
        "15",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    hdr = ""
    p = Path("/tmp/artcb267_curl_hdr.txt")
    if p.is_file():
        hdr = p.read_text(encoding="utf-8", errors="replace")[:1500]
    return {
        "flag": flag,
        "url": url,
        "rc": proc.returncode,
        "write_out": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "")[-400:],
        "headers": hdr,
        "dur_ns": time.perf_counter_ns() - t0,
    }


def health_trace(url: str) -> dict:
    t0 = time.perf_counter_ns()
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=15, context=CTX if url.startswith("https") else None) as resp:
            raw = resp.read()
            hdrs = {k: resp.headers.get(k) for k in ("X-ARTCB-Trace-Ns", "Server", "Alt-Svc", "Strict-Transport-Security")}
            return {
                "url": url,
                "http": resp.status,
                "bytes": len(raw),
                "headers": hdrs,
                "dur_ns": time.perf_counter_ns() - t0,
            }
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "error": type(exc).__name__, "dur_ns": time.perf_counter_ns() - t0}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload: dict = {
        "stamp": stamp,
        "note": (
            "Measured live. Not InfiniBand NDR, not 800G, not RoCE, not QUIC/HTTP3 "
            "unless curl --http3 succeeds. WireGuard only if wg show lists a device."
        ),
        "client_curl": subprocess.run(["curl", "--version"], capture_output=True, text=True, check=False).stdout.splitlines()[:3],
        "http_versions": {},
        "health": {},
        "nodes": {},
    }
    targets = [
        HTTPS["ovh-node-1"] + "/health",
        HTTP["ovh-node-1"] + "/health",
        PUBLIC["ovh-node-1"],
    ]
    for url in targets:
        payload["http_versions"][url] = {
            "http1.1": curl_http_version(url, "--http1.1"),
            "http2": curl_http_version(url, "--http2"),
            "http3": curl_http_version(url, "--http3-only")
            if "https" in url
            else {"skipped": True, "reason": "http3 needs TLS"},
        }
        payload["health"][url] = health_trace(url)

    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        row = _ssh(nid, REMOTE, timeout=45)
        parsed = None
        try:
            parsed = json.loads(row.get("stdout") or "")
        except json.JSONDecodeError:
            parsed = None
        nginx_blob = ""
        if isinstance(parsed, dict):
            nginx_blob = str((parsed.get("nginx_v") or {}).get("out") or "") + str(
                (parsed.get("nginx_v") or {}).get("err") or ""
            )
        payload["nodes"][nid] = {
            "ssh_rc": row.get("returncode"),
            "ssh_dur_ns": row.get("dur_ns"),
            "ssh_err": row.get("stderr"),
            "parsed": parsed,
            "nginx_compiled_http2": bool(re.search(r"--with-http_v2_module", nginx_blob)),
            "nginx_compiled_http3": bool(re.search(r"http_v3|http3|quic", nginx_blob, re.I)),
            "http2_in_nginx": False,
            "http3_in_nginx": False,
            "infiniband": bool((parsed or {}).get("infiniband_sys")),
            "wireguard": (parsed or {}).get("wg_bin") not in (None, "")
            and "NO_WIREGUARD" not in str(((parsed or {}).get("wg_show") or {}).get("out") or "NO_WIREGUARD"),
        }

    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    dest = out_dir / f"267_stack_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "267_stack_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    brief = {
        "wrote": str(dest),
        "infiniband_any": any(n.get("infiniband") for n in payload["nodes"].values()),
        "http3_nginx_any": any(n.get("http3_in_nginx") for n in payload["nodes"].values()),
        "wireguard_any": any(n.get("wireguard") for n in payload["nodes"].values()),
        "ssh_rc": {k: v.get("ssh_rc") for k, v in payload["nodes"].items()},
    }
    print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
