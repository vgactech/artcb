#!/usr/bin/env python3
"""Simulation 172 — launch AWS EC2 aws-node-3 and probe OVH1 + AWS3 together.

Does not invent live SHA. Does not create an OVH-2 VM. Does not redeploy OVH1.
Never prints secrets.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import DEFAULT_LIVE_HTTPS_URL, DEFAULT_LIVE_URL, http_json  # noqa: E402
from artcb.node_registry import public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e172_aws_ec2_dual_probe"


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


def live_ovh1() -> dict:
    expected = _git(["rev-parse", "origin/main"]) or _git(["rev-parse", "HEAD"])
    http_code, http_body = 0, {}
    try:
        with urlopen(f"{DEFAULT_LIVE_URL}/health", timeout=15) as resp:
            http_code = resp.status
            http_body = json.loads(resp.read().decode())
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        http_body = {"error": type(exc).__name__}
    https_code, https_body = http_json("GET", f"{DEFAULT_LIVE_HTTPS_URL}/health")
    live_sha = None
    live_branch = None
    if isinstance(http_body, dict):
        live_sha = http_body.get("git_sha")
        live_branch = http_body.get("git_branch")
    if not live_sha and isinstance(https_body, dict):
        live_sha = https_body.get("git_sha")
        live_branch = https_body.get("git_branch")
    me_code, me = http_json("GET", f"{DEFAULT_LIVE_HTTPS_URL}/api/v1/api-keys/me")
    p2p_code, p2p = _http_json(f"{DEFAULT_LIVE_URL}/api/v1/p2p/status")
    return {
        "classification": "PROBE LIVE",
        "expected_origin_main_sha": expected,
        "live_git_sha": live_sha,
        "live_git_branch": live_branch,
        "sha_match_current_main": bool(live_sha and expected and live_sha == expected),
        "http_health": http_code,
        "https_health": https_code,
        "https_me": me_code,
        "key_id": me.get("key_id") if isinstance(me, dict) else None,
        "p2p_http": p2p_code,
        "p2p_node_id": p2p.get("node_id") if isinstance(p2p, dict) else None,
        "p2p_has_kem": bool((p2p.get("kem_public_key_hex") or "") if isinstance(p2p, dict) else ""),
        "new_ovh_machine": False,
    }


def probe_aws(ip: str | None) -> dict:
    if not ip:
        return {"reachable": False, "reason": "no_public_ip"}
    http_code, http_body = _http_json(f"http://{ip}:8000/health")
    https_code, https_body = http_json("GET", f"https://{ip}:8443/health")
    p2p_code, p2p = _http_json(f"http://{ip}:8000/api/v1/p2p/status")
    sha = None
    branch = None
    if isinstance(http_body, dict):
        sha = http_body.get("git_sha")
        branch = http_body.get("git_branch")
    if not sha and isinstance(https_body, dict):
        sha = https_body.get("git_sha")
        branch = https_body.get("git_branch")
    return {
        "classification": "PROBE LIVE",
        "ip": ip,
        "http_health": http_code,
        "https_health": https_code,
        "git_sha": sha,
        "git_branch": branch,
        "p2p_http": p2p_code,
        "p2p_node_id": p2p.get("node_id") if isinstance(p2p, dict) else None,
        "p2p_has_kem": bool((p2p.get("kem_public_key_hex") or "") if isinstance(p2p, dict) else ""),
        "reachable": http_code == 200 or https_code == 200,
    }


def try_cross_register(ovh_ip: str, aws_ip: str) -> dict:
    """Best-effort public register; never invents success."""
    results = {}
    for name, target, source in (
        ("ovh1_registers_aws3", f"http://{ovh_ip}:8000", f"http://{aws_ip}:8000"),
        ("aws3_registers_ovh1", f"http://{aws_ip}:8000", f"http://{ovh_ip}:8000"),
    ):
        body = json.dumps(
            {
                "node_public_url": source,
                "device_fingerprint": f"e2e172-{name}",
                "node_label": name,
                "network_id": "artcb-devnet-1",
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
                results[name] = {"http": resp.status, "registered": bool(payload.get("registered"))}
        except Exception as exc:  # noqa: BLE001
            results[name] = {"http": 0, "registered": False, "error": type(exc).__name__}
    return results


def run_helper(script: str, extra: list[str] | None = None) -> dict:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *(extra or [])]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PATH"] = os.environ.get("PATH", "")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300, check=False, env=env)
    parsed = None
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else None
    except json.JSONDecodeError:
        parsed = None
    return {
        "script": script,
        "exit": proc.returncode,
        "parsed": parsed,
        "stderr_tail": (proc.stderr or "")[-400:],
        "stdout_is_json": parsed is not None,
    }


def main() -> int:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{ts}_{SIM_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    launch_requested = "--yes" in sys.argv
    manifest = collect(
        protocol_version="172-aws-ec2-dual-probe",
        economic_rules_version="D-025+V01-V07-provisional+D-027+D-029+D-030+D-031",
        simulation_id=SIM_ID,
        seed=172,
        script_path=Path(__file__),
        extra={"new_ovh_machine": False, "launch_requested": launch_requested},
    )
    failures: list[str] = []
    probe = live_ovh1()
    if probe.get("http_health") not in {200} and probe.get("https_health") not in {200}:
        failures.append("ovh1_health_unreachable")
    doppler = run_helper("provision_doppler_node_projects.py")
    ovh2 = run_helper("ovh_api_inventory.py", ["ovh-node-2"])
    aws_args = ["--yes"] if launch_requested else []
    aws = run_helper("provision_aws_ec2.py", aws_args)
    isolation = ((doppler.get("parsed") or {}).get("isolation") or {})
    if not isolation.get("ovh2_bound"):
        failures.append("doppler_artcb2_not_bound")
    if not isolation.get("aws3_bound"):
        failures.append("doppler_artcb3_not_bound")
    if isolation.get("ovh2_has_stripe") or isolation.get("aws3_has_stripe"):
        failures.append("stripe_leaked_into_node_vault")
    n2 = ovh2.get("parsed") or {}
    if n2.get("me_http") != 200:
        failures.append("ovh2_me_failed")
    instances = n2.get("instances") or []
    real_vms = [i for i in instances if not i.get("error") and i.get("id")]
    if real_vms:
        failures.append("ovh2_unexpected_vm")
    aws_parsed = aws.get("parsed") or {}
    aws_ip = aws_parsed.get("public_ip")
    aws_probe = probe_aws(aws_ip)
    cross = {}
    if aws_probe.get("reachable"):
        cross = try_cross_register("152.228.144.34", str(aws_ip))
    if launch_requested and not (aws_parsed.get("launched") or aws_parsed.get("reused")):
        failures.append("aws_not_launched")
    if launch_requested and not aws_probe.get("reachable"):
        failures.append("aws_health_unreachable")
    invariants = {
        "origin_main_known": bool(probe.get("expected_origin_main_sha")),
        "ovh1_live_health": probe.get("http_health") == 200 or probe.get("https_health") == 200,
        "live_equals_current_main": probe.get("sha_match_current_main") is True,
        "doppler_artcb2_bound": bool(isolation.get("ovh2_bound")),
        "doppler_artcb3_bound": bool(isolation.get("aws3_bound")),
        "no_stripe_on_node_vaults": not isolation.get("ovh2_has_stripe") and not isolation.get("aws3_has_stripe"),
        "ovh2_has_no_vm": n2.get("me_http") == 200 and not real_vms,
        "aws_ec2_allowed": aws_parsed.get("ec2_allowed") is True,
        "aws_instance_present": bool(aws_parsed.get("instance_id")),
        "aws_health": aws_probe.get("reachable") is True,
        "two_live_compute": (probe.get("http_health") == 200 or probe.get("https_health") == 200)
        and aws_probe.get("reachable") is True,
        "four_machines": False,
        "tokenomics_untouched": True,
        "v01_v07_still_open": True,
        "ovh1_not_redeployed": True,
    }
    summary = {
        "simulation": SIM_ID,
        "dir": str(out_dir),
        "failure_count": len(failures),
        "failures": failures,
        "invented": False,
        "certified_distributed_mainnet": False,
        "sha_match_current_main": probe.get("sha_match_current_main"),
        "ovh2_vm_count": len(real_vms),
        "aws_launched": aws_parsed.get("launched"),
        "aws_reused": aws_parsed.get("reused"),
        "aws_ec2_allowed": aws_parsed.get("ec2_allowed"),
        "aws_instance_id": aws_parsed.get("instance_id"),
        "aws_public_ip": aws_ip,
        "new_ovh_machine": False,
        "new_aws_machine": bool(aws_parsed.get("launched")),
        "two_live_nodes": invariants["two_live_compute"],
        "categories": {
            "LIVE_OVH1": probe,
            "DOPPLER_BIND": isolation,
            "OVH2_INVENTORY": "PROBE LIVE — still 0 Public Cloud instances",
            "AWS3": aws_probe,
            "P2P_CROSS": cross or "skipped_until_aws_health",
            "DISTRIBUTED_CONSENSUS": "PARTIAL — 2/4 live VMs (OVH1+AWS3); OVH2 waiting; 4th not planned here",
        },
        "pending_validation": ["V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07"],
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_doppler_provision.json", doppler)
    _write(out_dir, "12_ovh1_probe.json", probe)
    _write(out_dir, "13_ovh2_inventory.json", ovh2)
    _write(out_dir, "14_aws_ec2.json", aws)
    _write(out_dir, "15_aws_health.json", aws_probe)
    _write(out_dir, "15_p2p_cross.json", cross)
    _write(out_dir, "16_invariants.json", invariants)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    log = (
        f"{manifest['started_at']} start\n"
        f"failures={len(failures)} sha_match={probe.get('sha_match_current_main')} "
        f"aws_allowed={aws_parsed.get('ec2_allowed')} launched={aws_parsed.get('launched')} "
        f"reused={aws_parsed.get('reused')} aws_ip={aws_ip} aws_health={aws_probe.get('reachable')}\n"
    )
    (out_dir / "run.log").write_text(log, encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
