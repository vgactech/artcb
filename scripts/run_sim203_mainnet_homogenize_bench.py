#!/usr/bin/env python3
"""Simulation 203 — homogenize live VMs onto origin/main + official bench capture.

Operator GO (D-053): keep-book reachable nodes onto this SHA, collect real
hardware/metrics, run machine-local benches where SSH works. Never wipe
blocks.jsonl. Never flip certified_distributed_mainnet.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.crypto_policy import NETWORK_ID, PROTOCOL_VERSION  # noqa: E402
from artcb.devnet_validation import OPERATOR_MAINNET_CERTIFICATION_GO, certification_gate  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps  # noqa: E402

SIM_ID = "e2e203_mainnet_homogenize_bench"
BRANCH = "main"
CTX = ssl._create_unverified_context()
LABELS = {
    "ovh1": NODES["ovh-node-1"].ssh_host or "152.228.144.34",
    "ovh2": NODES["ovh-node-2"].ssh_host or "151.80.107.29",
    "aws3": NODES["aws-node-3"].ssh_host or "51.44.222.232",
    "ovh4": NODES["ovh-node-4"].ssh_host or "91.134.45.8",
}
SSH = {
    "ovh1": (Path.home() / ".ssh" / "artcb_ovh_deploy", ROOT / "deploy" / "ovh_artcb_node_1.known_hosts", LABELS["ovh1"]),
    "ovh2": (Path.home() / ".ssh" / "artcb_ovh_node_2", ROOT / "deploy" / "ovh_artcb_node_2.known_hosts", LABELS["ovh2"]),
    "aws3": (Path.home() / ".ssh" / "artcb_aws_node_3", ROOT / "deploy" / "aws_artcb_node_3.known_hosts", LABELS["aws3"]),
    "ovh4": (Path.home() / ".ssh" / "artcb_ovh_node_4", ROOT / "deploy" / "ovh_artcb_node_4.known_hosts", LABELS["ovh4"]),
}
CERTBOT_NAMES = {
    "ovh1": "artcb.me www.artcb.me n1.artcb.me node.artcb.me",
    "ovh2": "n2.artcb.me",
    "aws3": "n3.artcb.me",
    "ovh4": "n4.artcb.me",
}
NGINX_CONF = ROOT / "deploy" / "nginx" / "artcb-me-http.conf"
ENABLE_SH = ROOT / "scripts" / "enable_artcb_me_nginx.sh"
ENDPOINTS = (
    "/health",
    "/api/v1/metrics",
    "/api/v1/system/hardware",
    "/api/v1/system/optimization",
    "/api/v1/chain/status",
)


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _http(url: str, timeout: int = 25, raw: bool = False) -> tuple[int, dict | str, float]:
    t0 = time.perf_counter()
    req = Request(url, method="GET", headers={"Accept": "application/json, text/html;q=0.8"})
    try:
        with urlopen(req, timeout=timeout, context=CTX if url.startswith("https://") else None) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            rtt = round((time.perf_counter() - t0) * 1000, 1)
            if raw:
                return resp.status, body[:800], rtt
            parsed = json.loads(body) if body.strip().startswith("{") else {"raw": body[:400]}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}, rtt
    except HTTPError as exc:
        rtt = round((time.perf_counter() - t0) * 1000, 1)
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail[:200]}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}, rtt
    except Exception as exc:  # noqa: BLE001
        rtt = round((time.perf_counter() - t0) * 1000, 1)
        return 0, {"error": type(exc).__name__, "url": url}, rtt


def _ssh_key_ready(name: str) -> bool:
    key, _known, _ip = SSH[name]
    return key.is_file() and key.stat().st_size > 80


def _ssh(name: str, remote: str, timeout: int = 180) -> dict:
    key, known, ip = SSH[name]
    if not _ssh_key_ready(name):
        return {"name": name, "returncode": 2, "stdout": "", "stderr": "missing_ssh_key"}
    known_opts = ["-o", "UserKnownHostsFile=" + str(known), "-o", "StrictHostKeyChecking=yes"] if known.is_file() else [
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    cmd = [
        "ssh", "-i", str(key),
        *known_opts,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        f"ubuntu@{ip}",
        remote,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return {"name": name, "returncode": proc.returncode, "stdout": (proc.stdout or "")[-6000:], "stderr": (proc.stderr or "")[-800:]}


def _scp(name: str, local: Path, remote: str) -> dict:
    key, known, ip = SSH[name]
    if not _ssh_key_ready(name):
        return {"name": name, "returncode": 2, "stderr": "missing_ssh_key"}
    known_opts = ["-o", "UserKnownHostsFile=" + str(known), "-o", "StrictHostKeyChecking=yes"] if known.is_file() else [
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    cmd = [
        "scp", "-i", str(key),
        *known_opts,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
        str(local),
        f"ubuntu@{ip}:{remote}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    return {"name": name, "returncode": proc.returncode, "stderr": (proc.stderr or "")[-400:]}


def wait_health(ip: str, *, want: int = 200, tries: int = 24) -> list[dict]:
    rows = []
    for i in range(tries):
        code, _, rtt = _http(f"http://{ip}:8000/health", timeout=5)
        rows.append({"try": i + 1, "http": code, "rtt_ms": rtt})
        if code == want:
            break
        time.sleep(3)
    return rows


def _remote_keep_book_from_origin() -> str:
    return f"""
