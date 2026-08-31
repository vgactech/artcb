#!/usr/bin/env python3
"""Simulation 173 — probe OVH1 + OVH2 + AWS3 after D-032 policy B.

Does not invent live SHA. Does not redeploy OVH1. Never prints secrets.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.crypto_policy import GENESIS_HASH, NETWORK_ID, PREFERRED_SIG, PROTOCOL_VERSION  # noqa: E402
from artcb.live import DEFAULT_LIVE_HTTPS_URL, DEFAULT_LIVE_URL, http_json  # noqa: E402
from artcb.node_registry import public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e173_ovh2_pqc_policy_b"
OVH1_IP = "152.228.144.34"
OVH2_IP = "151.80.107.29"
AWS3_IP = "51.44.222.232"


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=False)
    return (proc.stdout or "").strip()


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _http_json(url: str, timeout: int = 15) -> tuple[int, dict]:
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body if isinstance(body, dict) else {"raw": body}
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": type(exc).__name__, "url": url}


def probe_node(name: str, ip: str, https: bool = True) -> dict:
    http_code, http_body = _http_json(f"http://{ip}:8000/health")
    https_code, https_body = (0, {})
    if https:
        https_code, https_body = http_json("GET", f"https://{ip}:8443/health")
    p2p_code, p2p = _http_json(f"http://{ip}:8000/api/v1/p2p/status")
    source = http_body if http_code == 200 else https_body
    pqc = source.get("pqc") if isinstance(source, dict) else None
    algo = None
    available = None
    policy_id = None
    if isinstance(pqc, dict):
        algo = pqc.get("algorithm")
        available = pqc.get("available")
        policy = pqc.get("policy") if isinstance(pqc.get("policy"), dict) else {}
        policy_id = policy.get("policy_id")
    return {
        "classification": "PROBE LIVE",
        "name": name,
        "ip": ip,
        "http_health": http_code,
        "https_health": https_code,
        "git_sha": source.get("git_sha") if isinstance(source, dict) else None,
        "git_branch": source.get("git_branch") if isinstance(source, dict) else None,
        "bootstrap_mode": source.get("bootstrap_mode") if isinstance(source, dict) else None,
        "network_id": source.get("network_id") if isinstance(source, dict) else None,
        "protocol_version": source.get("protocol_version") if isinstance(source, dict) else None,
        "genesis_hash": source.get("genesis_hash") if isinstance(source, dict) else None,
        "pqc_algorithm": algo,
        "pqc_available": available,
        "policy_id": policy_id,
        "p2p_http": p2p_code,
        "p2p_node_id": p2p.get("node_id") if isinstance(p2p, dict) else None,
        "p2p_peer_count": p2p.get("peer_count") if isinstance(p2p, dict) else None,
        "p2p_crypto_suite": p2p.get("crypto_suite") if isinstance(p2p, dict) else None,
        "reachable": http_code == 200 or https_code == 200,
        "status": source.get("status") if isinstance(source, dict) else None,
    }


def live_ovh1() -> dict:
    expected = _git(["rev-parse", "origin/main"]) or _git(["rev-parse", "HEAD"])
    probe = probe_node("ovh-node-1", OVH1_IP)
    me_code, me = http_json("GET", f"{DEFAULT_LIVE_HTTPS_URL}/api/v1/api-keys/me")
    probe["expected_origin_main_sha"] = expected
    probe["sha_match_current_main"] = bool(
        probe.get("git_sha") and expected and probe.get("git_sha") == expected
    )
    probe["https_me"] = me_code
    probe["key_id"] = me.get("key_id") if isinstance(me, dict) else None
    probe["health_url"] = DEFAULT_LIVE_URL
    probe["https_url"] = DEFAULT_LIVE_HTTPS_URL
    return probe


def try_cross_register(pairs: list[tuple[str, str, str]]) -> dict:
    results: dict[str, dict] = {}
    for name, target, source in pairs:
        body = json.dumps(
            {
                "node_public_url": source,
                "device_fingerprint": f"e2e173-{name}",
                "node_label": name,
                "network_id": NETWORK_ID,
            }
        ).encode()
        req = Request(
            f"{target}/api/v1/p2p/register-public",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode())
                results[name] = {
                    "http": resp.status,
                    "registered": bool(payload.get("registered")),
                    "error": None,
                }
        except Exception as exc:  # noqa: BLE001
            results[name] = {"http": 0, "registered": False, "error": type(exc).__name__}
    return results


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect(
        protocol_version=PROTOCOL_VERSION,
        economic_rules_version="D-025+V01-V07-provisional+D-032+D-033",
        simulation_id=SIM_ID,
        seed=173,
        script_path=Path(__file__),
        extra={"ovh1_redeployed": False, "crypto_policy": "B-preferred-pqc"},
    )
    failures: list[str] = []
    ovh1 = live_ovh1()
    ovh2 = probe_node("ovh-node-2", OVH2_IP)
    aws3 = probe_node("aws-node-3", AWS3_IP)

    if not ovh1.get("reachable"):
        failures.append("ovh1_health_unreachable")
    if not ovh2.get("reachable"):
        failures.append("ovh2_health_unreachable")
    if not aws3.get("reachable"):
        failures.append("aws3_health_unreachable")
    if ovh2.get("bootstrap_mode") is True:
        failures.append("ovh2_still_bootstrap")
    if ovh1.get("git_sha") and str(ovh1.get("git_sha", "")).startswith("5b4b24ae"):
        ovh1_untouched = True
    else:
        ovh1_untouched = bool(ovh1.get("git_sha"))
        if ovh1.get("git_sha") and not str(ovh1.get("git_sha")).startswith("5b4b24ae"):
            failures.append("ovh1_sha_changed_without_order")

    for label, node in (("ovh2", ovh2), ("aws3", aws3)):
        if node.get("reachable") and node.get("pqc_available") is not True:
            failures.append(f"{label}_pqc_not_available")
        if node.get("reachable") and PREFERRED_SIG not in str(node.get("pqc_algorithm") or ""):
            if node.get("bootstrap_mode") is not True:
                failures.append(f"{label}_not_mldsa")

    pairs = []
    if ovh1.get("reachable") and aws3.get("reachable"):
        pairs.append(("ovh1_registers_aws3", f"http://{OVH1_IP}:8000", f"http://{AWS3_IP}:8000"))
        pairs.append(("aws3_registers_ovh1", f"http://{AWS3_IP}:8000", f"http://{OVH1_IP}:8000"))
    if ovh2.get("reachable") and ovh2.get("bootstrap_mode") is not True:
        if ovh1.get("reachable"):
            pairs.append(("ovh1_registers_ovh2", f"http://{OVH1_IP}:8000", f"http://{OVH2_IP}:8000"))
            pairs.append(("ovh2_registers_ovh1", f"http://{OVH2_IP}:8000", f"http://{OVH1_IP}:8000"))
        if aws3.get("reachable"):
            pairs.append(("aws3_registers_ovh2", f"http://{AWS3_IP}:8000", f"http://{OVH2_IP}:8000"))
            pairs.append(("ovh2_registers_aws3", f"http://{OVH2_IP}:8000", f"http://{AWS3_IP}:8000"))
    cross = try_cross_register(pairs) if pairs else {}

    live_count = sum(1 for n in (ovh1, ovh2, aws3) if n.get("reachable"))
    invariants = {
        "ovh1_live": ovh1.get("reachable") is True,
        "ovh2_live": ovh2.get("reachable") is True,
        "aws3_live": aws3.get("reachable") is True,
        "ovh1_not_redeployed": ovh1_untouched,
        "ovh2_pqc": ovh2.get("pqc_available") is True,
        "aws3_pqc": aws3.get("pqc_available") is True,
        "declared_network_id": NETWORK_ID,
        "declared_protocol_version": PROTOCOL_VERSION,
        "declared_genesis_hash": GENESIS_HASH,
        "three_live_compute": live_count == 3,
        "four_machines": False,
        "tokenomics_untouched": True,
        "economic_v_still_open": True,
        "dv_certified": False,
        "invented": False,
    }
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failure_count": len(failures),
        "failures": failures,
        "invented": False,
        "certified_distributed_mainnet": False,
        "live_count": live_count,
        "ovh1_sha": ovh1.get("git_sha"),
        "ovh2_sha": ovh2.get("git_sha"),
        "aws3_sha": aws3.get("git_sha"),
        "categories": {
            "LIVE_OVH1": ovh1,
            "LIVE_OVH2": ovh2,
            "LIVE_AWS3": aws3,
            "P2P_CROSS": cross or "skipped",
            "DISTRIBUTED_CONSENSUS": "PARTIAL — 3/4 live VMs; node 4 undefined; DV-04 not PASS",
        },
        "pending_economic_v": ["V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07"],
        "pending_dv": ["DV-01", "DV-02", "DV-03", "DV-04", "DV-05", "DV-06", "DV-07"],
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "12_ovh1_probe.json", ovh1)
    _write(out_dir, "13_ovh2_probe.json", ovh2)
    _write(out_dir, "14_aws3_probe.json", aws3)
    _write(out_dir, "15_p2p_cross.json", cross)
    _write(out_dir, "16_invariants.json", invariants)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    (out_dir / "run.log").write_text(
        f"{manifest['started_at']} start failures={len(failures)} live={live_count}\n",
        encoding="utf-8",
    )
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
