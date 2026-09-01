#!/usr/bin/env python3
"""Simulation 189 — D-043 mainnet identity + new public genesis.

Never invent SHA. Does not flip certified_distributed_mainnet.
Does not run install.sh or scripts/init_genesis.py (those wipe chain.key).

Sequence (required): STOP all four → git checkout branch (no install) →
backup+empty blocks.jsonl and incoming_public.jsonl → write release.env →
START all four → mesh → one public TX on OVH2 → sync → restart OVH1 → compare.
Emptying one node while another still holds the 174 book would re-import
index-0 because GENESIS_PREV_HASH is 64 zeros.
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

from artcb.consensus_spec import public_spec  # noqa: E402
from artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PROTOCOL_VERSION, accept_peer_protocol  # noqa: E402
from artcb.devnet_validation import DECISIONS_189, certification_gate, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e189_mainnet_genesis"
BRANCH = "cursor/mainnet-genesis-d043-16d8"
OVH1 = NODES["ovh-node-1"].ssh_host or "152.228.144.34"
OVH2 = NODES["ovh-node-2"].ssh_host or "151.80.107.29"
AWS3 = NODES["aws-node-3"].ssh_host or "51.44.222.232"
OVH4 = NODES["ovh-node-4"].ssh_host or ""
CTX = ssl._create_unverified_context()
LABELS = {"ovh1": OVH1, "ovh2": OVH2, "aws3": AWS3, "ovh4": OVH4}
SSH = {
    "ovh1": (
        Path.home() / ".ssh" / "artcb_ovh_deploy",
        ROOT / "deploy" / "ovh_artcb_node_1.known_hosts",
        OVH1,
    ),
    "ovh2": (
        Path.home() / ".ssh" / "artcb_ovh_node_2",
        ROOT / "deploy" / "ovh_artcb_node_2.known_hosts",
        OVH2,
    ),
    "aws3": (
        Path.home() / ".ssh" / "artcb_aws_node_3",
        ROOT / "deploy" / "aws_artcb_node_3.known_hosts",
        AWS3,
    ),
    "ovh4": (
        Path.home() / ".ssh" / "artcb_ovh_node_4",
        ROOT / "deploy" / "ovh_artcb_node_4.known_hosts",
        OVH4,
    ),
}


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _http(url: str, method: str = "GET", body: dict | None = None, timeout: int = 20) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
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
        "ssh",
        "-i",
        str(key),
        "-o",
        "UserKnownHostsFile=" + str(known),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        f"ubuntu@{ip}",
        remote,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "name": name,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-1500:],
    }


def wait_health(ip: str, *, want: int = 200, tries: int = 25) -> list[dict]:
    rows = []
    for i in range(tries):
        code, _ = _http(f"http://{ip}:8000/health", timeout=5)
        rows.append({"try": i + 1, "http": code})
        if code == want:
            break
        time.sleep(3)
    return rows


def probe(name: str, ip: str) -> dict:
    http_c, health = _http(f"http://{ip}:8000/health")
    https_c, _ = _http(f"https://{ip}:8443/health")
    _, chain = _http(f"http://{ip}:8000/api/v1/chain/status")
    _, verify = _http(f"http://{ip}:8000/api/v1/chain/verify")
    _, p2p = _http(f"http://{ip}:8000/api/v1/p2p/status")
    faucet_c, faucet = _http(
        f"http://{ip}:8000/api/v1/devnet/faucet",
        "POST",
        {"address": "artcb1faucetprobe000000000000001"},
        timeout=15,
    )
    proto_ok, proto_reason = accept_peer_protocol(
        advertised_network_id=health.get("network_id") or p2p.get("network_id"),
        advertised_protocol_version=health.get("protocol_version") or p2p.get("protocol_version"),
        advertised_genesis_hash=health.get("genesis_hash") or p2p.get("genesis_hash"),
    )
    pqc = health.get("pqc") if isinstance(health.get("pqc"), dict) else {}
    policy = pqc.get("policy") if isinstance(pqc.get("policy"), dict) else {}
    return {
        "classification": "PROBE LIVE",
        "name": name,
        "ip": ip,
        "http": http_c,
        "https": https_c,
        "git_sha": health.get("git_sha"),
        "git_branch": health.get("git_branch"),
        "network_id": health.get("network_id") or p2p.get("network_id"),
        "protocol_version": health.get("protocol_version") or p2p.get("protocol_version"),
        "genesis_hash": health.get("genesis_hash") or p2p.get("genesis_hash"),
        "certified_distributed_mainnet": health.get("certified_distributed_mainnet"),
        "pqc": pqc.get("algorithm"),
        "pqc_available": pqc.get("available"),
        "hybrid_verify_mode": policy.get("hybrid_verify_mode"),
        "ed25519_only_until": policy.get("ed25519_only_until"),
        "height": chain.get("height"),
        "last_hash": chain.get("last_hash"),
        "chain_valid": chain.get("chain_valid") or verify.get("valid"),
        "public_state_digest": p2p.get("public_state_digest"),
        "capability_signed": bool((p2p.get("capability_card") or {}).get("signed")),
        "peer_count": p2p.get("peer_count"),
        "protocol_compatible": proto_ok,
        "protocol_reason": proto_reason,
        "reachable": http_c == 200 or https_c == 200,
        "bootstrap_mode": health.get("bootstrap_mode"),
        "public_blocks_local": p2p.get("public_blocks_local"),
        "faucet_http": faucet_c,
        "faucet_detail": (faucet or {}).get("detail"),
    }


def register_pair(target_ip: str, source_ip: str, label: str) -> dict:
    code, body = _http(
        f"http://{target_ip}:8000/api/v1/p2p/register-public",
        "POST",
        {
            "node_public_url": f"http://{source_ip}:8000",
            "device_fingerprint": f"e2e189-{label}",
            "node_label": label,
            "network_id": NETWORK_ID,
        },
        timeout=30,
    )
    peer = body.get("peer") if isinstance(body.get("peer"), dict) else {}
    return {
        "http": code,
        "peer_id": (body or {}).get("peer_id") or peer.get("peer_id"),
        "protocol_compatible": peer.get("protocol_compatible"),
    }


def drop_incompatible_peers(ip: str) -> list[dict]:
    dropped: list[dict] = []
    _, body = _http(f"http://{ip}:8000/api/v1/p2p/peers")
    for peer in body.get("peers") or []:
        if peer.get("protocol_compatible"):
            continue
        pid = peer.get("peer_id")
        if not pid:
            continue
        code, _ = _http(f"http://{ip}:8000/api/v1/p2p/peers/{pid}", "DELETE")
        dropped.append({"peer_id": pid, "host": peer.get("host"), "deleted_http": code})
    return dropped


def tips() -> dict[str, dict]:
    out = {}
    for name, ip in LABELS.items():
        _, chain = _http(f"http://{ip}:8000/api/v1/chain/status")
        _, p2p = _http(f"http://{ip}:8000/api/v1/p2p/status")
        out[name] = {
            "height": chain.get("height"),
            "last_hash": chain.get("last_hash"),
            "public_state_digest": p2p.get("public_state_digest"),
        }
    return out


def four_equal(snapshot: dict[str, dict]) -> bool:
    hashes = {row.get("last_hash") for row in snapshot.values()}
    digests = {row.get("public_state_digest") for row in snapshot.values()}
    h = next(iter(hashes), None)
    d = next(iter(digests), None)
    if not h or str(h).startswith("0" * 16):
        return False
    if not d:
        return False
    return len(hashes) == 1 and len(digests) == 1 and len(snapshot) == 4


def checkout_and_empty(name: str) -> dict:
    """Stop, fetch branch without install.sh, empty test book. Do not start.

    Forbidden: install.sh, scripts/init_genesis.py. All four must be empty
    before any node starts, or an empty tip can import the 174 index-0 block
    (prev_hash is 64 zeros).
    """
    remote = r"""
