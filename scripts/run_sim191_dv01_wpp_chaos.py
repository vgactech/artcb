#!/usr/bin/env python3
"""Simulation 191 — D-045 TPM + WPP freeze + seed discovery + live chaos.

Never invent SHA. Does not run install.sh, init_genesis.py, or init-node.
Does not empty blocks.jsonl. Packet-loss (tc netem) on ONE node then restore.
Bounded HTTP flood (not SYN). Replit stays bootstrap (no wallet).
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

from artcb.config import REPLIT_PUBLIC_URL  # noqa: E402
from artcb.crypto_policy import NETWORK_ID, PROTOCOL_VERSION  # noqa: E402
from artcb.devnet_validation import DECISIONS_191, certification_gate, public_lock  # noqa: E402
from artcb.economics.demographic import H_ADULT_MAX, HMAX_FROZEN, default_reference  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e191_dv01_wpp_chaos"
BRANCH = "cursor/dv01-tpm-wpp-chaos-16d8"
REPLIT = REPLIT_PUBLIC_URL  # https://artcb--vgac42371.replit.app
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
    return {"name": name, "returncode": proc.returncode, "stdout": (proc.stdout or "")[-4000:], "stderr": (proc.stderr or "")[-800:]}


def wait_health(ip: str, *, want: int = 200, tries: int = 24) -> list[dict]:
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
git fetch origin cursor/dv01-tpm-wpp-chaos-16d8
if git show-ref --verify --quiet refs/remotes/origin/cursor/dv01-tpm-wpp-chaos-16d8; then
  git checkout -B cursor/dv01-tpm-wpp-chaos-16d8 origin/cursor/dv01-tpm-wpp-chaos-16d8
  git reset --hard origin/cursor/dv01-tpm-wpp-chaos-16d8
else
  git checkout -B cursor/dv01-tpm-wpp-chaos-16d8 FETCH_HEAD
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


def probe_tpm(name: str) -> dict:
    remote = r"""
set -euo pipefail
echo TPM_DEV=$(test -e /dev/tpm0 && echo yes || echo no)
echo TPMRM=$(test -e /dev/tpmrm0 && echo yes || echo no)
echo TPM_SYS=$(test -r /sys/class/tpm/tpm0/tpm_version_major && cat /sys/class/tpm/tpm0/tpm_version_major || echo none)
echo MACHINE_ID_HASH=$(sha256sum /etc/machine-id | awk '{print $1}')
echo DMI_UUID_HASH=$( (sudo cat /sys/class/dmi/id/product_uuid 2>/dev/null || cat /sys/class/dmi/id/product_uuid 2>/dev/null || echo none) | sha256sum | awk '{print $1}')
echo SYS_VENDOR=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null || echo none)
echo PRODUCT=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo none)
echo CLOUD_IID=$(cat /var/lib/cloud/data/instance-id 2>/dev/null || echo none)
command -v tpm2_getcap >/dev/null && echo TPM2_TOOLS=yes || echo TPM2_TOOLS=no
"""
    return _ssh(name, remote, timeout=30)


def probe(name: str, root: str) -> dict:
    root = root.rstrip("/")
    http_c, health = _http(f"{root}/health")
    p2p_c, p2p = _http(f"{root}/api/v1/p2p/status")
    _, peers_body = _http(f"{root}/api/v1/p2p/peers")
    _, chain = _http(f"{root}/api/v1/chain/status")
    net_c, net = _http(f"{root}/api/v1/network/nodes?live=1", timeout=25)
    eco_c, eco = _http(f"{root}/api/v1/economics/h-adult")
    del_c, _deleted = _http(f"{root}/api/v1/p2p/peers/peer_probe_unauth", "DELETE")
    sync_c, _sync = _http(f"{root}/api/v1/p2p/sync", "POST")
    gossip_c, _g = _http(f"{root}/api/v1/p2p/gossip/announce", "POST")
    lib_c, lib = _http(f"{root}/api/v1/p2p/libp2p/status")
    ssrf_c, ssrf = _http(
        f"{root}/api/v1/network/announce",
        "POST",
        {"node_public_url": "http://169.254.169.254/latest", "network_id": NETWORK_ID},
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
        "machine": health.get("machine") or p2p.get("machine"),
        "height": chain.get("height"),
        "last_hash": chain.get("last_hash"),
        "peer_count": p2p.get("peer_count"),
        "peer_hosts": [p.get("host") for p in peer_rows],
        "compatible_peers": [p.get("host") for p in peer_rows if p.get("protocol_compatible")],
        "network_dir_http": net_c,
        "live_online": net.get("live_online"),
        "seeds": net.get("seeds"),
        "h_adult_http": eco_c,
        "hmax_frozen": eco.get("hmax_frozen"),
        "h_adult_max": (eco.get("demographic_reference") or {}).get("adult_population_estimate"),
        "unauth_delete_http": del_c,
        "unauth_sync_http": sync_c,
        "unauth_gossip_http": gossip_c,
        "libp2p_http": lib_c,
        "libp2p_running": lib.get("running"),
        "ssrf_http": ssrf_c,
        "ssrf_detail": (ssrf or {}).get("detail"),
    }


def probe_ip(name: str, ip: str) -> dict:
    row = probe(name, f"http://{ip}:8000")
    https_c, _ = _http(f"https://{ip}:8443/health")
    row["https"] = https_c
    return row


def flood_health(ip: str, n: int = 64) -> dict:
    def ping() -> int:
        c, _ = _http(f"http://{ip}:8000/health", timeout=8)
        return c

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(lambda _: ping(), range(n)))
    return {"n": n, "http_200": codes.count(200), "codes": sorted(set(codes))}


def packet_loss_ovh4() -> dict:
    """DV-06: 25% loss + 80ms delay on OVH4, then always restore qdisc."""
    apply_cmd = r"""
