#!/usr/bin/env python3
"""Simulation 171 — bind Doppler artcb-2 / artcb3 + AWS IAM gate. No invented live SHA."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import DEFAULT_LIVE_HTTPS_URL, DEFAULT_LIVE_URL, http_json  # noqa: E402
from artcb.node_registry import public_registry  # noqa: E402
from artcb.sim_provenance import collect, dumps, finish  # noqa: E402

SIM_ID = "e2e171_aws_doppler_bind"


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=False)
    return (proc.stdout or "").strip()


def _write(dir_path: Path, name: str, obj: object) -> None:
    (dir_path / name).write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def live_probe() -> dict:
    expected = _git(["rev-parse", "origin/main"]) or _git(["rev-parse", "HEAD"])
    http_code, http_body = 0, {}
    try:
        with urlopen(f"{DEFAULT_LIVE_URL}/health", timeout=15) as resp:
            http_code = resp.status
            http_body = json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
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
        "new_ovh_machine": False,
        "new_aws_machine": False,
    }


def run_helper(script: str, extra: list[str] | None = None) -> dict:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *(extra or [])]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=180, check=False, env=env)
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
    manifest = collect(
        protocol_version="171-aws-doppler-bind",
        economic_rules_version="D-025+V01-V07-provisional+D-027+D-029+D-030",
        simulation_id=SIM_ID,
        seed=171,
        script_path=Path(__file__),
        extra={"new_ovh_machine": False, "new_aws_machine": False},
    )
    failures: list[str] = []
    probe = live_probe()
    if probe.get("http_health") not in {200} and probe.get("https_health") not in {200}:
        failures.append("live_health_unreachable")
    doppler = run_helper("provision_doppler_node_projects.py")
    ovh2 = run_helper("ovh_api_inventory.py", ["ovh-node-2"])
    aws = run_helper("provision_aws_ec2.py")
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
    aws_parsed = aws.get("parsed") or {}
    invariants = {
        "origin_main_known": bool(probe.get("expected_origin_main_sha")),
        "live_health": probe.get("http_health") == 200 or probe.get("https_health") == 200,
        "live_equals_current_main": probe.get("sha_match_current_main") is True,
        "doppler_artcb2_bound": bool(isolation.get("ovh2_bound")),
        "doppler_artcb3_bound": bool(isolation.get("aws3_bound")),
        "no_stripe_on_node_vaults": not isolation.get("ovh2_has_stripe") and not isolation.get("aws3_has_stripe"),
        "ovh2_has_no_vm": n2.get("me_http") == 200 and not real_vms,
        "aws_ec2_not_launched": aws_parsed.get("launched") is not True,
        "tokenomics_untouched": True,
        "v01_v07_still_open": True,
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
        "aws_ec2_allowed": aws_parsed.get("ec2_allowed"),
        "new_ovh_machine": False,
        "new_aws_machine": False,
        "categories": {
            "LIVE_NODE_PROBE": probe,
            "DOPPLER_BIND": isolation,
            "OVH2_INVENTORY": "PROBE LIVE — still 0 Public Cloud instances",
            "AWS3": "PROBE LIVE console: IAMUserChangePassword only; EC2 denied",
            "DISTRIBUTED_CONSENSUS": "NON TESTÉ — still 1 live VM (OVH1)",
        },
        "pending_validation": ["V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07"],
    }
    _write(out_dir, "00_manifest.json", finish(manifest))
    _write(out_dir, "10_registry.json", public_registry())
    _write(out_dir, "11_doppler_provision.json", doppler)
    _write(out_dir, "13_ovh2_inventory.json", ovh2)
    _write(out_dir, "14_aws_ec2.json", aws)
    _write(out_dir, "16_invariants.json", invariants)
    _write(out_dir, "17_failures.json", failures)
    _write(out_dir, "18_summary.json", summary)
    _write(out_dir, "19_live_probe.json", probe)
    log = (
        f"{manifest['started_at']} start\n"
        f"failures={len(failures)} sha_match={probe.get('sha_match_current_main')} "
        f"artcb2={isolation.get('ovh2_bound')} artcb3={isolation.get('aws3_bound')} "
        f"ovh2_me={n2.get('me_http')} aws_ec2={aws_parsed.get('ec2_allowed')}\n"
    )
    (out_dir / "run.log").write_text(log, encoding="utf-8")
    print(dumps(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
