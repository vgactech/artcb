#!/usr/bin/env python3
"""Simulation 200 — artcb.me official domain + keep-book deploy of four nodes.

Never orders a domain. Never runs install.sh / init_genesis / init-node.
Never empties blocks.jsonl. Never prints secrets. certified stays false.
OVH2/OVH4 GitHub HTTPS often fails: git bundle fallback (same SHA).
"""

from __future__ import annotations

import json
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

from artcb.config import ARTCB_DNS_A_RECORDS, ARTCB_DOMAIN, ARTCB_DOMAIN_LEGACY  # noqa: E402
from artcb.crypto_policy import NETWORK_ID, PROTOCOL_VERSION  # noqa: E402
from artcb.devnet_validation import certification_gate  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps  # noqa: E402

SIM_ID = "e2e200_artcb_me_official"
BRANCH = "cursor/artcb-me-official-16d8"
OVH1 = NODES["ovh-node-1"].ssh_host or "152.228.144.34"
OVH2 = NODES["ovh-node-2"].ssh_host or "151.80.107.29"
AWS3 = NODES["aws-node-3"].ssh_host or "51.44.222.232"
OVH4 = NODES["ovh-node-4"].ssh_host or "91.134.45.8"
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


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 20) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Accept": "application/json"}
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
    return {
        "name": name,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-800:],
    }


def _scp(name: str, local: Path, remote: str) -> dict:
    key, known, ip = SSH[name]
    cmd = [
        "scp", "-i", str(key),
        "-o", "UserKnownHostsFile=" + str(known),
        "-o", "StrictHostKeyChecking=yes",
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
        code, _ = _http(f"http://{ip}:8000/health", timeout=5)
        rows.append({"try": i + 1, "http": code})
        if code == want:
            break
        time.sleep(3)
    return rows


def _remote_keep_book_from_origin() -> str:
    return f"""
set -euo pipefail
cd /home/ubuntu/artcb
git fetch origin {BRANCH}
if git show-ref --verify --quiet refs/remotes/origin/{BRANCH}; then
  git checkout -B {BRANCH} origin/{BRANCH}
  git reset --hard origin/{BRANCH}
else
  git checkout -B {BRANCH} FETCH_HEAD
  git reset --hard FETCH_HEAD
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
wc -l data/chain/blocks.jsonl
sudo systemctl restart artcb
"""


def _remote_keep_book_from_bundle() -> str:
    return f"""
set -euo pipefail
cd /home/ubuntu/artcb
git fetch /tmp/artcb-me-200.bundle HEAD
git checkout -B {BRANCH} FETCH_HEAD
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
echo "BUNDLE_FALLBACK=1"
wc -l data/chain/blocks.jsonl
sudo systemctl restart artcb
"""


def deploy_keep_book(name: str, bundle: Path) -> dict:
    first = _ssh(name, _remote_keep_book_from_origin(), timeout=240)
    if first.get("returncode") == 0 and "DEPLOYED_SHA=" in (first.get("stdout") or ""):
        return {"name": name, "method": "git_fetch_origin", **first}
    scp = _scp(name, bundle, "/tmp/artcb-me-200.bundle")
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


def probe(name: str, ip: str) -> dict:
    http_c, health = _http(f"http://{ip}:8000/health")
    https_c, _ = _http(f"https://{ip}:8443/health")
    _, chain = _http(f"http://{ip}:8000/api/v1/chain/status")
    p2p_c, p2p = _http(f"http://{ip}:8000/api/v1/p2p/status")
    _, peers_body = _http(f"http://{ip}:8000/api/v1/p2p/peers")
    del_c, _ = _http(f"http://{ip}:8000/api/v1/p2p/peers/peer_probe_unauth", "DELETE")
    peer_rows = [p for p in (peers_body.get("peers") or []) if isinstance(p, dict)]
    pqc = health.get("pqc") if isinstance(health.get("pqc"), dict) else {}
    return {
        "name": name,
        "ip": ip,
        "http": http_c,
        "https": https_c,
        "git_sha": health.get("git_sha"),
        "git_branch": health.get("git_branch"),
        "network_id": health.get("network_id") or p2p.get("network_id"),
        "protocol_version": health.get("protocol_version"),
        "bootstrap_mode": health.get("bootstrap_mode"),
        "certified_distributed_mainnet": health.get("certified_distributed_mainnet"),
        "hybrid_and_function": pqc.get("hybrid_and_function") or health.get("hybrid_and_function"),
        "height": chain.get("height"),
        "last_hash": chain.get("last_hash"),
        "p2p_http": p2p_c,
        "peer_hosts": [p.get("host") for p in peer_rows],
        "unauth_delete_http": del_c,
    }


def make_bundle() -> tuple[Path, str]:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    path = Path("/tmp/artcb-me-200.bundle")
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
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V01-V07-locked-D043",
        simulation_id=SIM_ID,
        seed=200,
        script_path=Path(__file__),
        extra={
            "branch": BRANCH,
            "domain": ARTCB_DOMAIN,
            "legacy_cors": ARTCB_DOMAIN_LEGACY,
            "dns_a": ARTCB_DNS_A_RECORDS,
            "local_sha": local_sha,
            "keep_book": True,
            "order_attempted": False,
        },
    )
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_manifest.json", manifest)
    _write(out_dir, "12_dns_wanted.json", {"domain": ARTCB_DOMAIN, "records": ARTCB_DNS_A_RECORDS})
    before = {n: probe(n, ip) for n, ip in LABELS.items()}
    _write(out_dir, "13_before.json", before)
    deploys = {}
    waits = {}
    for name in LABELS:
        deploys[name] = deploy_keep_book(name, bundle)
        waits[name] = wait_health(LABELS[name])
    _write(out_dir, "14_deploys.json", deploys)
    _write(out_dir, "15_waits.json", waits)
    after = {n: probe(n, ip) for n, ip in LABELS.items()}
    _write(out_dir, "16_after.json", after)
    hashes = {row.get("last_hash") for row in after.values()}
    shas = {row.get("git_sha") for row in after.values()}
    certs = {row.get("certified_distributed_mainnet") for row in after.values()}
    gate = certification_gate(
        {k: "PASS" for k in ("DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07")}
    )
    summary = {
        "ok": all(row.get("http") == 200 for row in after.values())
        and local_sha in shas
        and certs == {False},
        "branch": BRANCH,
        "local_sha": local_sha,
        "live_shas": sorted(x for x in shas if x),
        "last_hashes": sorted(x for x in hashes if x),
        "certified": False,
        "gate_certified": gate.get("certified_distributed_mainnet"),
        "https_200": {n: row.get("https") for n, row in after.items()},
        "http_200": {n: row.get("http") for n, row in after.items()},
        "network_id": NETWORK_ID,
        "order_attempted": False,
        "secrets_printed": False,
        "keep_book": True,
        "methods": {n: deploys[n].get("method") for n in LABELS},
    }
    _write(out_dir, "17_summary.json", summary)
    print(dumps(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
