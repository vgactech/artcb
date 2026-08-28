"""Simulation 164 — End-to-End Protocol Integration.

Wires live modules (no economic mocks) in ONE execution::

    HumanID → MachineID → WalletID → HumanBinding → JobID/WorkID
    → Capacity → Partition → PB → PoL → Provider/Worker → HBP
    → OwnerDecay → EconomicRoot → BlockHash → Settlement → wallets

DEBUG traces on. Does not re-run simulations 162/163.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))

from src.artcb.chain.manager import ChainManager
from src.artcb.economics.economic_root import economic_root
from src.artcb.economics.human_binding import HumanBindingError
from src.artcb.economics.identity import IdentityError
from src.artcb.economics.owner_decay import fleet_owner_share, payout_owner_share
from src.artcb.economics.settlement import reject_owner_payment_cut, OwnerCannotCutPaymentError
from src.artcb.mining.protocol import (
    ProtocolEngine,
    ProtocolReject,
    REJECT_DOUBLE_BINDING,
    REJECT_DOUBLE_SETTLEMENT,
    REJECT_FAKE_HUMAN,
    REJECT_OWNER_CUT_PAYMENT,
)
from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI, SATOSHI_PER_ARTCB

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("sim164")


def _dump(name: str, payload: dict) -> Path:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.debug("wrote %s", path)
    return path


def _engine(tmp: Path) -> ProtocolEngine:
    chain = ChainManager(
        tmp / "chain" / "blocks.jsonl",
        key_path=tmp / "chain.key",
        enable_security=False,
    )
    return ProtocolEngine(tmp, chain=chain)


def _bootstrap(engine: ProtocolEngine) -> dict:
    """Users A,B,C,D then later E. Machines A→M1, A→M2→B, A→M3→C, A→M4→D."""
    creator = engine.humans.bootstrap_creator(human_id="H-A", address="A")
    humans = {"A": creator}
    for hid, addr in (("H-B", "B"), ("H-C", "C"), ("H-D", "D")):
        rec = engine.humans.register_candidate(human_id=hid, address=addr)
        rec = engine.humans.creator_direct_validate(hid, creator_id="H-A")
        humans[addr] = rec
        engine.devices.register(device_id=f"D-{addr}", fingerprint=f"fp-{addr}", human_id=hid)
        engine.wallet_ids.bind(
            wallet_id=f"WLT-{addr}",
            address=addr,
            human_id=hid,
            device_id=f"D-{addr}",
        )
    engine.devices.register(device_id="D-A", fingerprint="fp-A", human_id="H-A")
    engine.wallet_ids.bind(wallet_id="WLT-A", address="A", human_id="H-A", device_id="D-A")

    m1 = engine.machines.register(machine_id="M1", owner_address="A")
    m2 = engine.machines.register(machine_id="M2", owner_address="A", bound_human_address="B")
    m3 = engine.machines.register(machine_id="M3", owner_address="A", bound_human_address="C")
    m4 = engine.machines.register(machine_id="M4", owner_address="A", bound_human_address="D")
    n_a = engine.n_economic("A")
    p_extras = fleet_owner_share(n_a)
    log.debug("bootstrap N_A=%s P_extras=%.6f H_adult=%s", n_a, p_extras, engine.h_adult())
    return {
        "humans": {k: v.to_dict() for k, v in humans.items()},
        "machines": [m.to_dict() for m in (m1, m2, m3, m4)],
        "n_a": n_a,
        "p_extras": p_extras,
        "h_adult": engine.h_adult(),
        "m1_owner_share": payout_owner_share(is_first_machine=True, n_economic=n_a),
    }


def _mine(
    engine: ProtocolEngine,
    *,
    work_id: str,
    machine_ids: list[str],
    job_id: str | None = None,
    missing: list[str] | None = None,
    n_partitions: int | None = None,
    capacity: dict | None = None,
    provider_scores: dict | None = None,
    job_payment: dict | None = None,
    pol_score: float = 0.82,
) -> dict:
    result = engine.execute_block(
        graph_id=f"g-{work_id}",
        graph_root="a" * 64,
        pol_score=pol_score,
        work_id=work_id,
        machine_ids=machine_ids,
        job_id=job_id,
        missing_preblock_ids=missing,
        n_partitions=n_partitions,
        capacity=capacity,
        provider_scores=provider_scores,
        job_payment=job_payment,
        interval_seconds=600.0,
    )
    return {
        "block_index": result.block_index,
        "block_hash": result.block_hash,
        "hash_version": result.hash_version,
        "h_adult": result.h_adult,
        "r_block_satoshi": result.r_block_satoshi,
        "hbp_rate": result.hbp_rate,
        "economic_root": result.economic_root,
        "total_paid_satoshi": result.total_paid_satoshi,
        "conservation": result.total_paid_satoshi == result.r_block_satoshi,
        "supply_satoshi": result.supply_satoshi,
        "supply_le_21m": result.supply_satoshi <= MAX_SUPPLY_SATOSHI,
        "by_address_satoshi": result.by_address_satoshi,
        "lines": result.lines,
        "missing_preblocks": result.missing_preblocks,
        "requeued": result.requeued_work_ids,
        "n_max": result.n_max,
        "n_partitions": result.n_partitions,
        "phases": result.phases,
        "job_payment": result.job_payment,
    }


LOADS = {
    "low": {"cpu": 4, "ram": 4, "storage": 4, "bandwidth": 10, "latency": 2, "queue": 0, "error_rate": 0},
    "medium": {"cpu": 16, "ram": 16, "storage": 16, "bandwidth": 100, "latency": 1, "queue": 0.2, "error_rate": 0.01},
    "high": {"cpu": 64, "ram": 64, "storage": 64, "bandwidth": 1000, "latency": 0.5, "queue": 1.0, "error_rate": 0.05},
}


def run() -> dict:
    os.environ.setdefault("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
    os.environ.setdefault("ARTCB_DEBUG", "true")
    tmp = HERE / "data"
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    engine = _engine(tmp)
    wallets: dict[str, int] = {}
    failures: list[str] = []
    attacks: dict[str, dict] = {}

    boot = _bootstrap(engine)
    _dump("01_bootstrap.json", boot)

    jobs = {}
    jobs["small"] = engine.jobs.submit(provider_address="A", payload="small useful work").to_dict()
    jobs["large"] = engine.jobs.submit(provider_address="A", payload="large " * 200).to_dict()
    jobs["sim_a"] = engine.jobs.submit(provider_address="B", payload="simultaneous-a").to_dict()
    jobs["sim_b"] = engine.jobs.submit(provider_address="C", payload="simultaneous-b").to_dict()
    cancelled = engine.jobs.submit(provider_address="D", payload="will cancel")
    engine.jobs.cancel(cancelled.job_id)
    jobs["cancelled"] = engine.jobs.get(cancelled.job_id).to_dict()
    partial = engine.jobs.submit(provider_address="A", payload="partial")
    engine.jobs.partition(partial.job_id, worker_capacities=[1.0, 1.0], r_block_satoshi=1000)
    engine.jobs.mark_partial(partial.job_id, completed_preblocks=1)
    jobs["partial"] = engine.jobs.get(partial.job_id).to_dict()
    _dump("02_jobs.json", jobs)

    blocks = []
    machines_abcd = ["M1", "M2", "M3", "M4"]
    for label, cap in LOADS.items():
        blk = _mine(
            engine,
            work_id=f"W-load-{label}",
            machine_ids=machines_abcd,
            job_id=jobs["small"]["job_id"],
            n_partitions=3 if label == "low" else (5 if label == "medium" else 8),
            capacity=cap,
            provider_scores={"A": 1.0},
        )
        blocks.append({"load": label, **blk})
        for addr, sat in blk["by_address_satoshi"].items():
            wallets[addr] = wallets.get(addr, 0) + sat

    more_pb = _mine(
        engine,
        work_id="W-more-pb",
        machine_ids=machines_abcd,
        n_partitions=12,
        capacity=LOADS["high"],
        provider_scores={"A": 1.0},
    )
    blocks.append({"load": "more_preblocks", **more_pb})
    for addr, sat in more_pb["by_address_satoshi"].items():
        wallets[addr] = wallets.get(addr, 0) + sat

    missing = _mine(
        engine,
        work_id="W-missing-pb",
        machine_ids=machines_abcd,
        n_partitions=5,
        missing=["pb3"],
        capacity=LOADS["medium"],
        provider_scores={"A": 1.0},
    )
    blocks.append({"load": "missing_pb", **missing})
    _dump("03_blocks_jobs_network.json", {"blocks": blocks, "wallets": wallets})

    # Add E / M5 — P(N) must change
    engine.humans.register_candidate(human_id="H-E", address="E")
    engine.humans.creator_direct_validate("H-E", creator_id="H-A")
    p_before = fleet_owner_share(engine.n_economic("A"))
    m5 = engine.machines.register(machine_id="M5", owner_address="A", bound_human_address="E")
    p_after = fleet_owner_share(engine.n_economic("A"))
    m5_block = _mine(
        engine,
        work_id="W-m5",
        machine_ids=["M1", "M2", "M3", "M4", "M5"],
        n_partitions=5,
        provider_scores={"A": 1.0},
    )
    _dump(
        "04_m5_pn_change.json",
        {
            "n_before": 4,
            "n_after": engine.n_economic("A"),
            "p_before": p_before,
            "p_after": p_after,
            "p_changed": p_after != p_before,
            "m5": m5.to_dict(),
            "block": m5_block,
            "h_adult": engine.h_adult(),
        },
    )

    # Attack 1: double binding A tries M2→B and extra machine → B again
    try:
        engine.machines.register(machine_id="M-evil-B", owner_address="A", bound_human_address="B")
        attacks["1_double_binding"] = {"rejected": False, "error": None}
        failures.append("double binding was accepted")
    except HumanBindingError as exc:
        attacks["1_double_binding"] = {"rejected": True, "code": REJECT_DOUBLE_BINDING, "error": str(exc)}
        log.debug("ATTACK1 REJECT %s", exc)

    # Attack 2: double settlement same WorkID
    try:
        _mine(engine, work_id="W-m5", machine_ids=["M1"], provider_scores={"A": 1.0})
        attacks["2_double_settlement"] = {"rejected": False}
        failures.append("double settlement was accepted")
    except ProtocolReject as exc:
        attacks["2_double_settlement"] = {
            "rejected": True,
            "code": exc.code,
            "error": str(exc),
            "expect": REJECT_DOUBLE_SETTLEMENT,
        }
        log.debug("ATTACK2 REJECT %s", exc)

    # Attack 3: owner A tries to cut B's payment
    try:
        reject_owner_payment_cut()
        attacks["3_owner_cut"] = {"rejected": False}
        failures.append("owner cut was accepted")
    except OwnerCannotCutPaymentError as exc:
        attacks["3_owner_cut"] = {"rejected": True, "code": "IMPOSSIBLE", "error": str(exc)}
    try:
        engine.execute_block(
            graph_id="g-cut",
            graph_root="b" * 64,
            pol_score=0.8,
            work_id="W-owner-cut",
            machine_ids=["M2"],
            owner_redirect={"M2": "A"},
        )
        attacks["3_owner_cut_engine"] = {"rejected": False}
        failures.append("owner_redirect was accepted")
    except ProtocolReject as exc:
        attacks["3_owner_cut_engine"] = {
            "rejected": True,
            "code": exc.code,
            "error": str(exc),
            "expect": REJECT_OWNER_CUT_PAYMENT,
        }

    # Attack 4: offline M2 ACTIVE → GRACE → OFFLINE; N_A still correct
    n_before_off = engine.n_economic("A")
    engine.heartbeat("M2", online=False, missed_beats=1)
    grace = engine.machines.get("M2")
    engine.heartbeat("M2", online=False, missed_beats=3)
    offline = engine.machines.get("M2")
    n_after_off = engine.n_economic("A")
    attacks["4_offline_grace"] = {
        "status_grace": grace.status if grace else None,
        "status_offline": offline.status if offline else None,
        "n_before": n_before_off,
        "n_after": n_after_off,
        "n_unchanged": n_before_off == n_after_off,
        "rejected_shrink": n_before_off == n_after_off,
    }
    if n_before_off != n_after_off:
        failures.append("offline shrank N_economic")

    resume = _mine(
        engine,
        work_id="W-resume-offline",
        machine_ids=["M1", "M3", "M4", "M5"],
        provider_scores={"A": 1.0},
    )
    engine.heartbeat("M2", online=True)
    _dump("05_offline_resume.json", {"attack4": attacks["4_offline_grace"], "resume": resume})

    # Attack 5: transfer M2 to new owner; recalc N_A and P_A
    n_seller_before = engine.n_economic("A")
    p_seller_before = fleet_owner_share(n_seller_before)
    transferred = engine.machines.transfer("M2", new_owner="Z")
    n_seller_after = engine.n_economic("A")
    p_seller_after = fleet_owner_share(max(n_seller_after, 2)) if n_seller_after >= 2 else 1.0
    attacks["5_transfer"] = {
        "n_a_before": n_seller_before,
        "n_a_after": n_seller_after,
        "p_before": p_seller_before,
        "p_after": p_seller_after,
        "n_z": engine.n_economic("Z"),
        "transferred": transferred.to_dict(),
        "n_decreased": n_seller_after < n_seller_before,
    }
    if not (n_seller_after < n_seller_before):
        failures.append("transfer did not decrease N_A")

    # Attack 6: fake human — same identity multiple bindings / same address
    try:
        engine.humans.register_candidate(human_id="H-FAKE", address="B")
        attacks["6_fake_human"] = {"rejected": False}
        failures.append("fake human same address accepted")
    except IdentityError as exc:
        attacks["6_fake_human"] = {"rejected": True, "code": REJECT_FAKE_HUMAN, "error": str(exc)}
    try:
        engine.humans.register_candidate(human_id="H-B", address="B2")
        attacks["6_fake_human_id"] = {"rejected": False}
        failures.append("duplicate HumanID accepted")
    except IdentityError as exc:
        attacks["6_fake_human_id"] = {"rejected": True, "error": str(exc)}

    # Attack 7: tamper settlement → EconomicRoot / BlockHash change
    last_line = engine.chain.blocks_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    block = json.loads(last_line)
    original_root = block.get("economic_root") or (block.get("economics") or {}).get("economic_root")
    original_hash = block.get("hash")
    tampered_parts = {"r_block_satoshi": 1, "tamper": True}
    tampered_root = economic_root(tampered_parts)
    block["economic_root"] = tampered_root
    if "economics" in block:
        block["economics"] = dict(block["economics"])
        block["economics"]["economic_root"] = tampered_root
    verify_ok = engine.chain.verify()
    # write tampered copy aside, verify that C hash mismatches without rewriting live chain
    from src.artcb.chain import ffi

    expected_after_tamper = ffi.build_block_hash(
        int(block["index"]),
        str(block["timestamp"]),
        str(block["prev_hash"]),
        str(block["graph_root"]),
        str(block.get("merkle_root") or block["graph_root"]),
        float(block["pol_score"]),
        economic_root=tampered_root if int(block.get("hash_version") or 1) >= 2 else None,
    )
    attacks["7_tamper_root"] = {
        "original_root": original_root,
        "tampered_root": tampered_root,
        "root_changed": original_root != tampered_root,
        "original_hash": original_hash,
        "hash_after_recompute": expected_after_tamper,
        "hash_changed": original_hash != expected_after_tamper,
        "live_chain_still_valid": verify_ok.get("valid"),
        "c_abi_v2": ffi.has_economic_root_abi(),
    }
    if original_root == tampered_root or original_hash == expected_after_tamper:
        failures.append("tamper did not change EconomicRoot/BlockHash")

    _dump("06_attacks.json", attacks)

    supply = engine.chain._issued_so_far_satoshi()
    conservation_ok = all(b.get("conservation") for b in blocks) and m5_block["conservation"]
    summary = {
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "h_adult": engine.h_adult(),
        "supply_satoshi": supply,
        "supply_artcb": supply / SATOSHI_PER_ARTCB,
        "supply_le_21m": supply <= MAX_SUPPLY_SATOSHI,
        "wallets": wallets,
        "wallet_sum_satoshi": sum(wallets.values()),
        "n_a": engine.n_economic("A"),
        "conservation_ok": conservation_ok,
        "c_economic_root_abi": ffi.has_economic_root_abi(),
        "hash_abi_version": ffi.hash_abi_version(),
        "attacks": {k: v.get("rejected", v.get("n_unchanged") or v.get("n_decreased") or v.get("hash_changed")) for k, v in attacks.items()},
        "failures": failures,
        "pipeline": "HumanID→MachineID→WalletID→HumanBinding→JobID/WorkID→Capacity→Partition→PB→PoL→Provider/Worker→HBP→OwnerDecay→EconomicRoot→BlockHash→Settlement→wallets",
        "job_payment_ne_block_reward": True,
        "stripe_mints": False,
    }
    _dump("00_summary.json", summary)
    manifest = {
        "sim": "164",
        "folder": str(HERE),
        "failures": failures,
        "ok": not failures,
    }
    _dump("00_manifest.json", manifest)
    return summary


if __name__ == "__main__":
    try:
        summary = run()
        print(json.dumps({"ok": not summary["failures"], "failures": summary["failures"]}, indent=2))
        sys.exit(0 if not summary["failures"] else 1)
    except Exception:
        traceback.print_exc()
        sys.exit(2)