set -euo pipefail
cd /home/ubuntu/artcb
git fetch origin {BRANCH} || true
if git show-ref --verify --quiet refs/remotes/origin/{BRANCH}; then
  git checkout -f -B {BRANCH} origin/{BRANCH}
  git reset --hard origin/{BRANCH}
else
  git checkout -f -B {BRANCH} FETCH_HEAD || true
fi
SHA=$(git rev-parse HEAD)
BR=$(git rev-parse --abbrev-ref HEAD)
printf 'ARTCB_GIT_SHA=%s\\nARTCB_GIT_BRANCH=%s\\n' "$SHA" "$BR" > /tmp/artcb_release.env
sudo mkdir -p /etc/artcb
sudo cp /tmp/artcb_release.env /etc/artcb/release.env
echo "install.sh not executed"
echo "init_genesis.py not executed"
echo "init-node not executed"
echo "blocks.jsonl not emptied"
echo "DEPLOYED_SHA=$SHA"
echo "DEPLOYED_BRANCH=$BR"
wc -l data/chain/blocks.jsonl
sudo systemctl restart artcb
"""


def _remote_keep_book_from_bundle() -> str:
    return f"""
set -euo pipefail
cd /home/ubuntu/artcb
git fetch /tmp/artcb-me-203.bundle HEAD
git checkout -f -B {BRANCH} FETCH_HEAD
git reset --hard FETCH_HEAD
SHA=$(git rev-parse HEAD)
BR=$(git rev-parse --abbrev-ref HEAD)
printf 'ARTCB_GIT_SHA=%s\\nARTCB_GIT_BRANCH=%s\\n' "$SHA" "$BR" > /tmp/artcb_release.env
sudo mkdir -p /etc/artcb
sudo cp /tmp/artcb_release.env /etc/artcb/release.env
echo "install.sh not executed"
echo "init_genesis.py not executed"
echo "init-node not executed"
echo "blocks.jsonl not emptied"
echo "DEPLOYED_SHA=$SHA"
echo "DEPLOYED_BRANCH=$BR"
echo "BUNDLE_FALLBACK=1"
wc -l data/chain/blocks.jsonl
sudo systemctl restart artcb
"""


def deploy_keep_book(name: str, bundle: Path) -> dict:
    if not _ssh_key_ready(name):
        ping = _ssh(name, "true")
        return {"name": name, "method": "skipped_no_ssh_key", **ping}
    first = _ssh(name, _remote_keep_book_from_origin(), timeout=240)
    if first.get("returncode") == 0 and "DEPLOYED_SHA=" in (first.get("stdout") or ""):
        return {"name": name, "method": "git_fetch_origin", **first}
    scp = _scp(name, bundle, "/tmp/artcb-me-203.bundle")
    second = _ssh(name, _remote_keep_book_from_bundle(), timeout=240)
    return {
        "name": name,
        "method": "git_bundle",
        "origin_attempt": {
            "returncode": first.get("returncode"),
            "stderr": first.get("stderr"),
            "stdout_tail": (first.get("stdout") or "")[-400:],
        },
        "scp": scp,
        **second,
    }


def enable_nginx(name: str) -> dict:
    if not _ssh_key_ready(name):
        return {"name": name, "returncode": 2, "stderr": "missing_ssh_key"}
    scp_conf = _scp(name, NGINX_CONF, "/tmp/artcb-me-http.conf")
    scp_sh = _scp(name, ENABLE_SH, "/tmp/enable_artcb_me_nginx.sh")
    names = CERTBOT_NAMES[name]
    remote = f"""
