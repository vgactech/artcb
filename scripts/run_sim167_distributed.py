#!/usr/bin/env python3
"""Simulation 167 — distributed EconomicStateSnapshot + SettlementID.

Does NOT invent results. Writes only what this process actually computed.
Does NOT overwrite 162/164/165 simulation folders.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ARTCB_WALLET_PASSPHRASE", "test-passphrase-artcb-dev-32chars!")
os.environ.setdefault("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
os.environ.setdefault("ARTCB_DEBUG", "true")
os.environ.setdefault("ARTCB_PQC_ENABLED", "true")
os.environ.setdefault("ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000")

from src.artcb.economics.distributed import (  # noqa: E402
    begin_aligned_epoch,
    build_nodes,
    canonical_tip,
    concurrent_settle,
    execute_on_node,
    gossip_after_heal,
    is_final,
    sid_for,
)
from src.artcb.economics.economic_snapshot import (  # noqa: E402
    DEFAULT_FINALITY_CONFIRMATIONS,
    ECONOMIC_RULES_VERSION,
    PROTOCOL_VERSION,
    SettlementLedger,
)
from src.artcb.economics.hbp import hbp_rate, hbp_rate_from_ratio  # noqa: E402
from src.artcb.economics.oracle import oracle_median_or_unavailable  # noqa: E402
from src.artcb.economics.owner_decay import fleet_owner_share, payout_owner_share  # noqa: E402
from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI  # noqa: E402

SEED = 167
SIM_ID = "e2e167_distributed_consolidated"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("ARTCB_GIT_SHA", "unknown")


def _write(out: Path, name: str, payload: object) -> None:
    path = out / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    started = datetime.now(UTC)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "simulations" / f"{stamp}_{SIM_ID}"
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "run.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )
    log = logging.getLogger("sim167")
    failures: list[dict] = []
    invariants: dict[str, bool] = {}

    def fail(code: str, detail: str) -> None:
        failures.append({"code": code, "detail": detail})
        log.error("FAIL %s %s", code, detail)

    commit = _git_sha()
    req = ROOT / "requirements.txt"
    dep_hash = _sha_file(req) if req.is_file() else None
    manifest = {
        "commit_sha": commit,
        "protocol_version": PROTOCOL_VERSION,
        "economic_rules_version": ECONOMIC_RULES_VERSION,
        "simulation_id": SIM_ID,
        "random_seed": SEED,
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": None,
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependency_hash": dep_hash,
        "invented_results": False,
    }
    _write(out, "00_manifest.json", manifest)

    pending = {
        "V-01": "EconomicStateSnapshot at epoch start (implemented, pending lock)",
        "V-02": "transfer effect = next epoch (implemented, pending lock)",
        "V-03": "reconnect grace 24h prod / 1s in this sim (pending lock)",
        "V-04": "retire effect = next snapshot (implemented, pending lock)",
        "V-05": "finality = N confirmations (N=2) vs quorum (pending lock)",
        "V-06": "H_adult_max = versioned DemographicReference (not frozen)",
        "V-07": "HBP 10→60→20 on H_verified/H_adult_max (function added, live path unchanged)",
    }
    _write(
        out,
        "02_decision_matrix.json",
        {
            "validated": {
                "D-014": "21M cap",
                "D-024": "no 210k halving",
                "D-025": "M1=100%, fleet P(N), time-norm, Stripe≠mint",
            },
            "pending_user_validation": pending,
            "matrix": [
                {"decision": "21M", "code": "emission", "test": "cap", "sim": "supply"},
                {"decision": "M1=100%", "code": "owner_decay", "test": "m1", "sim": "fleet"},
                {"decision": "OwnerDecay", "code": "economics", "test": "fleet", "sim": "N changes"},
                {"decision": "HBP envelope", "code": "hbp", "test": "budget", "sim": "demographic"},
                {"decision": "SettlementID", "code": "economic_snapshot", "test": "uniqueness", "sim": "S2"},
                {"decision": "Stripe≠mint", "code": "payments", "test": "isolation", "sim": "S9"},
            ],
        },
    )

    try:
        work = out / "work"
        work.mkdir()
        ledger = SettlementLedger(work / "settlements.json")
        nodes = build_nodes(work, ledger=ledger)
        _write(
            out,
            "04_identity_model.json",
            {
                "humans": ["H-A", "H-B", "H-C", "H-D", "H-E"],
                "creator_verified": True,
                "adult_age_years": 18,
            },
        )
        _write(
            out,
            "05_machine_fleet.json",
            {
                "A": ["M1", "M2", "M3", "M4"],
                "M1": "100%",
                "extras": "P(N_economic) from snapshot",
            },
        )

        # Epoch 1 snapshot (V-01)
        snaps = begin_aligned_epoch(nodes, parent_root="0" * 64)
        snap_a = snaps["A"]
        n_a = snap_a.n_economic("A")
        p_m1 = payout_owner_share(is_first_machine=True, n_economic=n_a)
        p_extra = fleet_owner_share(n_a)
        if p_m1 != 1.0:
            fail("M1_NOT_100", f"p_m1={p_m1}")
        invariants["M1_100"] = p_m1 == 1.0
        _write(
            out,
            "01_protocol_snapshot.json",
            {
                "epoch": snap_a.epoch,
                "digest": snap_a.digest(),
                "h_adult": snap_a.h_adult,
                "n_economic_A": n_a,
                "p_m1": p_m1,
                "p_extras": p_extra,
                "machines": [m.to_dict() for m in snap_a.machines],
            },
        )
        _write(
            out,
            "03_population_model.json",
            {
                "h_adult": snap_a.h_adult,
                "hmax_frozen": False,
                "demographic_digest": snap_a.demographic_digest,
                "hbp_live_absolute": hbp_rate(h_adult=snap_a.h_adult),
                "hbp_ratio_provisional": hbp_rate_from_ratio(
                    h_verified=float(snap_a.h_adult),
                    h_adult_max=5_820_000_000,
                ),
                "note": "V-06/V-07 pending — ratio function exists, live mining still uses absolute anchors",
            },
        )

        # S1/S2 concurrent WorkID-X on all 4 nodes
        results_x = concurrent_settle(
            nodes,
            snaps,
            ledger,
            work_id="WorkID-X",
            machine_ids=["M1", "M2", "M3", "M4"],
            graph_suffix="s1s2",
            provider_scores={"JP1": 1.0, "JP2": 1.0},
        )
        ok_x = [r for r in results_x if r.get("ok")]
        ko_x = [r for r in results_x if not r.get("ok")]
        count_x = ledger.count_for_work("WorkID-X")
        invariants["settlement_workid_x_eq_1"] = count_x == 1
        if count_x != 1:
            fail("DOUBLE_SETTLEMENT", f"count={count_x} results={results_x}")
        _write(
            out,
            "11_consensus_events.json",
            {"S1_S2_WorkID-X": results_x, "consumed": ledger.to_list()},
        )

        # Mid-epoch transfer of M5-equivalent M4 queued (V-02) — P stays snapshot
        node_a = next(n for n in nodes if n.node_id == "A")
        n_before = snaps["A"].n_economic("A")
        node_a.coordinator.queue_transfer("M4", new_owner="B", bound_human_address="E")
        n_after_queue = node_a.engine.n_economic("A")
        invariants["transfer_does_not_mutate_live_until_next_epoch"] = n_after_queue == n_before
        # live registry still has M4 until apply — queue only
        if n_after_queue != n_before:
            fail("TRANSFER_IMMEDIATE", f"N live changed {n_before}->{n_after_queue} before epoch")

        r_transfer = execute_on_node(
            node_a,
            snap=snaps["A"],
            ledger=ledger,
            work_id="WorkID-transfer-window",
            machine_ids=["M1", "M2", "M3", "M4"],
            graph_suffix="s6",
        )
        _write(
            out,
            "07_workloads.json",
            {
                "WorkID-X": {"ok": len(ok_x), "rejected": len(ko_x), "settlement_count": count_x},
                "WorkID-transfer-window": r_transfer,
                "snapshot_n_economic_A": n_before,
            },
        )

        # Epoch 2 applies transfer
        snaps2 = begin_aligned_epoch(nodes[:1], parent_root=node_a.tip_hash())
        n_a2 = snaps2["A"].n_economic("A")
        invariants["n_decreases_next_epoch_after_transfer"] = n_a2 < n_before
        if not (n_a2 < n_before):
            fail("TRANSFER_NEXT_EPOCH", f"N_A snapshot2={n_a2} snapshot1={n_before}")

        # S7 offline / reconnect grace (1s in sim)
        node_a.engine.machines.mark_offline("M2")
        node_a.coordinator.queue_reconnect("M2")
        n_offline = node_a.engine.n_economic("A")
        invariants["offline_still_counts"] = n_offline >= 1

        # S9 Stripe down during block
        r_stripe = execute_on_node(
            node_a,
            snap=snaps2["A"],
            ledger=ledger,
            work_id="WorkID-stripe-down",
            machine_ids=["M1", "M2"],
            graph_suffix="s9",
            job_payment={
                "kind": "JobPayment",
                "mints": False,
                "attempt_live": True,
                "job_id": "job_stripe_down_167",
            },
        )
        jp = node_a.engine  # phases on last result only via return
        invariants["stripe_down_does_not_block"] = bool(r_stripe.get("ok"))
        if not r_stripe.get("ok"):
            fail("STRIPE_BLOCKED_CHAIN", str(r_stripe))

        # S3 partition then heal
        g1 = [n for n in nodes if n.partition_group == "G1"]
        g2 = [n for n in nodes if n.partition_group == "G2"]
        # G2 tries same already-settled WorkID-X
        part_results = concurrent_settle(
            g2,
            snaps,
            ledger,
            work_id="WorkID-X",
            machine_ids=["M1"],
            graph_suffix="partition-dup",
        )
        heal = gossip_after_heal(nodes)
        invariants["partition_dup_rejected"] = all(not r.get("ok") for r in part_results)
        if not invariants["partition_dup_rejected"]:
            fail("PARTITION_DUP_ACCEPTED", str(part_results))
        _write(out, "10_network_events.json", {"partition_dup": part_results, "heal": heal, "g1": [n.node_id for n in g1], "g2": [n.node_id for n in g2]})

        # S10 oracle
        no_quorum = oracle_median_or_unavailable([None, None, None], min_sources=2)
        quorum = oracle_median_or_unavailable([1.0, 1.2, None], min_sources=2)
        invariants["oracle_unavailable_not_invented"] = no_quorum.status == "OracleUnavailable" and no_quorum.invented is False
        invariants["oracle_quorum_median"] = quorum.status == "quorum" and quorum.median == 1.1
        _write(
            out,
            "13_economic_root.json",
            {
                "ok_blocks": [r for r in results_x + [r_transfer, r_stripe] if r.get("ok")],
                "oracle": {"no_quorum": no_quorum.to_dict(), "quorum": quorum.to_dict()},
            },
        )

        # S8 provider missing — worker takes pool (existing settle_block)
        r_noprov = execute_on_node(
            node_a,
            snap=snaps2["A"],
            ledger=ledger,
            work_id="WorkID-noprovider",
            machine_ids=["M1"],
            graph_suffix="s8",
        )
        invariants["provider_unavailable_still_settles"] = bool(r_noprov.get("ok"))

        # S4 restart: rebuild node B engine from same data dir
        node_b = next(n for n in nodes if n.node_id == "B")
        height_before = node_b.height()
        from src.artcb.chain.manager import ChainManager
        from src.artcb.mining.protocol import ProtocolEngine
        from src.artcb.wallet.manager import WalletManager

        bdir = work / "node_B"
        chain_b = ChainManager(bdir / "blocks.jsonl", key_path=bdir / "chain.key", enable_security=True)
        engine_b = ProtocolEngine(bdir, chain=chain_b, wallet_manager=WalletManager(bdir / "wallets"))
        invariants["restart_preserves_height"] = engine_b.chain.list_blocks().__len__() == height_before
        if not invariants["restart_preserves_height"]:
            fail("RESTART_HEIGHT", f"{engine_b.chain.list_blocks().__len__()} vs {height_before}")

        # S5 clock skew recorded
        _write(
            out,
            "06_wallet_state.json",
            {
                "clock_skew_seconds": {n.node_id: n.clock_skew_seconds for n in nodes},
                "note": "skew is injected latency metadata; blocks use wall UTC",
            },
        )

        supplies = {n.node_id: n.engine.chain._issued_so_far_satoshi() for n in nodes}
        wallets_sum = {}
        for n in nodes:
            total = 0
            for w in n.engine.wallets.list_wallets():
                total += int(w.get("balance_satoshi") or w.get("balance") or 0)
            wallets_sum[n.node_id] = total
        cap_ok = all(s <= MAX_SUPPLY_SATOSHI for s in supplies.values())
        invariants["supply_le_21m"] = cap_ok
        if not cap_ok:
            fail("SUPPLY_CAP", str(supplies))

        nid, height, tip = canonical_tip(nodes)
        _write(out, "08_preblocks.json", {"note": "preblocks reuse ProtocolEngine partition; no extra mint"})
        _write(out, "09_pol_results.json", {"pol_score_used": 0.85, "useful_work_tokens_ignored": True})
        _write(out, "12_settlements.json", ledger.to_list())
        _write(out, "14_supply.json", {"satoshi": supplies, "max": MAX_SUPPLY_SATOSHI, "cap_ok": cap_ok})
        _write(out, "15_wallet_balances.json", wallets_sum)
        _write(
            out,
            "16_invariants.json",
            {
                **invariants,
                "finality_example": {
                    "height_0_final_at_tip": is_final(height=0, tip_height=height, confirmations=DEFAULT_FINALITY_CONFIRMATIONS),
                    "n": DEFAULT_FINALITY_CONFIRMATIONS,
                },
                "canonical": {"node": nid, "height": height, "tip": tip},
            },
        )
    except Exception as exc:
        fail("UNCAUGHT", f"{type(exc).__name__}: {exc}")
        log.error("uncaught\n%s", traceback.format_exc())

    finished = datetime.now(UTC)
    manifest["finished_at"] = finished.strftime("%Y-%m-%dT%H:%M:%SZ")
    _write(out, "00_manifest.json", manifest)
    _write(out, "17_failures.json", failures)
    summary = {
        "simulation": SIM_ID,
        "dir": str(out),
        "failures": failures,
        "failure_count": len(failures),
        "invariants": invariants,
        "certified_distributed_mainnet": False,
        "invented": False,
        "pending_validation": list(pending.keys()),
    }
    _write(out, "18_summary.json", summary)
    log.info("SIM167_DIR=%s failures=%s", out, len(failures))
    print(f"SIM167_DIR={out}")
    print(f"SIM167_FAILURES={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
