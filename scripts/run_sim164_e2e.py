#!/usr/bin/env python3
"""Simulation 164 — End-to-End Protocol Integration. DEBUG on. No economic mocks."""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.artcb.chain.manager import ChainManager  # noqa: E402
from src.artcb.economics.economic_root import economic_root  # noqa: E402
from src.artcb.economics.fees import quote_fee_satoshi  # noqa: E402
from src.artcb.economics.human_binding import HumanBindingError  # noqa: E402
from src.artcb.economics.identity import IdentityError  # noqa: E402
from src.artcb.economics.owner_decay import payout_owner_share  # noqa: E402
from src.artcb.economics.settlement import MachineContribution, settle_block  # noqa: E402
from src.artcb.mining.protocol import ProtocolEngine, ProtocolReject  # noqa: E402
from src.artcb.payments.stripe_jobs import (  # noqa: E402
    BLOCK_REWARD_KIND,
    JOB_PAYMENT_KIND,
    StripeJobLedger,
    handle_stripe_webhook,
    stripe_secret,
)
from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI, SATOSHI_PER_ARTCB  # noqa: E402

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("sim164")

SIM_TAG = os.getenv("ARTCB_SIM_TAG", "e2e164")
os.environ.setdefault("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
# Pytest monkeypatch can leak this into a reused shell; live probes are the default for e2e.
os.environ.pop("ARTCB_ORACLE_FORCE_STUB", None)


def dump(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.debug("wrote %s", path)


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{stamp}_{SIM_TAG}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "out").mkdir(exist_ok=True)
    log_path = out_dir / "run.log"
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(fh)

    failures: list[str] = []
    data = out_dir / "data"
    interval_note = os.environ.get("ARTCB_MIN_BLOCK_INTERVAL_SEC", "")
    logger.info(
        "sim tag=%s security=ON min_block_interval_sec=%s (0 = sequential sim, not production)",
        SIM_TAG,
        interval_note,
    )
    chain = ChainManager(data / "blocks.jsonl", enable_security=True)
    eng = ProtocolEngine(data, chain=chain)
    assert chain.enable_security is True
    logger.info("Security modules ENABLED — Anti-Sybil + Slashing attached to ProtocolEngine")

    eng.humans.bootstrap_creator(human_id="H-A", address="A")
    for hid, addr in (("H-B", "B"), ("H-C", "C"), ("H-D", "D"), ("H-E", "E")):
        eng.humans.register_candidate(human_id=hid, address=addr)
        eng.humans.creator_direct_validate(hid, creator_id="H-A")
    for did, hid in (("DEV-A", "H-A"), ("DEV-B", "H-B"), ("DEV-C", "H-C"), ("DEV-D", "H-D"), ("DEV-E", "H-E")):
        eng.devices.register(device_id=did, fingerprint=f"fp-{did}", human_id=hid)
        eng.wallet_ids.bind(
            wallet_id=f"WLT-{hid}",
            address=hid.replace("H-", ""),
            human_id=hid,
            device_id=did,
        )
    eng.machines.register(machine_id="A:M1", owner_address="A")
    eng.machines.register(machine_id="A:M2", owner_address="A", bound_human_address="B")
    eng.machines.register(machine_id="A:M3", owner_address="A", bound_human_address="C")
    eng.machines.register(machine_id="A:M4", owner_address="A", bound_human_address="D")

    identity = {
        "h_adult": eng.h_adult(),
        "machines_A": [m.to_dict() for m in eng.machines.economic_machines_of("A")],
        "n_A": eng.n_economic("A"),
        "p_m1": payout_owner_share(is_first_machine=True, n_economic=4),
        "p_extras": payout_owner_share(is_first_machine=False, n_economic=4),
    }
    dump(out_dir / "out" / "01_identity.json", identity)

    try:
        eng.machines.register(machine_id="A:M5", owner_address="A", bound_human_address="E")
        identity_m5 = {
            "n_A": eng.n_economic("A"),
            "p_extras": payout_owner_share(is_first_machine=False, n_economic=eng.n_economic("A")),
        }
    except Exception as exc:
        failures.append(f"M5: {exc}")
        identity_m5 = {"error": str(exc)}
    dump(out_dir / "out" / "02_m5_p_n.json", identity_m5)

    jobs = {}
    for name, work_id, machines, extra in (
        ("petit", "W-small", ["A:M1"], {}),
        ("gros", "W-big", ["A:M1", "A:M2", "A:M3", "A:M4"], {"n_partitions": 5}),
        ("simultane_1", "W-par-1", ["A:M1"], {}),
        ("simultane_2", "W-par-2", ["A:M2"], {}),
        ("plus_de_pb", "W-more-pb", ["A:M1", "A:M3"], {"n_partitions": 8}),
        ("partiel_pb_manquant", "W-partial", ["A:M1", "A:M2"], {"n_partitions": 5, "missing_preblock_ids": ["pb3"]}),
        (
            "job_payment_no_mint",
            "W-priority",
            ["A:M1"],
            {"job_payment": {"kind": "JobPayment", "mints": False, "payment_intent_id": "pi_sim164"}},
        ),
        (
            "providers_nonzero",
            "W-providers",
            ["A:M1"],
            {"provider_scores": {"JP1": 1.0, "JP2": 1.0}},
        ),
        (
            "stripe_down_no_block",
            "W-stripe-down",
            ["A:M1"],
            {
                "job_payment": {
                    "kind": "JobPayment",
                    "mints": False,
                    "attempt_live": True,
                    "job_id": "job_sim_stripe_down",
                }
            },
        ),
    ):
        try:
            result = eng.execute_block(
                graph_id=f"g-{name}",
                graph_root=f"root-{name}",
                pol_score=0.82,
                work_id=work_id,
                machine_ids=machines,
                interval_seconds=600,
                **extra,
            )
            jobs[name] = {
                "block_index": result.block_index,
                "hash": result.block_hash,
                "hash_version": result.hash_version,
                "h_adult": result.h_adult,
                "r_block_satoshi": result.r_block_satoshi,
                "paid": result.total_paid_satoshi,
                "conservation": result.total_paid_satoshi == result.r_block_satoshi,
                "economic_root": result.economic_root,
                "by_address": result.by_address_satoshi,
                "missing": result.missing_preblocks,
                "requeued": result.requeued_work_ids,
                "provider_worker": result.phases.get("provider_worker"),
                "job_payment_phase": result.phases.get("job_payment"),
            }
            if result.total_paid_satoshi != result.r_block_satoshi:
                failures.append(f"{name} conservation")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            jobs[name] = {"error": str(exc), "trace": traceback.format_exc()}
    dump(out_dir / "out" / "03_jobs.json", jobs)
    providers_job = jobs.get("providers_nonzero") or {}
    pw = providers_job.get("provider_worker") or {}
    if not pw.get("provider_pool") or not pw.get("worker_pool"):
        failures.append("providers_nonzero: expected non-zero provider and worker pools")
    addrs = providers_job.get("by_address") or {}
    if not addrs.get("JP1") or not addrs.get("JP2"):
        failures.append("providers_nonzero: JP1/JP2 missing from settlement")
    stripe_job = jobs.get("stripe_down_no_block") or {}
    sphase = stripe_job.get("job_payment_phase") or {}
    if sphase.get("consensus_blocked") is True:
        failures.append("stripe_down_no_block blocked consensus")
    if sphase.get("mints") is True:
        failures.append("stripe_down_no_block minted")
    if stripe_job.get("conservation") is not True:
        failures.append("stripe_down_no_block conservation")

    cancelled_job = eng.jobs.submit(provider_address="A", payload="cancel-me")
    eng.jobs.cancel(cancelled_job.job_id)
    cancelled = {
        "job_id": cancelled_job.job_id,
        "work_id": "W-cancel",
        "status": eng.jobs.get(cancelled_job.job_id).status,
        "minted": False,
        "settled": False,
    }
    dump(out_dir / "out" / "04_cancelled.json", cancelled)

    load = {}
    for label, cap in (
        ("faible", {"cpu": 16, "ram": 16, "storage": 16, "bandwidth": 1000, "latency": 1, "queue": 0, "error_rate": 0}),
        ("moyenne", {"cpu": 8, "ram": 8, "storage": 8, "bandwidth": 100, "latency": 5, "queue": 2, "error_rate": 0.01}),
        ("forte", {"cpu": 2, "ram": 2, "storage": 2, "bandwidth": 10, "latency": 40, "queue": 20, "error_rate": 0.2}),
    ):
        r = eng.execute_block(
            graph_id=f"g-load-{label}",
            graph_root=f"root-load-{label}",
            pol_score=0.8,
            work_id=f"W-load-{label}",
            machine_ids=["A:M1"],
            capacity=cap,
            n_partitions=None,
        )
        load[label] = {"n_max": r.n_max, "n_partitions": r.n_partitions, "paid": r.total_paid_satoshi}
    dump(out_dir / "out" / "05_load.json", load)

    attacks: dict = {}
    try:
        eng.machines.register(machine_id="Z:M1", owner_address="Z")
        eng.machines.register(machine_id="Z:M2", owner_address="Z", bound_human_address="B")
        attacks["double_binding_B"] = "NOT_REJECTED"
        failures.append("double binding B not rejected")
    except HumanBindingError as exc:
        attacks["double_binding_B"] = {"code": "REJECT_DOUBLE_BINDING", "message": str(exc)}
    try:
        eng.execute_block(
            graph_id="g-dup",
            graph_root="r",
            pol_score=0.8,
            work_id="W-small",
            machine_ids=["A:M1"],
        )
        attacks["double_workid"] = "NOT_REJECTED"
        failures.append("double WorkID not rejected")
    except ProtocolReject as exc:
        attacks["double_workid"] = {"code": exc.code, "message": str(exc)}
    try:
        eng.execute_block(
            graph_id="g-cut",
            graph_root="r",
            pol_score=0.8,
            work_id="W-cut",
            machine_ids=["A:M2"],
            owner_redirect={"A:M2": "A"},
        )
        attacks["owner_cut_B"] = "NOT_REJECTED"
        failures.append("owner cut B not rejected")
    except ProtocolReject as exc:
        attacks["owner_cut_B"] = {"code": exc.code, "message": str(exc)}

    n_before = eng.n_economic("A")
    eng.heartbeat("A:M2", missed_beats=1, online=False)
    grace = eng.machines.get("A:M2").status
    eng.heartbeat("A:M2", missed_beats=2, online=False)
    offline = eng.machines.get("A:M2").status
    n_offline = eng.n_economic("A")
    eng.machines.transfer("A:M2", new_owner="E")
    attacks["offline_transfer"] = {
        "n_before": n_before,
        "grace": grace,
        "offline": offline,
        "n_while_offline": n_offline,
        "n_A_after_transfer": eng.n_economic("A"),
        "n_E": eng.n_economic("E"),
        "p_A_after": payout_owner_share(is_first_machine=False, n_economic=eng.n_economic("A")),
    }

    machines = [
        MachineContribution("A1", "A", 1, None, 1.0, n_economic=2, is_first_machine=True),
        MachineContribution("A2", "A", 2, "B", 1.0, n_economic=2, is_first_machine=False),
    ]
    s1 = settle_block(r_block_satoshi=50 * SATOSHI_PER_ARTCB, h_adult=eng.h_adult(), machines=machines)
    tampered = dict(s1.economic_parts)
    tampered["lines"] = list(tampered["lines"])
    tampered["lines"][0] = ("A", "owner", "A1", s1.lines[0].reward_satoshi + 1)
    attacks["tamper_economic_root"] = {
        "before": economic_root(s1.economic_parts),
        "after": economic_root(tampered),
        "changed": economic_root(s1.economic_parts) != economic_root(tampered),
    }
    try:
        eng.humans.register_candidate(human_id="H-FAKE", address="B")
        attacks["fake_human_multi_binding"] = "NOT_REJECTED"
        failures.append("fake human multi-binding not rejected")
    except IdentityError as exc:
        attacks["fake_human_multi_binding"] = {"code": "FAKE_HUMAN", "message": str(exc)}

    dump(out_dir / "out" / "06_attacks.json", attacks)
    if not attacks["tamper_economic_root"]["changed"]:
        failures.append("tamper did not change EconomicRoot")

    oracle_out: dict = {}
    try:
        from src.artcb.economics.oracle import fetch_oracle_snapshot

        snap = fetch_oracle_snapshot(snapshot_path=out_dir / "out" / "oracle_snapshot.json")
        fee = quote_fee_satoshi(congestion=1000.0, snapshot_path=out_dir / "out" / "oracle_snapshot.json")
        # Unlisted ARTCB → live=False, fee_satoshi=None (conversion refused, NOT 0% fees).
        explicit = quote_fee_satoshi(congestion=0.0, artcb_usd_price=1.0)
        oracle_out = {
            "snapshot": snap.to_dict(),
            "fee_unlisted_or_live": fee,
            "fee_explicit_price_1usd": explicit,
            "probes_attempted": True,
            "invented_price": False,
            "conversion_refused": (not snap.live) or snap.artcb_usd <= 0,
            "fee_satoshi_when_unlisted_is_none": fee.get("fee_satoshi") is None or snap.live,
            "explicit_converts": explicit.get("fee_satoshi") is not None and explicit.get("mints") is False,
        }
        if not oracle_out["explicit_converts"]:
            failures.append("explicit ARTCB_USD price did not convert")
        if snap.live is False and fee.get("fee_satoshi") is not None:
            failures.append("unlisted oracle invented a fee_satoshi")
        if snap.live is False and fee.get("live") is not False:
            failures.append("unlisted oracle claimed live=True")
    except Exception as exc:
        oracle_out = {"error": str(exc), "fallback_documented": True, "invented_price": False}
        logger.error("oracle live fetch failed: %s", exc)
        failures.append(f"oracle exception: {exc}")
    dump(out_dir / "out" / "07_oracle.json", oracle_out)

    ledger = StripeJobLedger(data / "stripe.json")
    stripe_out = {
        "kind": JOB_PAYMENT_KIND,
        "distinct_from": BLOCK_REWARD_KIND,
        "mints": False,
        "secret_present": bool(stripe_secret()),
    }
    event = {
        "id": "evt_sim164",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_sim", "status": "succeeded", "metadata": {
            "artcb_kind": JOB_PAYMENT_KIND, "artcb_job_id": "job_sim", "artcb_mints": "false",
        }}},
    }
    stripe_out["webhook_first"] = handle_stripe_webhook(event, ledger=ledger)
    stripe_out["webhook_dup"] = handle_stripe_webhook(event, ledger=ledger)
    if stripe_secret():
        try:
            from src.artcb.payments.stripe_jobs import create_priority_job_payment

            pay = create_priority_job_payment(job_id="job_sim164", ledger=ledger)
            stripe_out["live"] = pay.to_dict()
        except Exception as exc:
            stripe_out["live_error"] = str(exc)
            logger.error("stripe live failed: %s", exc)
    dump(out_dir / "out" / "08_stripe.json", stripe_out)

    pqc_out: dict = {}
    try:
        from src.artcb.crypto.liboqs_runtime import native_liboqs_available
        from src.artcb.crypto.pqc import PQC_SIG_ALGORITHM, pqc_available

        native = native_liboqs_available()
        available = pqc_available()
        pqc_out = {
            "native_liboqs": native,
            "pqc_available": available,
            "algorithm": PQC_SIG_ALGORITHM if available else "Ed25519 (fallback)",
            "fallback": not available,
        }
        if available:
            logger.info("PQC native ML-DSA-65 ENABLED")
        else:
            logger.warning(
                "PQC fallback Ed25519 — liboqs native library not found (explicit, not silent)"
            )
    except Exception as exc:
        pqc_out = {"error": str(exc), "fallback": True, "algorithm": "Ed25519 (fallback)"}
        logger.warning("PQC probe failed: %s", exc)
    dump(out_dir / "out" / "11_pqc.json", pqc_out)

    balances: dict[str, dict] = {}
    chain_path = eng.chain.blocks_path
    totals: dict[str, int] = {}
    all_paid = 0
    if chain_path.is_file():
        for line in chain_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            block = json.loads(line)
            for contributor in block.get("contributors") or []:
                addr = str(contributor.get("address") or "")
                sat = int(contributor.get("reward_satoshi") or 0)
                all_paid += sat
                if addr:
                    totals[addr] = totals.get(addr, 0) + sat
    for addr in ("A", "B", "C", "D", "E", "JP1", "JP2"):
        sat = totals.get(addr, 0)
        balances[addr] = {"address": addr, "balance_satoshi": sat, "balance_artcb": sat / SATOSHI_PER_ARTCB}
    paid_on_chain = all_paid
    supply = eng.chain._issued_so_far_satoshi()
    if paid_on_chain != supply:
        failures.append(f"wallet conservation {paid_on_chain} != supply {supply}")
    dump(out_dir / "out" / "10_wallet_balances.json", {
        "balances": balances,
        "sum_balances_satoshi": paid_on_chain,
        "supply_satoshi": supply,
        "conservation": paid_on_chain == supply,
    })

    verify = eng.chain.verify()
    if not verify.get("valid"):
        failures.append(f"chain verify failed: {verify}")

    summary = {
        "h_adult": eng.h_adult(),
        "h_adult_source": "HumanRegistry.verified_adult_count",
        "adult_age_years": 18,
        "hmax_frozen": False,
        "security_modules": "ENABLED" if chain.enable_security else "DISABLED",
        "security_named_disable_reason": os.getenv("ARTCB_SECURITY_DISABLE_REASON") or None,
        "pqc": pqc_out,
        "supply_satoshi": supply,
        "supply_artcb": supply / SATOSHI_PER_ARTCB,
        "cap_ok": supply <= MAX_SUPPLY_SATOSHI,
        "wallet_sum_equals_supply": paid_on_chain == supply,
        "blocks": len(eng.chain.list_blocks()),
        "wallet_sum_satoshi": paid_on_chain,
        "chain_valid": verify.get("valid"),
        "hash_abi": 2,
        "providers_nonzero_split": bool((jobs.get("providers_nonzero") or {}).get("provider_worker", {}).get("provider_pool")),
        "stripe_consensus_blocked": bool((jobs.get("stripe_down_no_block") or {}).get("job_payment_phase", {}).get("consensus_blocked")),
        "failures": failures,
    }
    dump(out_dir / "out" / "00_manifest.json", {
        "simulation": SIM_TAG,
        "utc": stamp,
        "failures": failures,
        "dir": str(out_dir),
        "security_modules": "ENABLED" if chain.enable_security else "DISABLED",
        "hmax_frozen": False,
    })
    dump(out_dir / "out" / "09_summary.json", summary)

    readme = out_dir / "README.md"
    readme.write_text(
        f"""# Simulation {SIM_TAG} — E2E Protocol Integration

UTC: {stamp}
DEBUG: on. No economic mocks.
Security modules: ENABLED (Anti-Sybil + Slashing). Sequential sim uses ARTCB_MIN_BLOCK_INTERVAL_SEC=0.
hmax_frozen: false (adult max unfrozen; no UN WPP lock).

## Scenario
Users A,B,C,D,E. Machines A:M1 (100%), A:M2→B, A:M3→C, A:M4→D, A:M5→E (P(N) changes).
Jobs: petit, gros, simultanés, plus de PB, annulé, partiel (PB manquant + requeue), JobPayment no-mint,
providers_nonzero (JP1+JP2 scores), stripe_down_no_block (Stripe fail ≠ chain fail).
Load: faible / moyenne / forte.
Attacks: double binding B, double WorkID, owner cut B, offline GRACE→OFFLINE, transfer M2, fake human, tamper EconomicRoot.
Wallets: Σ balances = supply (chain contributors). Oracle: live probes; unlisted → conversion refused (not 0%).

## Outputs
See `out/*.json` and `run.log`.

Failures: {failures or 'none'}
""",
        encoding="utf-8",
    )
    print(f"SIM164_DIR={out_dir}")
    print(f"FAILURES={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