set -euo pipefail
export ARTCB_NGINX_HTTP_CONF=/tmp/artcb-me-http.conf
export CERTBOT_NAMES='{names}'
bash /tmp/enable_artcb_me_nginx.sh
"""
    ran = _ssh(name, remote, timeout=240)
    return {"name": name, "scp_conf": scp_conf, "scp_sh": scp_sh, **ran}


def collect_node(name: str, ip: str) -> dict:
    row: dict = {"name": name, "ip": ip}
    for path in ENDPOINTS:
        code, body, rtt = _http(f"http://{ip}:8000{path}")
        slim = body if isinstance(body, dict) else {"raw": body}
        if path == "/health" and isinstance(slim, dict):
            machine = slim.get("machine") if isinstance(slim.get("machine"), dict) else {}
            pqc = slim.get("pqc") if isinstance(slim.get("pqc"), dict) else {}
            row["health"] = {
                "http": code,
                "rtt_ms": rtt,
                "git_sha": slim.get("git_sha"),
                "git_branch": slim.get("git_branch"),
                "certified_distributed_mainnet": slim.get("certified_distributed_mainnet"),
                "certification_reason": slim.get("certification_reason"),
                "network_id": slim.get("network_id"),
                "protocol_version": slim.get("protocol_version"),
                "pqc_algo": (pqc.get("policy") or {}).get("signature_algorithm") if isinstance(pqc.get("policy"), dict) else pqc.get("algorithm"),
                "machine": {
                    "tpm_device_present": machine.get("tpm_device_present"),
                    "tpm_type": machine.get("tpm_type"),
                    "virt": machine.get("virt") or machine.get("virtualization"),
                    "cloud": machine.get("cloud"),
                    "assurance": machine.get("assurance") or machine.get("hardware_assurance"),
                },
            }
        elif path.endswith("/metrics") and isinstance(slim, dict):
            net = slim.get("network") if isinstance(slim.get("network"), dict) else {}
            cpu = slim.get("cpu") if isinstance(slim.get("cpu"), dict) else {}
            mem = slim.get("memory") if isinstance(slim.get("memory"), dict) else {}
            row["metrics"] = {
                "http": code,
                "rtt_ms": rtt,
                "cpu_percent": cpu.get("percent"),
                "ram_used_gb": mem.get("used_gb"),
                "ram_total_gb": mem.get("total_gb"),
                "bandwidth_mbps": net.get("bandwidth_mbps"),
                "measured_bandwidth_mbps": net.get("measured_bandwidth_mbps"),
                "estimated_bandwidth_mbps": net.get("estimated_bandwidth_mbps"),
                "fallback_bandwidth_mbps": net.get("fallback_bandwidth_mbps"),
                "bandwidth_source": net.get("bandwidth_source"),
                "sample_sleep_seconds": net.get("sample_sleep_seconds"),
                "metrics_timing": slim.get("metrics_timing"),
            }
        elif path.endswith("/hardware") and isinstance(slim, dict):
            cpu = slim.get("cpu") if isinstance(slim.get("cpu"), dict) else {}
            mem = slim.get("memory") if isinstance(slim.get("memory"), dict) else {}
            disk = slim.get("disk") if isinstance(slim.get("disk"), dict) else {}
            plat = slim.get("platform") if isinstance(slim.get("platform"), dict) else {}
            row["hardware"] = {
                "http": code,
                "rtt_ms": rtt,
                "hostname": plat.get("hostname"),
                "vcpu": cpu.get("logical_cores"),
                "ram_gb": mem.get("total_gb"),
                "disk_gb": disk.get("total_gb"),
                "gpus": slim.get("gpus"),
                "network": slim.get("network"),
            }
        elif path.endswith("/optimization") and isinstance(slim, dict):
            row["optimization"] = {"http": code, "rtt_ms": rtt, "profile": slim}
        elif path.endswith("/chain/status") and isinstance(slim, dict):
            row["chain"] = {
                "http": code,
                "rtt_ms": rtt,
                "height": slim.get("height"),
                "last_hash": slim.get("last_hash"),
                "chain_valid": slim.get("chain_valid"),
            }
        else:
            row[path] = {"http": code, "rtt_ms": rtt}
    return row


def run_machine_bench(name: str) -> dict:
    if not _ssh_key_ready(name):
        return {"name": name, "skipped": True, "reason": "missing_ssh_key"}
    remote = r"""
