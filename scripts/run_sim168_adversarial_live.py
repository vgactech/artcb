#!/usr/bin/env python3
"""Simulation 168 — adversarial replay + live node probe.

Local ledger attacks are executed here. Live numbers come only from HTTP.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from src.artcb.economics.economic_snapshot import AlreadySettled, SettlementLedger, settlement_id  # noqa: E402


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_dir() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_e2e168_adversarial_live"


def _write(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_adversarial(work: Path) -> dict:
    ledger = SettlementLedger(work / "ledger.json")
    sid = settlement_id(work_id="WorkID-X", snapshot_digest="digest-canonical", protocol_version="167-distributed-snapshot")
    events = []
    first = ledger.consume(sid, work_id="WorkID-X", node_id="A", epoch=1)
    events.append({"op": "first", "ok": True, "sid": sid[:16], "node": "A"})
    for node, extra_sid in (("B", sid), ("C", "forged-sid"), ("A", sid)):
        try:
            ledger.consume(extra_sid, work_id="WorkID-X", node_id=node, epoch=1)
            events.append({"op": "replay", "ok": True, "node": node})
        except AlreadySettled as exc:
            events.append({"op": "replay", "ok": False, "node": node, "error": type(exc).__name__})
    # reordering of independent work ids must still be unique per id
    sid_y = settlement_id(work_id="WorkID-Y", snapshot_digest="digest-canonical", protocol_version="167-distributed-snapshot")
    ledger.consume(sid_y, work_id="WorkID-Y", node_id="D", epoch=1)
    try:
        ledger.consume(sid_y, work_id="WorkID-Y", node_id="A", epoch=2)
        y_dup = True
    except AlreadySettled:
        y_dup = False
    return {
        "events": events,
        "count_x": ledger.count_for_work("WorkID-X"),
        "count_y": ledger.count_for_work("WorkID-Y"),
        "y_duplicate_rejected": y_dup is False,
        "invariants": {
            "workid_x_eq_1": ledger.count_for_work("WorkID-X") == 1,
            "all_replays_rejected": all(not e["ok"] for e in events if e["op"] == "replay"),
            "y_unique": ledger.count_for_work("WorkID-Y") == 1,
        },
        "first_sid_prefix": first["settlement_id"][:16],
    }


def live_probe() -> dict:
    script = ROOT / "scripts" / "artcb_live_bootstrap.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    try:
        payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError:
        payload = {"ok": False, "parse_error": True, "rc": completed.returncode}
    payload["bootstrap_rc"] = completed.returncode
    return payload


def main() -> int:
    stamp = _ts_dir()
    out = ROOT / "simulations" / stamp
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    started = _now()
    adv = run_adversarial(work)
    probe = live_probe()
    finished = _now()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    failures = []
    if not all(adv["invariants"].values()):
        failures.append({"code": "ADVERSARIAL_INVARIANT", "detail": adv["invariants"]})
    if not probe.get("ok"):
        failures.append({"code": "LIVE_HEALTH", "detail": {"http": probe.get("health_http")}})
    summary = {
        "simulation": "e2e168_adversarial_live",
        "dir": str(out),
        "failures": failures,
        "failure_count": len(failures),
        "invariants": adv["invariants"],
        "live": {
            "ok": bool(probe.get("ok")),
            "url": probe.get("live_url"),
            "git_sha": probe.get("git_sha"),
            "git_branch": probe.get("git_branch"),
            "key_present": probe.get("key_present"),
            "key_source": probe.get("key_source"),
            "me_http": probe.get("me_http"),
            "key_id": probe.get("key_id"),
        },
        "certified_distributed_mainnet": False,
        "invented": False,
        "pending_validation": ["V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07"],
    }
    manifest = {
        "commit_sha": sha,
        "protocol_version": "168-adversarial-live",
        "economic_rules_version": "D-025+V01-V07-provisional",
        "simulation_id": "e2e168_adversarial_live",
        "random_seed": 168,
        "started_at": started,
        "finished_at": finished,
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependency_hash": hashlib.sha256((sys.version + sha).encode()).hexdigest(),
        "invented_results": False,
    }
    _write(out / "00_manifest.json", manifest)
    _write(out / "10_network_events.json", {"note": "local adversarial; live probe separate", "probe_branch": probe.get("git_branch")})
    _write(out / "12_settlements.json", adv)
    _write(out / "16_invariants.json", adv["invariants"])
    _write(out / "17_failures.json", failures)
    _write(out / "18_summary.json", summary)
    _write(out / "19_live_probe.json", probe)
    (out / "run.log").write_text(
        f"{started} start\n{finished} finish failures={len(failures)} live_ok={probe.get('ok')}\n",
        encoding="utf-8",
    )
    print(json.dumps({"dir": str(out), "failures": failures, "live_ok": probe.get("ok"), "invented": False}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
