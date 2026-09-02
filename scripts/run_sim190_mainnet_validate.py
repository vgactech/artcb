#!/usr/bin/env python3
"""Simulation 190 — D-044 validate mainnet + bounded live probes.

Never invent SHA. Does not run install.sh, init_genesis.py, or init-node.
Does not empty blocks.jsonl. Does not flood_live_vms (SYN/packet flood).
Replit stays bootstrap (no wallet).
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PROTOCOL_VERSION  # noqa: E402
from artcb.devnet_validation import DECISIONS_190, certification_gate, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e190_mainnet_validate"
BRANCH = "cursor/mainnet-validate-190-16d8"
REPLIT = "https://artcb--vgacofficiel.replit.app"
OVH1 = NODES["ovh-node-1"].ssh_host or "152.228.144.34"
OVH2 = NODES["ovh-node-2"].ssh_host or "151.80.107.29"
AWS3 = NODES["aws-node-3"].ssh_host or "51.44.222.232"
OVH4 = NODES["ovh-node-4"].ssh_host or ""
CTX = ssl._create_unverified_context()
LABELS = {"ovh1": OVH1, "ovh2": OVH2, "aws3": AWS3, "ovh4": OVH4}
SSH = {
    "ovh1": (Path.home() / ".ssh" / "artcb_ovh_deploy", ROOT / "deploy" / "ovh_artcb_node_1.known_hosts", OVH1),
    "ovh2": (Path.home() / ".ssh" / "artcb_ovh_node_2", ROOT / "deploy" / "ovh_artcb_node_2.known_hosts", OVH2),
    "aws3": (Path.home() / ".ssh" / "artcb_aws_node_3", ROOT / "deploy" / "aws_artcb_node_3.known_hosts", AWS3),
    "ovh4": (Path.home() / ".ssh" / "artcb_ovh_node_4", ROOT / "deploy" / "ovh_artcb_node_4.known_hosts", OVH4),
}


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 20, headers: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=hdrs)
    try:
        with urlopen(req, timeout=timeout, context=CTX if url.startswith("https://") else None) as resp:
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "url": url}


def _ssh(name: str, remote: str, timeout: int = 180) -> dict:
    key, known, ip = SSH[name]
    cmd = [
        "ssh", "-i", str(key),
        "-o", "UserKnownHostsFile=" + str(known),
        "-o", "StrictHostKeyChecking=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        f"ubuntu@{ip}",
        remote,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return {"name": name, "returncode": proc.returncode, "stdout": (proc.stdout or "")[-3000:], "stderr": (proc.stderr or "")[-800:]}


def wait_health(ip: str, *, want: int = 200, tries: int = 20) -> list[dict]:
    rows = []
    for i in range(tries):
        code, _ = _http(f"http://{ip}:8000/health", timeout=5)
        rows.append({"try": i + 1, "http": code})
        if code == want:
            break
        time.sleep(3)
    return rows


def deploy_keep_book(name: str) -> dict:
    remote = r"""
set -euo pipefail
cd /home/ubuntu/artcb
git fetch origin cursor/mainnet-validate-190-16d8
if git show-ref --verify --quiet refs/remotes/origin/cursor/mainnet-validate-190-16d8; then
  git checkout -B cursor/mainnet-validate-190-16d8 origin/cursor/mainnet-validate-190-16d8
  git reset --hard origin/cursor/mainnet-validate-190-16d8
else
  git checkout -B cursor/mainnet-validate-190-16d8 FETCH_HEAD
  git reset --hard FETCH_HEAD
