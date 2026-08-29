#!/usr/bin/env python3
"""Simulation 169 — provenance + replicated settlement + live SHA/TLS probe.

Does not invent results. Does not create a new OVH machine.
Does not claim mainnet certification.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("ARTCB_WALLET_PASSPHRASE", "test-passphrase-artcb-dev-32chars!")
os.environ.setdefault("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
os.environ.setdefault("ARTCB_ALLOW_INSECURE_HTTP", "1")  # HTTP /me until TLS proven in-process

from src.artcb.economics.hbp import hbp_rate, hbp_rate_from_ratio  # noqa: E402
from src.artcb.economics.owner_decay import payout_owner_share  # noqa: E402
from src.artcb.economics.replicated_settlement import Cluster, build_cluster  # noqa: E402
from src.artcb.live import DEFAULT_LIVE_HTTPS_URL, DEFAULT_LIVE_URL, http_json  # noqa: E402
from src.artcb.sim_provenance import collect, dumps, finish  # noqa: E402


def _ts() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_e2e169_secure_live"


def _write(path: Path, obj: object) -> None:
    path.write_text(dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def v_options() -> dict:
    """Hypothesis only — V-01…V-07 remain unfrozen."""
    return {
        "classification": "HYPOTHESIS",
        "not_a_go": True,
        "V-01_snapshot_start": "implemented default; not user-locked",
        "V-02_transfer_next_epoch": "implemented default; not user-locked",
        "V-03_grace_24h": "implemented default; sim uses 1s",
        "V-04_retire_next_snapshot": "implemented default; not user-locked",
        "V-05_finality": {"N_confirmations": 2, "quorum": "not implemented", "status": "unfrozen"},
        "V-06_h_adult_max": "DemographicReference model exists; WPP 18+ extract still missing",
        "V-07_hbp": {
            "live_hbp_rate_H0": hbp_rate(0),
            "ratio_0": hbp_rate_from_ratio(h_verified=0.0, h_adult_max=1.0),
            "ratio_half": hbp_rate_from_ratio(h_verified=0.5, h_adult_max=1.0),
            "ratio_one": hbp_rate_from_ratio(h_verified=1.0, h_adult_max=1.0),
            "live_path_unchanged": True,
        },
        "M1_100": payout_owner_share(is_first_machine=True, n_economic=4),
        "extra_n4": payout_owner_share(is_first_machine=False, n_economic=4),
    }


def run_distributed(work: Path) -> dict:
    cluster: Cluster | None = None
    tests: list[dict] = []
    try:
        cluster = build_cluster(work / "replicas")
        time.sleep(0.15)

        # T1 same WorkID + same SID concurrent
        def _one(node: str) -> dict:
            return cluster.settle(proposer=node, work_id="WorkID-X", snapshot_digest="snap-1")

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_one, ["A", "B", "C", "D"]))
        oks = [r for r in results if r.get("ok")]
        tests.append({
            "id": "T1_concurrent_same_sid",
            "classification": "DISTRIBUTED PROCESS SIMULATION",
            "ok_count": len(oks),
            "expected": "exactly_one_ok",
            "pass": len(oks) == 1,
            "counts": cluster.consumed_counts("WorkID-X"),
        })

        # T2 different SID same WorkID
        r2 = cluster.settle(
            proposer="B",
            work_id="WorkID-X",
            snapshot_digest="snap-1",
            forged_sid="forged-sid-169",
        )
        tests.append({
            "id": "T2_same_work_different_sid",
            "classification": "DISTRIBUTED PROCESS SIMULATION",
            "ok": r2.get("ok"),
            "expected": "reject",
            "pass": r2.get("ok") is False,
            "reason": r2.get("reason"),
        })

        # T3 different snapshot same WorkID
        r3 = cluster.settle(proposer="C", work_id="WorkID-X", snapshot_digest="snap-OTHER")
        tests.append({
            "id": "T3_same_work_different_snapshot",
            "classification": "DISTRIBUTED PROCESS SIMULATION",
            "ok": r3.get("ok"),
            "expected": "reject (WorkID uniqueness)",
            "pass": r3.get("ok") is False,
        })

        # T4 crash/restart of replica A — ledger file persists
        a_dir = work / "replicas" / "A"
        before = cluster.replicas[0].state.ledger.count_for_work("WorkID-X")
        cluster.replicas[0].stop()
        from src.artcb.economics.economic_snapshot import SettlementLedger

        restarted = SettlementLedger(a_dir / "ledger.json")
        tests.append({
            "id": "T4_crash_restart_no_double",
            "classification": "DISTRIBUTED PROCESS SIMULATION",
            "before": before,
            "after_reload": restarted.count_for_work("WorkID-X"),
            "pass": before == 1 and restarted.count_for_work("WorkID-X") == 1,
        })

        # T5/T6 partition then heal
        cluster.isolate("C", True)
        cluster.isolate("D", True)
        r5 = cluster.settle(proposer="A", work_id="WorkID-PART", snapshot_digest="snap-1")
        cluster.isolate("C", False)
        cluster.isolate("D", False)
        r6 = cluster.settle(proposer="C", work_id="WorkID-PART", snapshot_digest="snap-1")
        tests.append({
            "id": "T5_partition_majority_A_B",
            "classification": "DISTRIBUTED PROCESS SIMULATION",
            "ok": r5.get("ok"),
            "prepared": r5.get("prepared"),
            "pass": r5.get("ok") is False,
            "note": "majority is 3 of 4; isolating C+D leaves 2 < 3 so settle must fail",
        })
        tests.append({
            "id": "T6_heal_no_double",
            "classification": "DISTRIBUTED PROCESS SIMULATION",
            "second_ok": r6.get("ok"),
            "counts": cluster.consumed_counts("WorkID-PART"),
            "pass": cluster.consumed_counts("WorkID-PART")["A"] <= 1,
        })

        # T7 already covered by T1
        # T8 epoch change still unique WorkID
        r8 = cluster.settle(proposer="A", work_id="WorkID-X", snapshot_digest="snap-1", epoch=2)
        tests.append({
            "id": "T8_replay_after_epoch",
            "classification": "DISTRIBUTED PROCESS SIMULATION",
            "ok": r8.get("ok"),
            "pass": r8.get("ok") is False,
        })

        # T9/T10 documented as snapshot/transfer rules already in 167 coordinator
        tests.append({
            "id": "T9_transfer_window",
            "classification": "SIMULÉ (167 EpochCoordinator, not re-run as 4 OVH VMs)",
            "pass": None,
            "note": "see 167 transfer_does_not_mutate_live_until_next_epoch",
        })
        tests.append({
            "id": "T10_snapshot_change",
            "classification": "SIMULÉ (same WorkID uniqueness as T3)",
            "pass": r3.get("ok") is False,
        })
    finally:
        if cluster:
            try:
                cluster.stop()
            except Exception:
                pass
    return {"tests": tests, "all_boolean_pass": all(t.get("pass") for t in tests if t.get("pass") is not None)}


def live_probe() -> dict:
    http_url = DEFAULT_LIVE_URL
    https_url = os.environ.get("ARTCB_API_HTTPS_URL", DEFAULT_LIVE_HTTPS_URL)
    h_code, health = http_json("GET", f"{http_url}/health")
    s_code, shealth = http_json("GET", f"{https_url}/health")
    me_code, me = http_json("GET", f"{http_url}/api/v1/api-keys/me")
    https_me_code, https_me = http_json("GET", f"{https_url}/api/v1/api-keys/me")
    expected = os.environ.get("ARTCB_EXPECTED_LIVE_SHA", "")
    live_sha = health.get("git_sha") if isinstance(health, dict) else None
    return {
        "classification": "PROBE LIVE",
        "http_health": h_code,
        "https_health": s_code,
        "http_me": me_code,
        "https_me": https_me_code,
        "live_git_sha": live_sha,
        "live_git_branch": health.get("git_branch") if isinstance(health, dict) else None,
        "expected_main_sha": expected or None,
        "sha_match_main": bool(expected) and live_sha == expected,
        "https_up": s_code == 200,
        "key_id": (https_me or me or {}).get("key_id") if isinstance(https_me or me, dict) else None,
        "new_ovh_machine": False,
    }


def main() -> int:
    out = ROOT / "simulations" / _ts()
    out.mkdir(parents=True, exist_ok=True)
    (out / "work").mkdir(exist_ok=True)
    manifest = collect(
        protocol_version="169-secure-live",
        economic_rules_version="D-025+V01-V07-provisional+D-027",
        simulation_id="e2e169_secure_live",
        seed=169,
        script_path=Path(__file__),
        extra={"new_ovh_machine": False, "existing_node_only": True},
    )
    dist = run_distributed(out / "work")
    probe = live_probe()
    options = v_options()
    failures = []
    if not dist.get("all_boolean_pass"):
        failures.append({"code": "DISTRIBUTED_INVARIANT", "tests": [t for t in dist["tests"] if t.get("pass") is False]})
    if probe.get("http_health") != 200:
        failures.append({"code": "LIVE_HTTP_HEALTH", "http": probe.get("http_health")})
    summary = {
        "simulation": "e2e169_secure_live",
        "dir": str(out),
        "failures": failures,
        "failure_count": len(failures),
        "invented": False,
        "certified_distributed_mainnet": False,
        "new_ovh_machine": False,
        "categories": {
            "LOCAL_ADVERSARIAL": "see 168 artifacts (not re-labelled as live)",
            "LIVE_NODE_PROBE": probe,
            "DISTRIBUTED_CONSENSUS": "4 HTTP replicas on 127.0.0.1 — NOT 4 OVH VMs",
        },
        "sha_match": probe.get("sha_match_main"),
        "https_up": probe.get("https_up"),
        "pending_validation": ["V-01", "V-02", "V-03", "V-04", "V-05", "V-06", "V-07"],
    }
    _write(out / "00_manifest.json", finish(manifest))
    _write(out / "02_v_options_hypothesis.json", options)
    _write(out / "11_distributed_settlement.json", dist)
    _write(out / "16_invariants.json", {t["id"]: t.get("pass") for t in dist["tests"]})
    _write(out / "17_failures.json", failures)
    _write(out / "18_summary.json", summary)
    _write(out / "19_live_probe.json", probe)
    (out / "run.log").write_text(
        f"{manifest.get('started_at')} start\n"
        f"failures={len(failures)} https={probe.get('https_up')} sha_match={probe.get('sha_match_main')}\n",
        encoding="utf-8",
    )
    print(json.dumps({"dir": str(out), "failures": failures, "https_up": probe.get("https_up"),
                      "live_sha": probe.get("live_git_sha"), "invented": False}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