set -euo pipefail
cd /home/ubuntu/artcb
python3 - <<'PY'
import json, os, platform, subprocess, time
from pathlib import Path
uname = platform.uname()
load = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
mem = subprocess.check_output(["free","-b"], text=True)
print("UNAME", uname.system, uname.release, uname.machine)
print("LOAD", load)
print("NPROC", os.cpu_count())
print("FREE_HEAD", mem.splitlines()[1] if mem else "")
t0 = time.perf_counter()
subprocess.run(["python3","-m","scripts.bench_artcb_real"], cwd="/home/ubuntu/artcb", check=False)
print("BENCH_WALL_S", round(time.perf_counter()-t0, 3))
logs = sorted(Path("/home/ubuntu/artcb/logs").glob("bench_artcb_*.json"))
print("BENCH_JSON", str(logs[-1]) if logs else "")
if logs:
    print(logs[-1].read_text()[:4000])
PY
"""
    return _ssh(name, remote, timeout=300)


def ping_mesh() -> dict:
    matrix = {}
    for src, sip in LABELS.items():
        matrix[src] = {}
        for dst, dip in LABELS.items():
            if src == dst:
                matrix[src][dst] = {"skipped": True}
                continue
            if not _ssh_key_ready(src):
                matrix[src][dst] = {"skipped": True, "reason": "missing_ssh_key"}
                continue
            cmd = f"ping -c 5 -w 8 {dip} | tail -2"
            matrix[src][dst] = _ssh(src, cmd, timeout=20)
    return matrix


def make_bundle() -> tuple[Path, str]:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    path = Path(f"/tmp/artcb-me-203-{os.getpid()}-{sha[:12]}.bundle")
    subprocess.run(
        ["git", "bundle", "create", str(path), "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return path, sha


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle, local_sha = make_bundle()
    keys = {n: _ssh_key_ready(n) for n in LABELS}
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_manifest.json", collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V01-V07-locked-D043",
        simulation_id=SIM_ID,
        seed=203,
        script_path=Path(__file__),
        extra={
            "branch": BRANCH,
            "local_sha": local_sha,
            "keep_book": True,
            "operator_certification_go": OPERATOR_MAINNET_CERTIFICATION_GO,
            "ssh_keys_present": keys,
        },
    ))
    before = {n: collect_node(n, ip) for n, ip in LABELS.items()}
    _write(out_dir, "13_before.json", before)
    deploys = {}
    waits = {}
    nginx = {}
    for name in LABELS:
        deploys[name] = deploy_keep_book(name, bundle)
        if deploys[name].get("method") not in {"skipped_no_ssh_key"}:
            waits[name] = wait_health(LABELS[name])
            nginx[name] = enable_nginx(name)
        else:
            waits[name] = [{"try": 0, "http": 0, "skipped": True}]
            nginx[name] = {"returncode": 2, "skipped": True}
    _write(out_dir, "14_deploys.json", deploys)
    _write(out_dir, "15_waits.json", waits)
    _write(out_dir, "15b_nginx.json", nginx)
    after = {n: collect_node(n, ip) for n, ip in LABELS.items()}
    _write(out_dir, "16_after.json", after)
    benches = {n: run_machine_bench(n) for n in LABELS if keys[n]}
    _write(out_dir, "16c_machine_benches.json", benches)
    mesh = ping_mesh()
    _write(out_dir, "16d_ping_mesh.json", mesh)
    shas = {(row.get("health") or {}).get("git_sha") for row in after.values()}
    branches = {(row.get("health") or {}).get("git_branch") for row in after.values()}
    certs = {(row.get("health") or {}).get("certified_distributed_mainnet") for row in after.values()}
    hashes = {(row.get("chain") or {}).get("last_hash") for row in after.values()}
    reachable = [n for n, row in after.items() if (row.get("health") or {}).get("http") == 200]
    gate = certification_gate()
    summary = {
        "ok": bool(reachable)
        and OPERATOR_MAINNET_CERTIFICATION_GO is False
        and False not in {c is False or c is None for c in certs if c is not None},
        "branch": BRANCH,
        "local_sha": local_sha,
        "reachable": reachable,
        "ssh_keys_present": keys,
        "live_shas": sorted(x for x in shas if x),
        "live_branches": sorted(x for x in branches if x),
        "last_hashes": sorted(x for x in hashes if x),
        "homogeneous_sha": len({x for x in shas if x}) == 1 and local_sha in shas,
        "certified": False,
        "gate_certified": gate.get("certified_distributed_mainnet"),
        "operator_certification_go": OPERATOR_MAINNET_CERTIFICATION_GO,
        "methods": {n: deploys[n].get("method") for n in LABELS},
        "historical_90_tps_is_lab_not_mainnet": True,
        "campaigns": ["machine", "wan_mesh", "local_chain", "distributed"],
        "secrets_printed": False,
        "keep_book": True,
        "network_id": NETWORK_ID,
    }
    _write(out_dir, "17_summary.json", summary)
    print(dumps(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