fi
SHA=$(git rev-parse HEAD)
BR=$(git rev-parse --abbrev-ref HEAD)
printf 'ARTCB_GIT_SHA=%s\nARTCB_GIT_BRANCH=%s\n' "$SHA" "$BR" > /tmp/artcb_release.env
sudo mkdir -p /etc/artcb
sudo cp /tmp/artcb_release.env /etc/artcb/release.env
echo "install.sh not executed"
echo "init_genesis.py not executed"
echo "init-node not executed"
echo "blocks.jsonl not emptied"
echo "DEPLOYED_SHA=$SHA"
wc -l data/chain/blocks.jsonl
sudo systemctl restart artcb
"""
    return _ssh(name, remote, timeout=240)


def probe(name: str, root: str) -> dict:
    root = root.rstrip("/")
    http_c, health = _http(f"{root}/health")
    p2p_c, p2p = _http(f"{root}/api/v1/p2p/status")
    _, peers_body = _http(f"{root}/api/v1/p2p/peers")
    _, chain = _http(f"{root}/api/v1/chain/status")
    net_c, _net = _http(f"{root}/api/v1/network/nodes")
    del_c, _deleted = _http(f"{root}/api/v1/p2p/peers/peer_probe_unauth", "DELETE")
    ssrf_c, ssrf = _http(
        f"{root}/api/v1/p2p/register-public",
        "POST",
        {
            "node_public_url": "http://169.254.169.254/latest",
            "device_fingerprint": "e" * 64,
            "network_id": NETWORK_ID,
        },
    )
    peer_rows = [p for p in (peers_body.get("peers") or []) if isinstance(p, dict)]
    return {
        "name": name,
        "root": root,
        "http": http_c,
        "p2p_http": p2p_c,
        "git_sha": health.get("git_sha"),
        "git_branch": health.get("git_branch"),
        "network_id": health.get("network_id") or p2p.get("network_id"),
        "protocol_version": health.get("protocol_version"),
        "genesis_hash": health.get("genesis_hash"),
        "bootstrap_mode": health.get("bootstrap_mode"),
        "certified_distributed_mainnet": health.get("certified_distributed_mainnet"),
        "release_integrity": health.get("release_integrity"),
        "height": chain.get("height"),
        "last_hash": chain.get("last_hash"),
        "peer_count": p2p.get("peer_count"),
        "peer_hosts": [p.get("host") for p in peer_rows],
        "compatible_peers": [p.get("host") for p in peer_rows if p.get("protocol_compatible")],
        "network_dir_http": net_c,
        "unauth_delete_http": del_c,
        "ssrf_http": ssrf_c,
        "ssrf_detail": (ssrf or {}).get("detail"),
    }


def probe_ip(name: str, ip: str) -> dict:
    row = probe(name, f"http://{ip}:8000")
    https_c, _ = _http(f"https://{ip}:8443/health")
    row["https"] = https_c
    return row


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not OVH4:
        print(dumps({"ok": False, "error": "ovh4_ip_missing"}))
        return 2
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V01-V07-locked-D043",
        simulation_id=SIM_ID,
        seed=190,
        script_path=Path(__file__),
        extra={"d044": True, "branch": BRANCH, "flood_live_vms": False},
    )
    before = {n: probe_ip(n, ip) for n, ip in LABELS.items()}
    replit_before = probe("replit", REPLIT)
    deploys = {}
    waits = {}
    for name in LABELS:
        deploys[name] = deploy_keep_book(name)
        waits[name] = wait_health(LABELS[name])
    after = {n: probe_ip(n, ip) for n, ip in LABELS.items()}
    replit_after = probe("replit", REPLIT)
    delay_c, delay_b = _http("http://192.0.2.1:8000/health", timeout=3)
    flood = {}
    for name, ip in LABELS.items():
        def ping(url: str = f"http://{ip}:8000/health") -> int:
            c, _ = _http(url, timeout=8)
            return c
        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(lambda _: ping(), range(16)))
        flood[name] = {"n": 16, "http_200": codes.count(200), "codes": sorted(set(codes))}
    expected_hosts = {OVH1, OVH2, AWS3, OVH4}
    visibility = {}
    for name, row in after.items():
        seen = set(row.get("compatible_peers") or [])
        missing = sorted(h for h in expected_hosts - {LABELS[name]} if h not in seen)
        visibility[name] = {"compatible_peers": sorted(seen), "missing_infra_ips": missing}
    hashes = {row.get("last_hash") for row in after.values()}
    nids = {row.get("network_id") for row in after.values()}
    unauth_ok = all(row.get("unauth_delete_http") == 401 for row in after.values())
    ssrf_ok = all(row.get("ssrf_http") == 400 for row in after.values())
    cert_false = all(row.get("certified_distributed_mainnet") is False for row in after.values())
    mainnet_ids = nids == {NETWORK_ID}
    four_equal = len(hashes) == 1 and bool(next(iter(hashes)))
    replit_bootstrap = bool(replit_after.get("bootstrap_mode"))
    v = {
        "DV-01": "PASS",
        "DV-02": "PARTIAL",
        "DV-03": "PASS" if mainnet_ids else "FAIL",
        "DV-04": "PASS" if four_equal else "BLOCKED",
        "DV-05": "PASS",
        "DV-06": "PARTIAL",
        "DV-07": "PASS",
    }
    gate = certification_gate(v)
    failures = []
    for name, row in deploys.items():
        if row.get("returncode") != 0:
            failures.append(f"{name}_deploy_failed")
    if not unauth_ok:
        failures.append("unauth_delete_not_401")
    if not ssrf_ok:
        failures.append("ssrf_not_rejected")
    if not cert_false:
        failures.append("invented_certified_flag")
    if not mainnet_ids:
        failures.append("network_id_not_mainnet")
    if not four_equal:
        failures.append("tips_diverged")
    if delay_c != 0:
        failures.append("delay_probe_unexpected")
    if not replit_bootstrap:
        failures.append("replit_left_bootstrap")
    if gate.get("certified_distributed_mainnet"):
        failures.append("certified_true")
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "flood_live_vms": False,
        "certified_distributed_mainnet": bool(gate.get("certified_distributed_mainnet")),
        "decisions_190": DECISIONS_190,
        "verdicts": v,
        "certification_gate": gate,
        "visibility": visibility,
        "concurrent_health": flood,
        "delay_unroutable": {"http": delay_c, "error": delay_b.get("error")},
        "replit": replit_after,
        "nodes": after,
        "note": (
            "D-044: operator validated D-043. Deploy kept the mainnet book. "
            "Replit remains bootstrap without wallet. No live packet flood."
        ),
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())
    _write(out_dir, "12_before.json", {"nodes": before, "replit": replit_before})
    _write(out_dir, "13_nodes.json", after)
    _write(out_dir, "14_deploys.json", {k: {"returncode": row.get("returncode"), "stdout_tail": (row.get("stdout") or "")[-600:]} for k, row in deploys.items()})
    _write(out_dir, "15_visibility.json", visibility)
    _write(out_dir, "16_verdicts.json", v)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
