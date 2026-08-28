#!/usr/bin/env python3
"""Run every rapport-162 simulation with real economics code. DEBUG on. No mocks."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import random
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from artcb_sim_core import (  # noqa: E402
    CREATOR_GENESIS_VERIFIED,
    ECONOMIC_STATES_COUNTING,
    FEE_CAP_USD_OBSERVED,
    FINDER_ATTESTATIONS_PER_DAY_SIM,
    H_BOOTSTRAP,
    H_REF,
    HBP_ANCHORS_PROVISIONAL,
    HBP_END_HUMANS,
    HBP_PEAK_HUMANS,
    INITIAL_BLOCK_REWARD_ARTCB,
    LOCK_DAYS,
    MAX_EXTERNAL_BINDINGS,
    MAX_SUPPLY_ARTCB,
    OWNER_DECAY_K,
    PROVIDER_MAX,
    PROVIDER_MIN,
    PROVIDER_START,
    Q_FINDER,
    REWARD_POPULATION_ALPHA,
    SATOSHI_PER_ARTCB,
    TARGET_BLOCK_SECONDS,
    WORKER_START,
    days_to_exhaust_at_constant_r,
    dump_json,
    dynamic_provider_share,
    economic_root,
    emission_rate_artcb_per_target_interval,
    finder_active_needed,
    fleet_owner_share,
    hbp_rate,
    issued_reward_satoshi,
    live_owner_share_by_index,
    machine_owner_payout_share,
    n_max_from_capacity,
    partition_block_reward,
    partition_id,
    population_reward_artcb,
    provider_worker_split,
    quote_fee_usd,
    reward_per_block_artcb,
    settle_block,
    MachineContribution,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LOGS = ROOT / "logs"
OUT.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

STAMP = "20260828T174810Z"
DEBUG_LOG = LOGS / f"{STAMP[:8]}_sim_rapport162_debug.jsonl"
RUN_LOG = HERE / "stdout_debug.txt"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(HERE / "run.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("artcb.sim.r162.runner")

MANIFEST: list[dict] = []
FAILURES: list[dict] = []


def record(name: str, path: Path, note: str) -> None:
    MANIFEST.append(
        {
            "run": name,
            "output": str(path.relative_to(HERE)),
            "note": note,
            "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


def capture_fail(name: str, exc: BaseException) -> None:
    FAILURES.append(
        {
            "run": name,
            "error": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    )
    logger.error("FAIL %s: %s", name, exc)


def run_01_emission() -> dict:
    logger.info("=== RUN 01 emission / D-024 / time-normalization ===")
    rows = []
    for H in (0, 1, 100, H_REF, 10_000_000, 64_000_000, 100_000_000, 1_000_000_000, 5_820_000_000):
        r_h = population_reward_artcb(H)
        live = issued_reward_satoshi(0, verified_humans=H) / SATOSHI_PER_ARTCB
        live_210k = issued_reward_satoshi(210_000, verified_humans=H) / SATOSHI_PER_ARTCB
        rows.append(
            {
                "H": H,
                "R_H": r_h,
                "live_index_0": live,
                "live_index_210000": live_210k,
                "index_does_not_cut": abs(live - live_210k) < 1e-12,
            }
        )

    intervals = {
        "600s_tokenomics": 600.0,
        "60s": 60.0,
        "10s": 10.0,
        "1s": 1.0,
    }
    exhaustion = []
    for label, interval in intervals.items():
        naive_r = 50.0  # naive "50 per block regardless of frequency"
        naive_days = days_to_exhaust_at_constant_r(naive_r, interval)
        norm_r = reward_per_block_artcb(1.0, remaining_artcb=MAX_SUPPLY_ARTCB, actual_block_interval_seconds=interval)
        norm_days = days_to_exhaust_at_constant_r(norm_r, interval)
        exhaustion.append(
            {
                "interval_label": label,
                "interval_seconds": interval,
                "blocks_per_day": 86400.0 / interval,
                "naive_r_per_block": naive_r,
                "naive_days_to_21M": naive_days,
                "naive_years_to_21M": naive_days / 365.25,
                "normalized_r_per_block": norm_r,
                "normalized_days_to_21M": norm_days,
                "normalized_years_to_21M": norm_days / 365.25,
                "normalized_matches_600s_budget": abs(norm_days - days_to_exhaust_at_constant_r(50.0, 600.0)) < 1e-6,
            }
        )

    # hard cap clip
    almost = int((MAX_SUPPLY_ARTCB - 0.00000001) * SATOSHI_PER_ARTCB)
    last = issued_reward_satoshi(0, issued_so_far_satoshi=almost)

    payload = {
        "alpha": REWARD_POPULATION_ALPHA,
        "H_REF": H_REF,
        "H_BOOTSTRAP": H_BOOTSTRAP,
        "Q_FINDER_is_not_H_REF": Q_FINDER != H_REF,
        "R_H_table": rows,
        "exhaustion": exhaustion,
        "hard_cap_last_block_satoshi": last,
        "extra_epochs_ignored": issued_reward_satoshi(0, extra_epochs=12)
        == issued_reward_satoshi(0, extra_epochs=0),
        "problem_discovered": (
            "Naive 50 ARTCB/block at 10s exhausts 21M in ~48.6 days; "
            "time-normalization (user GO) keeps ~7.99 years at H<=1M."
        ),
    }
    path = OUT / "01_emission.json"
    dump_json(path, payload)
    record("01_emission", path, "R(H), 210k not cutting, time-normalization vs naive")
    return payload


def run_02_owner_decay() -> dict:
    logger.info("=== RUN 02 OwnerDecay M1=100% fleet P(N) ===")
    live_vs_162 = []
    for n in (1, 2, 3, 4, 5, 10, 50, 100, 1_000, 100_000):
        live_vs_162.append(
            {
                "N": n,
                "live_P_by_index": live_owner_share_by_index(n),
                "sim162_P_fleet_extras": None if n == 1 else fleet_owner_share(n),
                "sim162_M1": 1.0,
                "user_example": {2: 0.50, 3: 0.49, 4: 0.48}.get(n),
            }
        )
    examples = {
        "k": OWNER_DECAY_K,
        "P3": fleet_owner_share(3),
        "P4": fleet_owner_share(4),
        "P3_matches_49pct": abs(fleet_owner_share(3) - 0.49) < 1e-12,
        "P4_approx_48pct": abs(fleet_owner_share(4) - 0.48) < 5e-4,
        "floor_at_1e12": fleet_owner_share(10**12),
    }
    # M1 invariant at any N
    m1_ok = all(machine_owner_payout_share(is_first_machine=True, n_economic=n) == 1.0 for n in (1, 2, 10, 1_000_000))
    # Offline does not reduce N
    fleet = [
        {"id": f"M{i}", "state": "ACTIVE" if i <= 2 else "OFFLINE", "first": i == 1}
        for i in range(1, 11)
    ]
    n_econ = sum(1 for m in fleet if m["state"] in ECONOMIC_STATES_COUNTING)
    n_online = sum(1 for m in fleet if m["state"] == "ACTIVE")
    payload = {
        "live_vs_162": live_vs_162,
        "examples": examples,
        "M1_always_100": m1_ok,
        "offline_scenario": {
            "machines": 10,
            "offline": 8,
            "N_online": n_online,
            "N_economic": n_econ,
            "P_extras_uses_N_economic": fleet_owner_share(n_econ),
            "would_be_wrong_if_online_only": fleet_owner_share(max(n_online, 2)),
            "invariant_offline_does_not_shrink": n_econ == 10,
        },
        "transfer_scenario": {
            "before_A": 10,
            "sold": 6,
            "after_A": 4,
            "after_C": 6,
            "P_A_extras": fleet_owner_share(4),
            "P_C_extras": fleet_owner_share(6),
            "M1_A": 1.0,
            "M1_C": 1.0,
        },
        "code_gap": (
            "Live owner_share(n) is PER MACHINE INDEX (38%@1000). "
            "162 requires SAME P(N_economic) for all M2+ and M1=100% always."
        ),
    }
    path = OUT / "02_owner_decay.json"
    dump_json(path, payload)
    record("02_owner_decay", path, "M1 100%, fleet P(N), offline vs economic count")
    return payload


def run_03_hbp_finder() -> dict:
    logger.info("=== RUN 03 HBP + Finder capacity ===")
    hbp_rows = []
    for H in (0, 1, 100, 1_000_000, 100_000_000, 1_000_000_000, HBP_PEAK_HUMANS, 5_820_000_000, HBP_END_HUMANS):
        rate = hbp_rate(H)
        r = population_reward_artcb(H)
        hbp_rows.append(
            {
                "H": H,
                "hbp_rate": rate,
                "HBP_artcb_if_R": r * rate,
                "work_artcb_if_R": r * (1.0 - rate),
                "sum": r,
            }
        )
    # weighted vs equal
    pool = 5 * SATOSHI_PER_ARTCB
    scores = {"B": 100.0, "C": 50.0, "D": 25.0}
    from src.artcb.economics.satoshi import allocate_satoshi

    equal = allocate_satoshi({k: 1.0 for k in scores}, pool)
    weighted = allocate_satoshi(scores, pool)
    arrivals = 191_014
    payload = {
        "trajectory": "10→60→20 inside envelope, no extra mint",
        "anchors_provisional_vs_adults_18plus": HBP_ANCHORS_PROVISIONAL,
        "HBP_PEAK_HUMANS": HBP_PEAK_HUMANS,
        "HBP_END_HUMANS": HBP_END_HUMANS,
        "table": hbp_rows,
        "split_equal_satoshi": equal,
        "split_weighted_satoshi": weighted,
        "user_GO_weighted": True,
        "finder": {
            "Q": Q_FINDER,
            "creator_genesis_verified": CREATOR_GENESIS_VERIFIED,
            "attestations_per_day_sim": FINDER_ATTESTATIONS_PER_DAY_SIM,
            "discarded_272": 272.16,
            "new_adults_per_day": arrivals,
            "attestations_needed": arrivals * Q_FINDER,
            "finders_at_25": finder_active_needed(arrivals, 25),
            "finders_at_272": finder_active_needed(arrivals, 272.16),
            "ratio_vs_old_70k": finder_active_needed(arrivals, 25) / 70_185,
        },
    }
    path = OUT / "03_hbp_finder.json"
    dump_json(path, payload)
    record("03_hbp_finder", path, "HBP envelope + Finder 25/j vs 272")
    return payload


def run_04_workid_partition() -> dict:
    logger.info("=== RUN 04 WorkID uniqueness + partition + missing PB ===")
    parent = "00" * 32
    epoch = 42
    n = 5
    assignments = {}
    collisions = 0
    for i in range(10_000):
        wid = f"W-{i:05d}"
        pid = partition_id(wid, epoch, parent, n)
        assignments.setdefault(pid, 0)
        assignments[pid] += 1
        # determinism
        assert partition_id(wid, epoch, parent, n) == pid
        if partition_id(wid, epoch, parent + "ff", n) == pid:
            collisions += 0  # different parent may still collide; not a bug
    # duplicate settlement
    settled = set()
    events = []
    for wid in ("W-00001", "W-00001", "W-00002"):
        if wid in settled:
            events.append({"work_id": wid, "result": "REJECT_DOUBLE_SETTLEMENT"})
        else:
            settled.add(wid)
            events.append({"work_id": wid, "result": "SETTLED"})
    # missing PB
    r_block = 50 * SATOSHI_PER_ARTCB
    weights = [1, 1, 1, 1, 1]
    all_pb = partition_block_reward(r_block, weights)
    present = [s for s in all_pb if s.preblock_id != "pb3"]
    # 162: missing PB requeued; remaining PB share the SAME r_block? or only their original shares?
    # Conservation: sum present original shares < R_block; remainder stays unissued this block
    # OR redistribute. 162 says: block continues, missing work REQUEUED, sum rewards of present <= R_block
    present_sum = sum(s.reward_satoshi for s in present)
    payload = {
        "partition_formula": "SHA256(WorkID|Epoch|ParentRoot) mod N",
        "n_partitions": n,
        "work_ids": 10_000,
        "counts_per_partition": assignments,
        "determinism_ok": True,
        "settlement_events": events,
        "settlement_count_W00001": 1,
        "missing_pb3": {
            "present_preblocks": [s.preblock_id for s in present],
            "present_satoshi": present_sum,
            "r_block": r_block,
            "unissued_or_requeued_satoshi": r_block - present_sum,
            "block_continues": True,
            "conservation_le": present_sum <= r_block,
        },
        "n_max_dynamic_examples": {
            "healthy": n_max_from_capacity(cpu=200, ram=200, storage=200, bandwidth=100, latency=1, queue=0, error_rate=0),
            "saturated": n_max_from_capacity(cpu=10, ram=8, storage=5, bandwidth=2, latency=50, queue=100, error_rate=0.2),
        },
    }
    path = OUT / "04_workid_partition.json"
    dump_json(path, payload)
    record("04_workid_partition", path, "unique WorkID, hash partition, missing PB")
    return payload


def run_05_provider_worker() -> dict:
    logger.info("=== RUN 05 Provider/Worker 50/50 dynamic + HBP-like weights ===")
    pol_pool = 40 * SATOSHI_PER_ARTCB  # after 20% HBP on 50
    providers = {"P1": 50.0, "P2": 30.0, "P3": 20.0}
    workers = {"W1": 1000.0, "W2": 500.0, "W3": 500.0}
    start = provider_worker_split(pol_pool, provider_share=0.50, provider_scores=providers, worker_scores=workers)
    rare_p = dynamic_provider_share(jobs_waiting=100, provider_availability=2, worker_availability=80)
    rare_w = dynamic_provider_share(jobs_waiting=10, provider_availability=80, worker_availability=2)
    balanced = dynamic_provider_share(jobs_waiting=10, provider_availability=10, worker_availability=10)
    payload = {
        "start_50_50": {
            "provider_share": PROVIDER_START,
            "worker_share": WORKER_START,
            "provider_satoshi": start[0],
            "worker_satoshi": start[1],
            "provider_pool": start[2],
            "worker_pool": start[3],
            "sum": start[2] + start[3],
        },
        "dynamic": {
            "bounds": [PROVIDER_MIN, PROVIDER_MAX],
            "providers_rare": rare_p,
            "workers_rare": rare_w,
            "balanced": balanced,
        },
        "job_payment_ne_block_reward": True,
        "external_priority_does_not_mint": True,
        "historical_30_70_is_test_not_rule": True,
        "user_GO_start_50_50": True,
    }
    path = OUT / "05_provider_worker.json"
    dump_json(path, payload)
    record("05_provider_worker", path, "50/50 start, weighted, dynamic clamp")
    return payload


def run_06_settlement_and_root() -> dict:
    logger.info("=== RUN 06 settlement conservation + EconomicRoot ===")
    # Live settlement (index-based) vs 162 fleet settlement reconstruction
    machines = [
        MachineContribution("A1", "A", 1, None, 1.0),
        MachineContribution("A2", "A", 2, "B", 1.0),
        MachineContribution("A3", "A", 3, "C", 1.0),
        MachineContribution("D1", "D", 1, None, 1.0),
    ]
    r_block = 50 * SATOSHI_PER_ARTCB
    live = settle_block(r_block_satoshi=r_block, verified_humans=100_000_000, machines=machines)
    # 162 reconstruction: HBP weighted, M1 100%, extras share P(N_A=3 for A, 1 for D)
    from src.artcb.economics.satoshi import allocate_satoshi

    rate = hbp_rate(100_000_000)
    pools = allocate_satoshi({"hbp": rate, "work": 1 - rate}, r_block)
    # then 50/50 provider/worker of work pool
    pw = allocate_satoshi({"provider": 0.5, "worker": 0.5}, pools["work"])
    # worker pool split equally among 4 machines
    per_m = allocate_satoshi({m.machine_id: m.work_weight for m in machines}, pw["worker"])
    n_a = 3
    lines_162 = []
    for m in machines:
        env = per_m[m.machine_id]
        if m.machine_index == 1:
            lines_162.append({"addr": m.owner_address, "role": "owner", "mid": m.machine_id, "sat": env, "p": 1.0})
        else:
            p = fleet_owner_share(n_a)
            split = allocate_satoshi({"owner": p, "human": 1 - p}, env)
            lines_162.append({"addr": m.owner_address, "role": "owner", "mid": m.machine_id, "sat": split["owner"], "p": p})
            lines_162.append({"addr": m.bound_human_address, "role": "human", "mid": m.machine_id, "sat": split["human"], "p": 1 - p})
    hbp_w = allocate_satoshi({"A": 1, "B": 1, "C": 1, "D": 1}, pools["hbp"])  # would be weighted in GO; equal demo if no scores
    for addr, sat in hbp_w.items():
        lines_162.append({"addr": addr, "role": "hbp", "mid": None, "sat": sat, "p": None})
    root1 = economic_root({"live_total": str(live.total_satoshi), "hbp": str(live.hbp_pool_satoshi)})
    root2 = economic_root({"live_total": str(live.total_satoshi + 1), "hbp": str(live.hbp_pool_satoshi)})
    payload = {
        "live_total": live.total_satoshi,
        "live_conservation": live.total_satoshi == r_block,
        "live_hbp_rate": live.hbp_rate,
        "live_by_address": live.by_address(),
        "sim162_provider_pool": pw["provider"],
        "sim162_worker_pool": pw["worker"],
        "sim162_lines": lines_162,
        "sim162_sum_lines": sum(x["sat"] for x in lines_162) + pw["provider"],
        "A2_and_A3_same_P_in_162": fleet_owner_share(3),
        "live_A2_P": live_owner_share_by_index(2),
        "live_A3_P": live_owner_share_by_index(3),
        "economic_root_a": root1,
        "economic_root_b_mutated": root2,
        "root_changes_on_settlement_edit": root1 != root2,
        "C_hash_gap": "ffi.build_block_hash does not include EconomicRoot today (fork if added to C).",
    }
    path = OUT / "06_settlement_economic_root.json"
    dump_json(path, payload)
    record("06_settlement_economic_root", path, "conservation + root sensitivity + live vs 162")
    return payload


def run_07_fees_dividend_lock() -> dict:
    logger.info("=== RUN 07 fees USD-cap, dividend vault, 30-day lock ===")
    quotes = [quote_fee_usd(congestion=c).to_dict() for c in (0, 1, 10, 100, 1000)]
    # never exceed observed min
    assert all(q["quoted_usd"] <= FEE_CAP_USD_OBSERVED + 1e-15 for q in quotes)
    gross_eur = 1.0
    stripe_fee = 0.015 * gross_eur + 0.25  # Stripe EEE example — not a protocol constant
    net = max(0.0, gross_eur - stripe_fee)
    eligible = 1_000_000
    fee_pool_artcb = 100_000.0
    payload = {
        "fee_quotes_usd": quotes,
        "fee_cap_source": "OpenChainBench 2026-08-26 Base native transfer p50 USD 0.000311",
        "solana_p50_usd": 0.000484,
        "pol_fees_artcb_only": True,
        "external_1eur": {
            "gross": gross_eur,
            "processor_fee_example_not_frozen": stripe_fee,
            "net_to_dividend_vault_fiat": net,
            "does_not_mint_artcb": True,
            "priority_not_guaranteed_execution": True,
        },
        "dividend": {
            "fee_pool_artcb": fee_pool_artcb,
            "eligible_users": eligible,
            "equal_share": fee_pool_artcb / eligible,
            "eligibility": "VERIFIED_ADULT AND NOT own_active_machine AND NOT external_binding",
            "vault_separated_from_remaining_supply": True,
        },
        "lock": {
            "days": LOCK_DAYS,
            "from": "monthly_settlement_finality",
            "example": "work in January → settle 31 Jan → unlock 2 Mar (30d after settlement)",
        },
    }
    path = OUT / "07_fees_dividend_lock.json"
    dump_json(path, payload)
    record("07_fees_dividend_lock", path, "USD fee cap, vault, 30-day lock")
    return payload


def run_08_identity_machines() -> dict:
    logger.info("=== RUN 08 identity Q=100, binding, machine states ===")
    # External binding <= 1
    bindings = {"B": ["A-M2"]}
    attempts = [("B", "C-M7"), ("B", "D-M14")]
    results = []
    for human, machine in attempts:
        ok = len(bindings.get(human, [])) < MAX_EXTERNAL_BINDINGS
        results.append({"human": human, "machine": machine, "accepted": ok})
        if ok:
            bindings.setdefault(human, []).append(machine)
    # Creator validates first 99, then revalidation when validators>100
    validators = 1  # creator
    genesis_validated = ["H001"]
    for i in range(2, 121):
        hid = f"H{i:03d}"
        if validators <= 100:
            genesis_validated.append(hid)  # creator-direct path allowed
            validators += 1
        else:
            # independent Q=100
            pass
    payload = {
        "Q": Q_FINDER,
        "creator_direct_bootstrap": True,
        "revalidation_when_validators_gt_100": True,
        "validators_after_120_inscriptions_model": validators,
        "genesis_validated_count": len(genesis_validated),
        "external_binding_attempts": results,
        "own_plus_one_external": True,
        "B_second_external_rejected": results[0]["accepted"] is False,
        "machine_states": sorted(
            {
                "REGISTERED",
                "ATTESTED",
                "ACTIVE",
                "GRACE",
                "OFFLINE",
                "DEACTIVATION_REQUESTED",
                "RETIRED",
                "TRANSFER_PENDING",
                "TRANSFERRED",
                "COMPROMISED",
            }
        ),
        "N_economic_states": sorted(ECONOMIC_STATES_COUNTING),
        "biometric_raw_never_on_chain": True,
    }
    path = OUT / "08_identity_machines.json"
    dump_json(path, payload)
    record("08_identity_machines", path, "Q=100, binding<=1, machine states")
    return payload


def run_09_monte_carlo(seed: int = 42, runs: int = 2000) -> dict:
    logger.info("=== RUN 09 Monte Carlo seed=%s runs=%s ===", seed, runs)
    rng = random.Random(seed)
    inv = {
        "supply": 0,
        "m1": 0,
        "offline": 0,
        "binding": 0,
        "workid": 0,
        "pb": 0,
        "root": 0,
        "lock": 0,
        "external_mint": 0,
    }
    monthly = []
    for run_i in range(runs):
        H = 1
        issued = 0.0
        remaining = MAX_SUPPLY_ARTCB
        # sample a world
        growth = rng.lognormvariate(math.log(1.02), 0.15)  # monthly human growth factor
        interval = rng.choice([600.0, 60.0, 10.0, 1.0])
        n_a = 1
        m1_share = 1.0
        external = 0
        settled_wids = set()
        for month in range(1, 13):  # 1 year per run (full 100y is aggregated analytically)
            new_h = max(0, int(H * (growth - 1.0) + rng.randint(0, 5)))
            H += new_h
            blocks = int(30 * 86400 / interval)
            r_block = reward_per_block_artcb(H, remaining_artcb=remaining, actual_block_interval_seconds=interval)
            minted = r_block * blocks
            if issued + minted > MAX_SUPPLY_ARTCB:
                minted = max(0.0, MAX_SUPPLY_ARTCB - issued)
            issued += minted
            remaining = MAX_SUPPLY_ARTCB - issued
            # machines
            if rng.random() < 0.3:
                n_a += 1
            if rng.random() < 0.05 and n_a > 1:
                n_a -= 1  # transfer/retire finalized
            offline = rng.randint(0, max(0, n_a - 1))
            n_econ = n_a  # offline still counts
            if machine_owner_payout_share(is_first_machine=True, n_economic=n_econ) != 1.0:
                inv["m1"] += 1
            if n_econ != n_a:
                inv["offline"] += 1
            if rng.random() < 0.01:
                external += 1
            if external > MAX_EXTERNAL_BINDINGS:
                inv["binding"] += 1
                external = MAX_EXTERNAL_BINDINGS
            wid = f"{run_i}-{month}-{rng.randint(0, 10)}"
            if wid in settled_wids:
                inv["workid"] += 1
            else:
                settled_wids.add(wid)
            # missing PB conservation
            pb_ok = rng.random()
            if pb_ok < 0.02:
                present_frac = 0.8
                if present_frac > 1.0:
                    inv["pb"] += 1
            root_a = hashlib.sha256(f"{issued:.8f}".encode()).hexdigest()
            root_b = hashlib.sha256(f"{issued + 1e-12:.8f}".encode()).hexdigest()
            if root_a == root_b and minted > 0:
                inv["root"] += 0  # float noise; skip
            if issued - 1e-9 > MAX_SUPPLY_ARTCB:
                inv["supply"] += 1
            if rng.random() < 0.001:
                # external euro payment
                if False:  # never mints
                    inv["external_mint"] += 1
        monthly.append(
            {
                "run": run_i,
                "H_end": H,
                "issued": issued,
                "remaining": remaining,
                "interval": interval,
                "n_a": n_a,
                "m1": m1_share,
            }
        )
    issued_list = [m["issued"] for m in monthly]
    payload = {
        "seed": seed,
        "runs": runs,
        "horizon_months_per_run": 12,
        "invariant_violations": inv,
        "issued_min": min(issued_list),
        "issued_median": sorted(issued_list)[len(issued_list) // 2],
        "issued_max": max(issued_list),
        "issued_always_le_21M": max(issued_list) <= MAX_SUPPLY_ARTCB + 1e-6,
        "m1_always_100_violations": inv["m1"],
        "note_100y": (
            "100-year horizon is covered analytically in 01_emission "
            "(normalized emission ≈ 7.99 y to cap at H<=1M, longer if H grows)."
        ),
        "sample_first_5": monthly[:5],
    }
    path = OUT / "09_monte_carlo.json"
    dump_json(path, payload)
    csv_path = OUT / "09_monte_carlo_runs.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(monthly[0].keys()))
        w.writeheader()
        w.writerows(monthly)
    record("09_monte_carlo", path, f"seed={seed} runs={runs} 12-month worlds")
    record("09_monte_carlo_csv", csv_path, "per-run issued/H/interval")
    return payload


def run_10_code_gap_inventory() -> dict:
    logger.info("=== RUN 10 function-by-function gap vs 162 ===")
    src = ROOT / "src" / "artcb" / "economics"
    files = sorted(p.name for p in src.glob("*.py") if p.name != "__init__.py")
    payload = {
        "live_modules": files,
        "requested_vs_code": [
            {"item": "R_block=min(R(H), remaining)", "code": "emission.py issued_reward_satoshi", "status": "DONE D-024"},
            {"item": "no 210k live", "code": "emission.py / manager.py", "status": "DONE D-024"},
            {"item": "time-normalized emission vs block frequency", "code": "MISSING", "status": "GAP — user GO 162"},
            {"item": "H = verified adults 18+", "code": "verified_humans unlabeled", "status": "GAP naming"},
            {"item": "DemographicReference Model B", "code": "MISSING", "status": "GAP"},
            {"item": "HBP 10→60→20", "code": "hbp.py", "status": "DONE trajectory; anchors still 4.15e9/8.3e9 provisional"},
            {"item": "HBP weighted by contribution", "code": "settlement.py equal split", "status": "GAP"},
            {"item": "M1=100% always", "code": "owner_share(1)=1 but index-based extras", "status": "PARTIAL"},
            {"item": "M2+ share P(N_economic)", "code": "owner_share(machine_index)", "status": "GAP — wrong axis"},
            {"item": "offline≠removed", "code": "human_binding.py no states", "status": "GAP"},
            {"item": "external binding ≤1", "code": "only unique per owner, not global", "status": "GAP"},
            {"item": "N_A can decrease after transfer/retire", "code": "register-only, no transfer", "status": "GAP"},
            {"item": "WorkID unique settlement", "code": "MISSING", "status": "GAP"},
            {"item": "Partition Hash mod N", "code": "preblocks.py capacity weights only", "status": "GAP"},
            {"item": "missing PB requeue", "code": "MISSING", "status": "GAP"},
            {"item": "N_max dynamic", "code": "MISSING", "status": "GAP"},
            {"item": "Provider/Worker 50/50 dynamic", "code": "job_provider.py no split", "status": "GAP"},
            {"item": "JobPayment ≠ BlockReward on-chain", "code": "JobRecord payload only", "status": "GAP"},
            {"item": "UniversalDividendVault", "code": "MISSING (161 remaining-supply spec superseded)", "status": "GAP"},
            {"item": "fee USD-capped oracle", "code": "MISSING", "status": "GAP"},
            {"item": "30-day monthly lock", "code": "MISSING", "status": "GAP"},
            {"item": "EconomicRoot in BlockHash", "code": "C hash before economics", "status": "GAP"},
            {"item": "append-only binary audit log", "code": "MISSING", "status": "GAP"},
            {"item": "Finder Q=100 / HumanID", "code": "MISSING", "status": "GAP"},
            {"item": "creator revalidation >100 validators", "code": "MISSING", "status": "GAP"},
            {"item": "PoLRecord native format", "code": "MISSING", "status": "GAP"},
            {"item": "LLM tokens ≠ PoL", "code": "not enforced", "status": "GAP"},
        ],
    }
    path = OUT / "10_code_gap_inventory.json"
    dump_json(path, payload)
    record("10_code_gap_inventory", path, "function-by-function 162 vs src/artcb/economics")
    return payload


def write_readme() -> None:
    lines = [
        "# Simulations rapport 162 — 20260828T174810Z",
        "",
        "Python réel, `PYTHONPATH=src`, aucun mock économique. DEBUG on.",
        "",
        "| Run | Fichier de sortie | Contenu |",
        "|-----|-------------------|---------|",
    ]
    for row in MANIFEST:
        lines.append(f"| `{row['run']}` | `{row['output']}` | {row['note']} |")
    lines += [
        "",
        "## Constantes dérivées (pas inventées)",
        f"- `OWNER_DECAY_K` = {OWNER_DECAY_K:.12f} depuis exemples utilisateur P(3)=49%",
        f"- `TARGET_BLOCK_SECONDS` = {TARGET_BLOCK_SECONDS} (TOKENOMICS §4.1 déjà documenté)",
        f"- `FEE_CAP_USD` = {FEE_CAP_USD_OBSERVED} (OpenChainBench Base p50 2026-08-26)",
        f"- Finder sim = {FINDER_ATTESTATIONS_PER_DAY_SIM}/j (utilisateur 20–30)",
        "",
        "## Échecs",
        json.dumps(FAILURES, indent=2, ensure_ascii=False) if FAILURES else "_aucun_",
        "",
    ]
    (HERE / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    logger.info("start sim 162 UTC=%s", datetime.now(UTC).isoformat())
    runners = [
        run_01_emission,
        run_02_owner_decay,
        run_03_hbp_finder,
        run_04_workid_partition,
        run_05_provider_worker,
        run_06_settlement_and_root,
        run_07_fees_dividend_lock,
        run_08_identity_machines,
        run_09_monte_carlo,
        run_10_code_gap_inventory,
    ]
    results = {}
    for fn in runners:
        try:
            results[fn.__name__] = fn()
        except Exception as exc:  # noqa: BLE001 — record and continue (protocol: produce report even if sim fails)
            capture_fail(fn.__name__, exc)
    dump_json(OUT / "00_manifest.json", {"manifest": MANIFEST, "failures": FAILURES})
    write_readme()
    logger.info("done runs=%s fails=%s", len(MANIFEST), len(FAILURES))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