set -euo pipefail
cd /home/ubuntu/artcb
sudo systemctl stop artcb || true
git fetch origin cursor/mainnet-genesis-d043-16d8
if git show-ref --verify --quiet refs/remotes/origin/cursor/mainnet-genesis-d043-16d8; then
  git checkout -B cursor/mainnet-genesis-d043-16d8 origin/cursor/mainnet-genesis-d043-16d8
  git reset --hard origin/cursor/mainnet-genesis-d043-16d8
else
  git checkout -B cursor/mainnet-genesis-d043-16d8 FETCH_HEAD
  git reset --hard FETCH_HEAD
fi
SHA=$(git rev-parse HEAD)
BR=$(git rev-parse --abbrev-ref HEAD)
printf 'ARTCB_GIT_SHA=%s\nARTCB_GIT_BRANCH=%s\n' "$SHA" "$BR" > /tmp/artcb_release.env
sudo mkdir -p /etc/artcb
sudo cp /tmp/artcb_release.env /etc/artcb/release.env
sudo chmod 644 /etc/artcb/release.env
CHAIN=data/chain/blocks.jsonl
ARCH=data/p2p/incoming_public.jsonl
mkdir -p data/chain data/p2p
if [ -f "$CHAIN" ]; then
  cp -a "$CHAIN" "data/chain/blocks.jsonl.bak-d043-testbook"