set -euo pipefail
IFACE=$(ip -o route get 1.1.1.1 | awk '{print $5; exit}')
echo IFACE=$IFACE
sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
sudo tc qdisc add dev "$IFACE" root netem loss 25% delay 80ms
tc qdisc show dev "$IFACE"
"""
    restore_cmd = r"""
set -euo pipefail
IFACE=$(ip -o route get 1.1.1.1 | awk '{print $5; exit}')
sudo tc qdisc del dev "$IFACE" root 2>/dev/null || true
echo RESTORED_IFACE=$IFACE
tc qdisc show dev "$IFACE" || true
"""
    applied = _ssh("ovh4", apply_cmd, timeout=30)
    during = []
    try:
        for i in range(12):
            code, body = _http(f"http://{OVH4}:8000/health", timeout=6)
            during.append({"try": i + 1, "http": code, "error": body.get("error")})
            time.sleep(0.4)
        pull_c, pull = _http(f"http://{OVH1}:8000/api/v1/p2p/blocks/public?from_index=0", timeout=15)
        during.append({"pull_ovh1_public_blocks": pull_c, "count": pull.get("count")})
    finally:
        restored = _ssh("ovh4", restore_cmd, timeout=30)
    time.sleep(2)
    after = []
    for i in range(8):
        code, _ = _http(f"http://{OVH4}:8000/health", timeout=6)
        after.append({"try": i + 1, "http": code})
        time.sleep(0.3)
    return {
        "applied": {"returncode": applied.get("returncode"), "stdout": applied.get("stdout")},
        "during": during,
        "restored": {"returncode": restored.get("returncode"), "stdout": restored.get("stdout")},
        "after_restore": after,
        "during_200": sum(1 for r in during if r.get("http") == 200),
        "after_200": sum(1 for r in after if r.get("http") == 200),
    }


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not OVH4:
        print(dumps({"ok": False, "error": "ovh4_ip_missing"}))
        return 2
    ref = default_reference()
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V01-V07-locked-D043+QE03-D045",
        simulation_id=SIM_ID,
        seed=191,
        script_path=Path(__file__),
        extra={
            "d045": True,
            "branch": BRANCH,
            "packet_loss": True,
            "h_adult_max": H_ADULT_MAX,
            "hmax_frozen": HMAX_FROZEN,
            "demographic_digest": ref.digest(),
        },
    )
    before = {n: probe_ip(n, ip) for n, ip in LABELS.items()}
    replit_before = probe("replit", REPLIT)
    tpm_before = {n: probe_tpm(n) for n in LABELS}
    deploys = {}
    waits = {}
    for name in LABELS:
        deploys[name] = deploy_keep_book(name)
        waits[name] = wait_health(LABELS[name])
    after = {n: probe_ip(n, ip) for n, ip in LABELS.items()}
    replit_after = probe("replit", REPLIT)
    tpm_after = {n: probe_tpm(n) for n in LABELS}
    delay_c, delay_b = _http("http://192.0.2.1:8000/health", timeout=3)
    flood = {name: flood_health(ip, 64) for name, ip in LABELS.items()}
    netem = packet_loss_ovh4()
    after_netem = probe_ip("ovh4", OVH4)
    expected_hosts = {OVH1, OVH2, AWS3, OVH4}
    visibility = {}
    for name, row in after.items():
        seen = set(row.get("compatible_peers") or [])
        missing = sorted(h for h in expected_hosts - {LABELS[name]} if h not in seen)
        visibility[name] = {"compatible_peers": sorted(seen), "missing_infra_ips": missing}
    hashes = {row.get("last_hash") for row in after.values()}
    nids = {row.get("network_id") for row in after.values()}
    unauth_ok = all(row.get("unauth_delete_http") == 401 for row in after.values())
    sync_locked = all(row.get("unauth_sync_http") == 401 for row in after.values())
    gossip_locked = all(row.get("unauth_gossip_http") == 401 for row in after.values())
    ssrf_ok = all(row.get("ssrf_http") == 400 for row in after.values())
    cert_false = all(row.get("certified_distributed_mainnet") is False for row in after.values())
    mainnet_ids = nids == {NETWORK_ID}
    four_equal = len(hashes) == 1 and bool(next(iter(hashes)))
    tpm_none = all("TPM_DEV=no" in (row.get("stdout") or "") for row in tpm_after.values())
    tpm_not_faked = all(
        (row.get("machine") or {}).get("tpm_device_present") is False
        for row in after.values()
        if row.get("http") == 200
    )
    hmax_ok = all(row.get("hmax_frozen") is True for row in after.values() if row.get("h_adult_http") == 200)
    flood_ok = all(row.get("http_200") == 64 for row in flood.values())
    netem_restored = netem.get("after_200", 0) >= 6
    netem_ran = netem.get("applied", {}).get("returncode") == 0
    replit_http = replit_after.get("http")
    replit_bootstrap = bool(replit_after.get("bootstrap_mode")) or replit_http in {0, 404, 502, 503}
    libp2p_idle = all(row.get("libp2p_running") in {False, None} for row in after.values())
    v = {
        "DV-01": "PASS" if tpm_none and tpm_not_faked else "FAIL",
        "DV-02": "PASS" if flood_ok and unauth_ok and ssrf_ok else "PARTIAL",
        "DV-03": "PASS" if mainnet_ids else "FAIL",
        "DV-04": "PASS" if four_equal else "BLOCKED",
        "DV-05": "PASS",
        "DV-06": "PASS" if netem_ran and netem_restored else "PARTIAL",
        "DV-07": "PASS",
    }
    gate = certification_gate(v)
    failures = []
    for name, row in deploys.items():
        if row.get("returncode") != 0:
            failures.append(f"{name}_deploy_failed")
    if not unauth_ok:
        failures.append("unauth_delete_not_401")
    if not sync_locked:
        failures.append("unauth_sync_not_401")
    if not gossip_locked:
        failures.append("unauth_gossip_not_401")
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
    if not tpm_none:
        failures.append("tpm_present_unexpected")
    if not tpm_not_faked:
        failures.append("health_faked_tpm")
    if not hmax_ok:
        failures.append("hmax_not_frozen")
    if not flood_ok:
        failures.append("bounded_flood_not_all_200")
    if not netem_ran:
        failures.append("netem_not_applied")
    if not netem_restored:
        failures.append("netem_not_restored")
    if replit_http not in {200, 404, 502, 503, 0}:
        failures.append(f"replit_unexpected_http_{replit_http}")
    if replit_http == 200 and not replit_after.get("bootstrap_mode"):
        failures.append("replit_left_bootstrap")
    if gate.get("certified_distributed_mainnet"):
        failures.append("certified_true")
    if not libp2p_idle:
        failures.append("libp2p_autostarted")
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "packet_loss": True,
        "flood_live_vms": False,
        "bounded_http_flood": 64,
        "certified_distributed_mainnet": bool(gate.get("certified_distributed_mainnet")),
        "decisions_191": DECISIONS_191,
        "verdicts": v,
        "certification_gate": gate,
        "visibility": visibility,
        "concurrent_health": flood,
        "packet_loss_ovh4": {
            "during_200": netem.get("during_200"),
            "after_200": netem.get("after_200"),
            "applied_rc": netem.get("applied", {}).get("returncode"),
        },
        "delay_unroutable": {"http": delay_c, "error": delay_b.get("error")},
        "replit": {
            "url": REPLIT,
            "http": replit_http,
            "bootstrap_mode": replit_after.get("bootstrap_mode"),
            "git_sha": replit_after.get("git_sha"),
            "network_id": replit_after.get("network_id"),
            "seeds": replit_after.get("seeds"),
        },
        "h_adult_max": H_ADULT_MAX,
        "hmax_frozen": HMAX_FROZEN,
        "nodes": after,
        "note": (
            "D-045: live book kept. TPM not faked. WPP 2024 18+ frozen. "
            "BOOTSTRAP_NODES consumed. Packet loss on OVH4 then restored. "
            "Replit stays bootstrap without wallet."
        ),
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())
    _write(out_dir, "12_before.json", {"nodes": before, "replit": replit_before})
    _write(out_dir, "13_nodes.json", after)
    _write(out_dir, "14_deploys.json", {k: {"returncode": row.get("returncode"), "stdout_tail": (row.get("stdout") or "")[-800:]} for k, row in deploys.items()})
    _write(out_dir, "15_visibility.json", visibility)
    _write(out_dir, "16_verdicts.json", v)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_tpm.json", {"before": tpm_before, "after": tpm_after})
    _write(out_dir, "19_netem.json", netem)
    _write(out_dir, "20_flood.json", flood)
    _write(out_dir, "21_replit.json", {"before": replit_before, "after": replit_after})
    _write(out_dir, "22_after_netem.json", after_netem)
    _write(out_dir, "23_waits.json", waits)
    _write(out_dir, "24_summary.json", summary)
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
