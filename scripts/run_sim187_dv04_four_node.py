#!/usr/bin/env python3
"""Simulation 187 — DV-04 C four-node public replication after D-041.

Adopts no invented merge. OVH1 already holds the OVH2 public book
(operator D-041). This run: mesh, public TX, sync four nodes, restart
OVH1, compare last_hash / public_state_digest. Never invent SHA.
certified_distributed_mainnet stays false. DV-05 stays BLOCKED.
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
from artcb.devnet_validation import DECISIONS_186, DECISIONS_187, public_lock  # noqa: E402
from artcb.node_registry import NODES, public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e187_dv04_four_node"
OVH1 = NODES["ovh-node-1"].ssh_host or "152.228.144.34"
OVH2 = NODES["ovh-node-2"].ssh_host or "151.80.107.29"
AWS3 = NODES["aws-node-3"].ssh_host or "51.44.222.232"
OVH4 = NODES["ovh-node-4"].ssh_host or ""
CTX = ssl._create_unverified_context()
LABELS = {"ovh1": OVH1, "ovh2": OVH2, "aws3": AWS3, "ovh4": OVH4}


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
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "url": url}


def probe(name: str, ip: str) -> dict:
    http_c, health = _http(f"http://{ip}:8000/health")
    https_c, _ = _http(f"https://{ip}:8443/health")
    _, chain = _http(f"http://{ip}:8000/api/v1/chain/status")
    _, verify = _http(f"http://{ip}:8000/api/v1/chain/verify")
    _, p2p = _http(f"http://{ip}:8000/api/v1/p2p/status")
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
        "pqc": pqc.get("algorithm"),
        "pqc_available": pqc.get("available"),
        "hybrid_verify_mode": policy.get("hybrid_verify_mode"),
        "height": chain.get("height"),
        "last_hash": chain.get("last_hash"),
        "chain_valid": chain.get("chain_valid") or verify.get("valid"),
        "hybrid_signatures": verify.get("hybrid_signatures"),
        "public_state_digest": p2p.get("public_state_digest"),
        "capability_signed": bool((p2p.get("capability_card") or {}).get("signed")),
        "peer_count": p2p.get("peer_count"),
        "protocol_compatible_with_174": proto_ok,
        "protocol_reason": proto_reason,
        "reachable": http_c == 200 or https_c == 200,
        "bootstrap_mode": health.get("bootstrap_mode"),
        "public_blocks_local": p2p.get("public_blocks_local"),
    }


def register_pair(target_ip: str, source_ip: str, label: str) -> dict:
    code, body = _http(
        f"http://{target_ip}:8000/api/v1/p2p/register-public",
        "POST",
        {
            "node_public_url": f"http://{source_ip}:8000",
            "device_fingerprint": f"e2e187-{label}",
            "node_label": label,
            "network_id": NETWORK_ID,
        },
        timeout=30,
    )
    peer = body.get("peer") if isinstance(body.get("peer"), dict) else {}
    return {
        "http": code,
        "status": (body or {}).get("status"),
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


def restart_ovh1() -> dict:
    key = Path.home() / ".ssh" / "artcb_ovh_deploy"
    known = ROOT / "deploy" / "ovh_artcb_node_1.known_hosts"
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
        "ConnectTimeout=15",
        f"ubuntu@{OVH1}",
        "sudo systemctl restart artcb",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    health_wait = []
    for i in range(20):
        code, body = _http(f"http://{OVH1}:8000/health", timeout=5)
        health_wait.append({"try": i + 1, "http": code})
        if code == 200:
            break
        time.sleep(3)
    return {
        "ssh_returncode": proc.returncode,
        "ssh_stderr_len": len(proc.stderr or ""),
        "health_wait": health_wait,
        "health_ok": bool(health_wait and health_wait[-1]["http"] == 200),
    }


def verdicts(nodes: dict[str, dict], after_tx: dict, after_restart: dict) -> dict[str, str]:
    compatible = all(n.get("protocol_compatible_with_174") for n in nodes.values())
    reachable = all(n.get("reachable") for n in nodes.values())
    pqc_ok = all(n.get("pqc_available") for n in nodes.values())
    dv04 = "PASS" if four_equal(after_tx) and four_equal(after_restart) else "BLOCKED"
    return {
        "DV-01": "PENDING",
        "DV-02": "PARTIAL" if reachable else "FAIL",
        "DV-03": "PASS" if compatible else "FAIL",
        "DV-04": dv04,
        "PRE-DV-04": "PASS" if four_equal(after_tx) else "FAIL",
        "DV-05": "BLOCKED",
        "DV-06": "PARTIAL" if after_restart else "NOT_RUN",
        "DV-07": "PARTIAL" if pqc_ok else "FAIL",
        "compatible_node_count": str(sum(1 for n in nodes.values() if n.get("protocol_compatible_with_174"))),
    }


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
        economic_rules_version="D-025+V-provisional+D-032..D-041",
        simulation_id=SIM_ID,
        seed=187,
        script_path=Path(__file__),
        extra={"d040": True, "d041": True, "four_node_book": True},
    )
    nodes_before = {
        "ovh1": probe("ovh-node-1", OVH1),
        "ovh2": probe("ovh-node-2", OVH2),
        "aws3": probe("aws-node-3", AWS3),
        "ovh4": probe("ovh-node-4", OVH4),
    }
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
    before = tips()
    store_c, store_b = _http(
        f"http://{OVH2}:8000/api/v1/store",
        "POST",
        {"text": f"DV-04 C TX-003 four-node replication probe 187 {ts}", "visibility": "public"},
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
    v = verdicts(nodes_after, after_tx, after_restart)
    failures: list[str] = []
    for key, node in nodes_after.items():
        if not node.get("reachable"):
            failures.append(f"{key}_down")
        if not node.get("protocol_compatible_with_174"):
            failures.append(f"{key}_protocol_incompatible")
        if node.get("bootstrap_mode") is True:
            failures.append(f"{key}_bootstrap")
    if not four_equal(after_tx):
        failures.append("dv04_tips_diverge_after_tx")
    if not four_equal(after_restart):
        failures.append("dv04_tips_diverge_after_restart")
    dv04_run = {
        "dropped_incompatible_peers": dropped,
        "registrations": registrations,
        "before": before,
        "store_http": store_c,
        "store_block_index": store_b.get("block_index") if isinstance(store_b, dict) else None,
        "sync_http": {k: val[0] for k, val in syncs.items()},
        "sync_ok_peers": {
            k: all(bool(row.get("ok")) for row in (val[1].get("results") or []) if isinstance(row, dict))
            for k, val in syncs.items()
        },
        "after_tx": after_tx,
        "restart_ovh1": {k: restart[k] for k in ("ssh_returncode", "health_ok") if k in restart},
        "restart_health_wait": restart.get("health_wait"),
        "after_restart": after_restart,
        "four_equal_after_tx": four_equal(after_tx),
        "four_equal_after_restart": four_equal(after_restart),
        "genesis_hash_expected": GENESIS_HASH,
    }
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "certified_distributed_mainnet": False,
        "decisions_186": DECISIONS_186,
        "decisions_187": DECISIONS_187,
        "verdicts": v,
        "consensus_extracted": public_spec(),
        "nodes_before": nodes_before,
        "nodes": nodes_after,
        "note": (
            "D-041: OVH1 adopted the existing OVH2 public book. "
            "DV-04 C PASS only if four last_hash+digest match after TX and restart. "
            "Not certified mainnet. DV-05 remains BLOCKED."
        ),
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_lock.json", public_lock())
    _write(out_dir, "12_nodes_before.json", nodes_before)
    _write(out_dir, "13_nodes.json", nodes_after)
    _write(out_dir, "14_dv04.json", dv04_run)
    _write(out_dir, "15_consensus.json", public_spec())
    _write(out_dir, "16_verdicts.json", v)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    for dv, status in v.items():
        if not dv.startswith("DV") and dv != "PRE-DV-04":
            continue
        dest = val_dir / dv / "RESULT.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(dumps({"id": dv, "status": status, "at": ts, "sim": SIM_ID}), encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
