#!/usr/bin/env python3
"""Simulation 204 — 3-node origin/main keep-book after OVH2 rescue recovery.

Does not wipe blocks.jsonl. Does not flip certified_distributed_mainnet.
OVH4 stays blocked without KEY_API_ARTCB_DOPPLER_4. Isolated tempdir TPS
is not distributed mainnet TPS. Historical 90 TPS remains lab 2026-08-03.
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

SIM_ID = "e2e204_three_node_main_homogenize"
CTX = ssl._create_unverified_context()
LABELS = {
    "ovh1": NODES["ovh-node-1"].ssh_host or "152.228.144.34",
    "ovh2": NODES["ovh-node-2"].ssh_host or "151.80.107.29",
    "aws3": NODES["aws-node-3"].ssh_host or "51.44.222.232",
    "ovh4": NODES["ovh-node-4"].ssh_host or "91.134.45.8",
}
SSH = {
    "ovh1": Path.home() / ".ssh" / "artcb_ovh_deploy",
    "ovh2": Path.home() / ".ssh" / "artcb_ovh_node_2",
    "aws3": Path.home() / ".ssh" / "artcb_aws_node_3",
    "ovh4": Path.home() / ".ssh" / "artcb_ovh_node_4",
}
HTTPS = {
    "ovh1": "https://artcb.me/health",
    "ovh2": "https://n2.artcb.me/health",
    "aws3": "https://n3.artcb.me/health",
    "ovh4": "https://n4.artcb.me/health",
}


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _http(url: str, timeout: int = 25) -> tuple[int, dict, float]:
    t0 = time.perf_counter()
    req = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout, context=CTX if url.startswith("https://") else None) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return resp.status, body if isinstance(body, dict) else {"raw": body}, round((time.perf_counter() - t0) * 1000, 1)
    except HTTPError as exc:
        return exc.code, {"detail": exc.read().decode("utf-8", errors="replace")[:200]}, round((time.perf_counter() - t0) * 1000, 1)
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "url": url}, round((time.perf_counter() - t0) * 1000, 1)


def _ssh_ready(name: str) -> bool:
    key = SSH[name]
    return key.is_file() and key.stat().st_size > 80


def collect_node(name: str, ip: str) -> dict:
    code, health, rtt = _http(f"http://{ip}:8000/health")
    _cc, chain, crtt = _http(f"http://{ip}:8000/api/v1/chain/status")
    _mc, metrics, mrtt = _http(f"http://{ip}:8000/api/v1/metrics")
    net = metrics.get("network") if isinstance(metrics.get("network"), dict) else {}
    hcode, https_body, httt = _http(HTTPS[name])
    return {
        "name": name,
        "ip": ip,
        "ssh_key": _ssh_ready(name),
        "health": {
            "http": code,
            "rtt_ms": rtt,
            "git_sha": health.get("git_sha"),
            "git_branch": health.get("git_branch"),
            "certified_distributed_mainnet": health.get("certified_distributed_mainnet"),
            "certification_reason": health.get("certification_reason"),
        },
        "chain": {
            "http": _cc,
            "rtt_ms": crtt,
            "height": chain.get("height"),
            "last_hash": chain.get("last_hash"),
            "chain_valid": chain.get("chain_valid"),
        },
        "metrics": {
            "http": _mc,
            "rtt_ms": mrtt,
            "measured_bandwidth_mbps": net.get("measured_bandwidth_mbps"),
            "estimated_bandwidth_mbps": net.get("estimated_bandwidth_mbps"),
            "fallback_bandwidth_mbps": net.get("fallback_bandwidth_mbps"),
            "bandwidth_source": net.get("bandwidth_source"),
            "metrics_timing": metrics.get("metrics_timing"),
        },
        "https_domain": {"url": HTTPS[name], "http": hcode, "rtt_ms": httt, "git_sha": https_body.get("git_sha")},
    }


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    local_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    origin_main = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
    _write(out_dir, "10_registry.json", public_registry())
    _write(
        out_dir,
        "11_manifest.json",
        collect(
            protocol_version=PROTOCOL_VERSION,
            economic_rules_version="D-025+V01-V07-locked-D054",
            simulation_id=SIM_ID,
            seed=204,
            script_path=Path(__file__),
            extra={
                "keep_book": True,
                "operator_certification_go": OPERATOR_MAINNET_CERTIFICATION_GO,
                "ssh_keys_present": {n: _ssh_ready(n) for n in LABELS},
                "local_sha": local_sha,
                "origin_main": origin_main,
            },
        ),
    )
    live = {n: collect_node(n, ip) for n, ip in LABELS.items()}
    _write(out_dir, "16_live.json", live)
    shas = {(row.get("health") or {}).get("git_sha") for row in live.values()}
    hashes = {(row.get("chain") or {}).get("last_hash") for row in live.values()}
    certs = {(row.get("health") or {}).get("certified_distributed_mainnet") for row in live.values()}
    reachable = [n for n, row in live.items() if (row.get("health") or {}).get("http") == 200]
    same_as_main = [n for n, row in live.items() if (row.get("health") or {}).get("git_sha") == origin_main]
    gate = certification_gate()
    summary = {
        "ok": bool(reachable)
        and OPERATOR_MAINNET_CERTIFICATION_GO is False
        and False not in {c is False or c is None for c in certs if c is not None},
        "origin_main": origin_main,
        "local_sha": local_sha,
        "reachable": reachable,
        "same_sha_as_origin_main": same_as_main,
        "live_shas": sorted(x for x in shas if x),
        "last_hashes": sorted(x for x in hashes if x),
        "homogeneous_four": len({x for x in shas if x}) == 1 and origin_main in shas and len(same_as_main) == 4,
        "cas_b_official_distributed_bench": False,
        "certified": False,
        "gate_certified": gate.get("certified_distributed_mainnet"),
        "operator_certification_go": OPERATOR_MAINNET_CERTIFICATION_GO,
        "historical_90_tps_is_lab_not_mainnet": True,
        "isolated_tempdir_tps_is_not_distributed_mainnet": True,
        "ovh4_blocked_without_doppler_4": True,
        "secrets_printed": False,
        "keep_book": True,
        "network_id": NETWORK_ID,
        "inject_script": "scripts/inject_ovh2_ssh_via_rescue.py",
    }
    _write(out_dir, "17_summary.json", summary)
    print(dumps(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