fi
if [ -f "$ARCH" ]; then
  cp -a "$ARCH" "data/p2p/incoming_public.jsonl.bak-d043-testbook"
fi
: > "$CHAIN"
: > "$ARCH"
echo "init_genesis.py not executed"
echo "install.sh not executed"
echo "DEPLOYED_SHA=$SHA"
echo "DEPLOYED_BRANCH=$BR"
wc -c "$CHAIN" "$ARCH" 2>/dev/null || true
test -f data/chain/chain.key && echo "chain_key=present" || echo "chain_key=MISSING"
"""
    return _ssh(name, remote, timeout=240)


def start_node(name: str) -> dict:
    return _ssh(name, "sudo systemctl start artcb", timeout=60)


def restart_ovh1() -> dict:
    result = _ssh("ovh1", "sudo systemctl restart artcb", timeout=60)
    health_wait = wait_health(OVH1, want=200, tries=20)
    return {
        "ssh_returncode": result["returncode"],
        "ssh_stderr": result["stderr"],
        "health_wait": health_wait,
        "health_ok": bool(health_wait and health_wait[-1]["http"] == 200),
    }


def probe_tpm(name: str) -> dict:
    remote = (
        "echo TPM_DEV=$(test -e /dev/tpm0 && echo yes || echo no); "
        "echo TPMRM=$(test -e /dev/tpmrm0 && echo yes || echo no); "
        "echo TPM_SYS=$(test -r /sys/class/tpm/tpm0/tpm_version_major && "
        "cat /sys/class/tpm/tpm0/tpm_version_major || echo none); "
        "command -v tpm2_getcap >/dev/null && echo TPM2_TOOLS=yes || echo TPM2_TOOLS=no"
    )
    return _ssh(name, remote, timeout=30)


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    val_dir = ROOT / "validation"
    if not OVH4 or OVH4 in {OVH1, OVH2}:
        print(dumps({"ok": False, "error": "ovh4_ip_missing_or_forbidden"}))
        return 2
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V01-V07-locked-D043",
        simulation_id=SIM_ID,
        seed=189,
        script_path=Path(__file__),
        extra={"d043": True, "branch": BRANCH},
    )
    nodes_before = {
        "ovh1": probe("ovh-node-1", OVH1),
        "ovh2": probe("ovh-node-2", OVH2),
        "aws3": probe("aws-node-3", AWS3),
        "ovh4": probe("ovh-node-4", OVH4),
    }
    _write(out_dir, "12_nodes_before.json", nodes_before)

    STOP_ALL = {name: _ssh(name, "sudo systemctl stop artcb", timeout=60) for name in LABELS}
    deploys = {name: checkout_and_empty(name) for name in LABELS}
    starts = {name: start_node(name) for name in LABELS}
    health_waits = {name: wait_health(ip, want=200, tries=25) for name, ip in LABELS.items()}
    tpm = {name: probe_tpm(name) for name in LABELS}

    dropped = {name: drop_incompatible_peers(ip) for name, ip in LABELS.items()}
    mesh = (
        ("ovh1_ovh2", OVH1, OVH2),
        ("ovh1_aws3", OVH1, AWS3),
        ("ovh1_ovh4", OVH1, OVH4),
        ("ovh2_ovh1", OVH2, OVH1),
        ("ovh2_aws3", OVH2, AWS3),
        ("ovh2_ovh4", OVH2, OVH4),
        ("aws3_ovh1", AWS3, OVH1),
        ("aws3_ovh2", AWS3, OVH2),
        ("aws3_ovh4", AWS3, OVH4),
        ("ovh4_ovh1", OVH4, OVH1),
        ("ovh4_ovh2", OVH4, OVH2),
        ("ovh4_aws3", OVH4, AWS3),
    )
    registrations = {name: register_pair(target, source, name) for name, target, source in mesh}
    before_tx = tips()
    store_c, store_b = _http(
        f"http://{OVH2}:8000/api/v1/store",
        "POST",
        {"text": f"D-043 artcb-mainnet-1 genesis public TX 189 {ts}", "visibility": "public"},
        timeout=60,
    )
    syncs = {
        name: _http(f"http://{ip}:8000/api/v1/p2p/sync", "POST", timeout=90)
        for name, ip in (("ovh1", OVH1), ("aws3", AWS3), ("ovh4", OVH4), ("ovh2", OVH2))
    }
    after_tx = tips()
    restart = restart_ovh1()
    after_restart = tips()
    nodes_after = {
        "ovh1": probe("ovh-node-1", OVH1),
        "ovh2": probe("ovh-node-2", OVH2),
        "aws3": probe("aws-node-3", AWS3),
        "ovh4": probe("ovh-node-4", OVH4),
    }

    identity_ok = all(n.get("capability_signed") for n in nodes_after.values())
    tpm_present = any("TPM_DEV=yes" in (row.get("stdout") or "") for row in tpm.values())
    dv01 = "PASS" if identity_ok else "PENDING"
    protocol_ok = all(n.get("protocol_compatible") for n in nodes_after.values())
    mainnet_ids = all(
        n.get("network_id") == NETWORK_ID
        and n.get("protocol_version") == PROTOCOL_VERSION
        and n.get("genesis_hash") == GENESIS_HASH
        for n in nodes_after.values()
    )
    faucet_off = all(n.get("faucet_http") == 403 for n in nodes_after.values())
    certified_false = all(n.get("certified_distributed_mainnet") is False for n in nodes_after.values())
    hybrid_and = all(n.get("hybrid_verify_mode") == "AND" for n in nodes_after.values())
    window_open = all(
        str(n.get("ed25519_only_until") or "").startswith("2026-12-31") for n in nodes_after.values()
    )
    genesis_replicated = four_equal(after_tx) and four_equal(after_restart)
    reachable = all(n.get("reachable") for n in nodes_after.values())

    v = {
        "DV-01": dv01,
        "DV-02": "PARTIAL" if reachable else "FAIL",
        "DV-03": "PASS" if protocol_ok and mainnet_ids else "FAIL",
        "DV-04": "PASS" if genesis_replicated else "BLOCKED",
        "DV-05": "PASS",
        "DV-06": "PARTIAL" if restart.get("health_ok") else "FAIL",
        "DV-07": "PASS" if hybrid_and and window_open else "PARTIAL",
    }
    gate = certification_gate(v)
    failures: list[str] = []
    for key, node in nodes_after.items():
        if not node.get("reachable"):
            failures.append(f"{key}_down")
        if not node.get("protocol_compatible"):
            failures.append(f"{key}_protocol_incompatible")
        if node.get("network_id") != NETWORK_ID:
            failures.append(f"{key}_not_mainnet_id")
        if node.get("bootstrap_mode") is True:
            failures.append(f"{key}_bootstrap")
        if node.get("faucet_http") != 403:
            failures.append(f"{key}_faucet_not_403")
        if node.get("certified_distributed_mainnet") is not False:
            failures.append(f"{key}_invented_certified_flag")
    for key, row in deploys.items():
        if row.get("returncode") not in {0}:
            failures.append(f"{key}_deploy_failed")
        stdout = row.get("stdout") or ""
        if "chain_key=MISSING" in stdout:
            failures.append(f"{key}_chain_key_missing")
        if "init_genesis.py executed" in stdout:
            failures.append(f"{key}_init_genesis_ran")
    for key, row in starts.items():
        if row.get("returncode") not in {0}:
            failures.append(f"{key}_start_failed")
    if store_c != 200:
        failures.append("genesis_tx_failed")
    if not four_equal(after_tx):
        failures.append("tips_diverge_after_genesis_tx")
    if not four_equal(after_restart):
        failures.append("tips_diverge_after_restart")
    if gate.get("certified_distributed_mainnet"):
        failures.append("certified_flag_true_while_dv02_open")

    ops = {
        "STOP_ALL": {k: {"returncode": row.get("returncode")} for k, row in STOP_ALL.items()},
        "starts": {
            k: {
                "returncode": row.get("returncode"),
                "stderr_tail": (row.get("stderr") or "")[-200:],
            }
            for k, row in starts.items()
        },
        "deploys": {
            k: {
                "returncode": v.get("returncode"),
                "stdout_tail": (v.get("stdout") or "")[-800:],
                "stderr_tail": (v.get("stderr") or "")[-400:],
            }
            for k, v in deploys.items()
        },
        "health_waits": health_waits,
        "tpm": {k: {"returncode": v.get("returncode"), "stdout": v.get("stdout")} for k, v in tpm.items()},
        "tpm_present_any": tpm_present,
        "dropped_incompatible_peers": dropped,
        "registrations": registrations,
        "before_tx": before_tx,
        "store_http": store_c,
        "store_block_index": store_b.get("block_index") if isinstance(store_b, dict) else None,
        "store_hash": store_b.get("hash") if isinstance(store_b, dict) else None,
        "sync_http": {k: val[0] for k, val in syncs.items()},
        "after_tx": after_tx,
        "restart_ovh1": {k: restart[k] for k in ("ssh_returncode", "health_ok") if k in restart},
        "restart_health_wait": restart.get("health_wait"),
        "after_restart": after_restart,
        "four_equal_after_tx": four_equal(after_tx),
        "four_equal_after_restart": four_equal(after_restart),
        "faucet_off": faucet_off,
        "certified_false": certified_false,
        "genesis_hash_declared": GENESIS_HASH,
        "network_id": NETWORK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "install_sh": "not_run",
        "init_genesis.py": "not_run",
    }
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "certified_distributed_mainnet": bool(gate.get("certified_distributed_mainnet")),
        "economic_v_locked": True,
        "decisions_189": DECISIONS_189,
        "verdicts": v,
        "certification_gate": gate,
        "consensus_extracted": public_spec(),
        "nodes_before": nodes_before,
        "nodes": nodes_after,
        "note": (
            "D-043: V-01…V-07 locked at sim-167 code. New identity artcb-mainnet-1. "
            "174 test book backed up then emptied on all four while STOPPED. "
            "One public genesis TX. certified_distributed_mainnet stays false "
            "while DV-02 C flood/chaos is not done. Not a rename of 174 probes."
        ),
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())
    _write(out_dir, "13_nodes.json", nodes_after)
    _write(out_dir, "14_ops.json", ops)
    _write(out_dir, "15_consensus.json", public_spec())
    _write(out_dir, "16_verdicts.json", v)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    _write(out_dir, "19_gate.json", gate)
    for dv, status in v.items():
        dest = val_dir / dv / "RESULT.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(dumps({"id": dv, "status": status, "at": ts, "sim": SIM_ID}), encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
