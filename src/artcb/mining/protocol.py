"""End-to-end protocol execution — one path, no orphan modules.

Order per block (D-025)::

    H_adult → R(H)×dt/T → HBP → Worker → Provider → OwnerDecay → Settlement
    EconomicRoot (native C v2) → BlockHash
    Σ payments = R_block ; Supply ≤ 21M
    JobPayment (Stripe) ≠ R_block and never mints.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.artcb.economics.audit_log import AuditLog
from src.artcb.economics.demographic import default_provisional_reference
from src.artcb.economics.dividend import UniversalDividendVault
from src.artcb.economics.economic_root import HASH_VERSION_V2, economic_root
from src.artcb.economics.emission import issued_reward_satoshi
from src.artcb.economics.human_binding import HumanBindingError, MachineRegistry
from src.artcb.economics.identity import (
    DeviceRegistry,
    HumanRegistry,
    IdentityError,
    WalletIdRegistry,
)
from src.artcb.economics.job_provider import JobProvider, JobProviderError
from src.artcb.economics.network_capacity import n_max_from_capacity
from src.artcb.economics.partition_map import assign_partitions
from src.artcb.economics.preblocks import partition_block_reward
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.economics.workid import WorkIDError, WorkRegistry, WorkStatus
from src.artcb.tokenomics import MAX_SUPPLY_SATOSHI, TARGET_BLOCK_SECONDS
from src.artcb.wallet.manager import WalletManager

logger = logging.getLogger("artcb.mining.protocol")

REJECT_DOUBLE_BINDING = "REJECT_DOUBLE_BINDING"
REJECT_DOUBLE_SETTLEMENT = "REJECT_DOUBLE_SETTLEMENT"
REJECT_OWNER_CUT_PAYMENT = "REJECT_OWNER_CUT_PAYMENT"
REJECT_FAKE_HUMAN = "REJECT_FAKE_HUMAN"
REJECT_UNKNOWN_MACHINE = "REJECT_UNKNOWN_MACHINE"
REJECT_WORK_ID = "REJECT_WORK_ID"


class ProtocolReject(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass
class ProtocolBlockResult:
    block_index: int
    block_hash: str
    hash_version: int
    h_adult: int
    r_block_satoshi: int
    hbp_rate: float
    economic_root: str
    total_paid_satoshi: int
    supply_satoshi: int
    work_id: str
    job_id: str | None
    missing_preblocks: list[str]
    requeued_work_ids: list[str]
    by_address_satoshi: dict[str, int]
    lines: list[dict]
    n_max: int
    n_partitions: int
    job_payment: dict | None = None
    phases: dict[str, Any] = field(default_factory=dict)


class ProtocolEngine:
    """Wires HumanID/DeviceID/WalletID/MachineID/WorkID/PB/PoL/HBP/settlement."""

    def __init__(
        self,
        data_dir: Path,
        *,
        chain,
        wallet_manager: WalletManager | None = None,
        machine_registry: MachineRegistry | None = None,
        job_provider: JobProvider | None = None,
        human_registry: HumanRegistry | None = None,
        work_registry: WorkRegistry | None = None,
        device_registry: DeviceRegistry | None = None,
        wallet_id_registry: WalletIdRegistry | None = None,
    ) -> None:
        eco = Path(data_dir) / "economics"
        eco.mkdir(parents=True, exist_ok=True)
        self.data_dir = Path(data_dir)
        self.chain = chain
        self.wallets = wallet_manager or WalletManager()
        self.humans = human_registry or HumanRegistry(eco / "humans.json")
        self.devices = device_registry or DeviceRegistry(eco / "devices.json")
        self.wallet_ids = wallet_id_registry or WalletIdRegistry(eco / "wallet_ids.json")
        self.machines = machine_registry or MachineRegistry(eco / "machines.json")
        self.works = work_registry or WorkRegistry(eco / "works.json")
        self.jobs = job_provider or JobProvider(eco / "jobs.json")
        self.audit = AuditLog(eco / "audit.bin")
        self.vault = UniversalDividendVault(eco / "dividend_vault.json")
        self.demographic = default_provisional_reference()
        if not getattr(chain, "enable_security", False):
            reason = os.getenv("ARTCB_SECURITY_DISABLE_REASON", "").strip()
            if not reason:
                raise RuntimeError(
                    "ProtocolEngine requires ChainManager(enable_security=True). "
                    "Silent disable is forbidden. Set ARTCB_SECURITY_DISABLE_REASON "
                    "only when a named dependency is missing."
                )
            logger.error("Security modules DISABLED named_reason=%s", reason)
        else:
            logger.info("Security modules ENABLED (Anti-Sybil + Slashing)")
        self.chain.bind_identity(
            human_registry=self.humans,
            machine_registry=self.machines,
            work_registry=self.works,
        )

    def h_adult(self) -> int:
        """Live counter = verified adults 18+ in the identity registry."""
        count = self.humans.verified_adult_count()
        logger.debug("H_adult live=%s source=HumanRegistry.adult_verified", count)
        return count

    def n_economic(self, owner_address: str) -> int:
        return self.machines.economic_count(owner_address)

    def heartbeat(self, machine_id: str, *, missed_beats: int = 0, online: bool = True):
        if online:
            return self.machines.mark_active(machine_id)
        if missed_beats <= 1:
            return self.machines.mark_grace(machine_id)
        return self.machines.mark_offline(machine_id)

    def execute_block(
        self,
        *,
        graph_id: str,
        graph_root: str,
        pol_score: float,
        work_id: str,
        machine_ids: list[str],
        work_weights: dict[str, float] | None = None,
        job_id: str | None = None,
        provider_scores: dict[str, float] | None = None,
        hbp_scores: dict[str, float] | None = None,
        missing_preblock_ids: list[str] | None = None,
        interval_seconds: float | None = None,
        n_partitions: int | None = None,
        capacity: dict[str, float] | None = None,
        owner_redirect: dict[str, str] | None = None,
        visibility: str = "private",
        job_payment: dict | None = None,
        epoch_snapshot=None,
        settlement_ledger=None,
        node_id: str = "local",
    ) -> ProtocolBlockResult:
        phases: dict[str, Any] = {}

        if job_payment is not None:
            if job_payment.get("mints") is True:
                raise ProtocolReject("REJECT_STRIPE_MINT", "JobPayment must never mint R_block")
            if job_payment.get("kind") not in {"JobPayment", "priority_job"}:
                raise ProtocolReject("REJECT_JOB_PAYMENT_KIND", "expected JobPayment kind")
            from src.artcb.payments.stripe_jobs import (
                BLOCK_REWARD_KIND,
                JOB_PAYMENT_KIND,
                attempt_job_payment_or_continue,
            )

            phases["job_payment"] = {
                "kind": JOB_PAYMENT_KIND,
                "mints": False,
                "distinct_from": BLOCK_REWARD_KIND,
                "payment_intent_id": job_payment.get("payment_intent_id"),
                "consensus_blocked": False,
                "stripe_is_consensus_dependency": False,
            }
            if job_payment.get("attempt_live"):
                live = attempt_job_payment_or_continue(
                    job_id=str(job_payment.get("job_id") or job_id or work_id),
                )
                phases["job_payment"].update(live)
                logger.debug(
                    "stripe attempt_live ok=%s consensus_blocked=%s",
                    live.get("ok"),
                    live.get("consensus_blocked"),
                )

        machines_recs = []
        for mid in machine_ids:
            rec = self.machines.get(mid)
            if rec is None:
                raise ProtocolReject(REJECT_UNKNOWN_MACHINE, f"unknown MachineID {mid}")
            machines_recs.append(rec)

        if owner_redirect:
            for mid, stolen in owner_redirect.items():
                rec = self.machines.get(mid)
                if rec and rec.bound_human_address and stolen != rec.bound_human_address:
                    raise ProtocolReject(
                        REJECT_OWNER_CUT_PAYMENT,
                        f"IMPOSSIBLE: owner cannot redirect bound-human payment on {mid}",
                    )

        try:
            work = self.works.get(work_id)
            if work is None:
                work = self.works.create(work_id=work_id, job_id=job_id or "job_inline")
            if work.status == WorkStatus.SETTLED.value or work.settlement_count >= 1:
                raise ProtocolReject(
                    REJECT_DOUBLE_SETTLEMENT,
                    f"WorkID already settled: {work_id}",
                )
            self.works.transition(work_id, WorkStatus.EXECUTING)
        except WorkIDError as exc:
            msg = str(exc)
            if "already 1" in msg or "SettlementCount" in msg or "already exists" in msg and "SETTLED" in msg:
                raise ProtocolReject(REJECT_DOUBLE_SETTLEMENT, msg) from exc
            raise ProtocolReject(REJECT_WORK_ID, msg) from exc

        weights = work_weights or {m.machine_id: 1.0 for m in machines_recs}
        contribs: list[MachineContribution] = []
        snapshot_sid = None
        if epoch_snapshot is not None:
            from src.artcb.economics.economic_snapshot import settlement_id as make_sid

            snapshot_sid = make_sid(
                work_id=work_id,
                snapshot_digest=epoch_snapshot.digest(),
                protocol_version=epoch_snapshot.protocol_version,
            )
            phases["snapshot"] = {
                "epoch": epoch_snapshot.epoch,
                "digest": epoch_snapshot.digest(),
                "settlement_id": snapshot_sid,
                "rule": "Settlement=f(EconomicStateSnapshot) V-01",
            }
            if settlement_ledger is not None:
                from src.artcb.economics.economic_snapshot import AlreadySettled

                try:
                    settlement_ledger.consume(
                        snapshot_sid,
                        work_id=work_id,
                        node_id=node_id,
                        epoch=epoch_snapshot.epoch,
                    )
                except AlreadySettled as exc:
                    raise ProtocolReject(REJECT_DOUBLE_SETTLEMENT, str(exc)) from exc
        for rec in machines_recs:
            snap_m = epoch_snapshot.machine(rec.machine_id) if epoch_snapshot is not None else None
            owner = snap_m.owner_address if snap_m else rec.owner_address
            n_econ = (
                epoch_snapshot.n_economic(owner)
                if epoch_snapshot is not None
                else self.machines.economic_count(rec.owner_address)
            )
            first = snap_m.is_first_machine if snap_m else (rec.is_first_machine or rec.machine_index == 1)
            bound = snap_m.bound_human_address if snap_m else rec.bound_human_address
            contribs.append(
                MachineContribution(
                    machine_id=rec.machine_id,
                    owner_address=owner,
                    machine_index=snap_m.machine_index if snap_m else rec.machine_index,
                    bound_human_address=bound,
                    work_weight=float(weights.get(rec.machine_id, 1.0)),
                    n_economic=n_econ,
                    is_first_machine=first,
                    provider_score=(provider_scores or {}).get(owner, 0.0),
                )
            )

        h_adult = float(self.h_adult())
        phases["h_adult"] = {
            "count": h_adult,
            "source": "HumanRegistry.verified_adult_count",
            "adult_age_years": 18,
            "demographic_ref": self.demographic.to_dict(),
            "hmax_frozen": False,
        }

        issued_so_far = self.chain._issued_so_far_satoshi()
        dt = interval_seconds if interval_seconds is not None else TARGET_BLOCK_SECONDS
        r_block = issued_reward_satoshi(
            h_adult=h_adult,
            issued_so_far_satoshi=issued_so_far,
            actual_block_interval_seconds=dt,
        )
        phases["r_h"] = {
            "h_adult": h_adult,
            "r_block_satoshi": r_block,
            "interval_seconds": dt,
            "issued_so_far_satoshi": issued_so_far,
        }

        cap = capacity or {
            "cpu": 8.0,
            "ram": 8.0,
            "storage": 8.0,
            "bandwidth": 100.0,
            "latency": 1.0,
            "queue": 0.0,
            "error_rate": 0.0,
        }
        n_max = n_max_from_capacity(
            cpu=cap["cpu"],
            ram=cap["ram"],
            storage=cap["storage"],
            bandwidth=cap["bandwidth"],
            latency=cap["latency"],
            queue=cap["queue"],
            error_rate=cap["error_rate"],
        )
        parts_n = n_partitions if n_partitions is not None else max(1, min(n_max, 5))
        parent_root = self.chain.last_hash()
        partition_assign = assign_partitions(
            [work_id],
            epoch=self.chain.list_blocks() and self.chain.list_blocks()[-1].get("index", 0) or 0,
            parent_root=parent_root,
            n_partitions=parts_n,
        )
        pb_weights = [1.0] * parts_n
        preblocks = partition_block_reward(r_block, pb_weights)
        missing = list(missing_preblock_ids or [])
        present = [pb for pb in preblocks if pb.preblock_id not in missing]
        present_satoshi = sum(pb.reward_satoshi for pb in present)
        requeued: list[str] = []
        if missing:
            for mid in missing:
                tag = f"{work_id}:requeue:{mid}"
                if self.works.get(tag) is None:
                    self.works.create(work_id=tag, job_id=job_id or work_id)
                self.works.transition(tag, WorkStatus.REQUEUED)
                requeued.append(tag)
            settle_budget = present_satoshi
        else:
            settle_budget = r_block
        phases["preblocks"] = {
            "n_partitions": parts_n,
            "n_max": n_max,
            "partition_of_work": partition_assign,
            "missing": missing,
            "present_satoshi": present_satoshi,
            "requeued": requeued,
        }

        settlement = settle_block(
            r_block_satoshi=settle_budget,
            h_adult=h_adult,
            machines=contribs,
            provider_scores=provider_scores,
            hbp_scores=hbp_scores,
        )
        if settlement.total_satoshi != settle_budget:
            raise RuntimeError("settlement conservation broken in protocol engine")
        if issued_so_far + r_block > MAX_SUPPLY_SATOSHI:
            raise RuntimeError("supply would exceed 21M")

        eco = economic_root(settlement.economic_parts)
        phases["hbp"] = {"rate": settlement.hbp_rate, "pool": settlement.hbp_pool_satoshi}
        phases["provider_worker"] = {
            "provider_pool": settlement.provider_pool_satoshi,
            "worker_pool": settlement.worker_pool_satoshi,
        }
        phases["owner_decay"] = {
            rec.machine_id: {
                "n_economic": self.machines.economic_count(rec.owner_address),
                "is_first": rec.is_first_machine or rec.machine_index == 1,
            }
            for rec in machines_recs
        }

        contributors = []
        for rec in machines_recs:
            human = self.humans.get_by_address(rec.owner_address)
            bound = rec.bound_human_address
            hbp_addr = bound or rec.owner_address
            weight = float(weights.get(rec.machine_id, 1.0))
            contributors.append({
                "address": rec.owner_address,
                "pol_score": pol_score,
                "signature": "",
                "machine_id": rec.machine_id,
                "owner_address": rec.owner_address,
                "machine_index": rec.machine_index,
                "bound_human_address": bound,
                "work_weight": weight,
                "n_economic": self.machines.economic_count(rec.owner_address),
                "is_first_machine": rec.is_first_machine or rec.machine_index == 1,
                "work_id": work_id,
                "job_id": job_id,
                "human_id": human.human_id if human else None,
                "provider_score": (provider_scores or {}).get(rec.owner_address, 0.0),
                "hbp_score": (hbp_scores or {}).get(hbp_addr),
                "hbp_contribution": (hbp_scores or {}).get(hbp_addr, 1.0),
                "role": "worker",
            })
        if provider_scores:
            for addr, score in provider_scores.items():
                if float(score) <= 0:
                    continue
                contributors.append({
                    "address": addr,
                    "pol_score": pol_score,
                    "signature": "",
                    "role": "provider",
                    "provider_score": float(score),
                    "owner_address": addr,
                    "work_id": work_id,
                    "job_id": job_id,
                })
                logger.debug("provider contributor %s score=%s", addr, score)

        block = self.chain.append_block(
            graph_id=graph_id,
            graph_root=graph_root,
            pol_score=pol_score,
            merkle_root=graph_root,
            visibility=visibility,
            contributors=contributors,
            block_reward=settle_budget,
            verified_humans=h_adult,
            h_adult=h_adult,
            source="mining",
        )
        try:
            rec_after = self.works.get(work_id)
            if rec_after is None or rec_after.status != WorkStatus.SETTLED.value:
                self.works.transition(work_id, WorkStatus.SETTLED, useful_work_score=pol_score)
        except WorkIDError as exc:
            if "REJECT_DOUBLE_SETTLEMENT" in str(exc) or "already 1" in str(exc):
                logger.debug("WorkID %s already settled by chain append", work_id)
            else:
                raise ProtocolReject(REJECT_DOUBLE_SETTLEMENT, str(exc)) from exc

        self.audit.append(
            "protocol_block",
            {
                "block_index": block.index,
                "work_id": work_id,
                "economic_root": eco,
                "h_adult": h_adult,
                "r_block_satoshi": settle_budget,
            },
        )
        supply = self.chain._issued_so_far_satoshi()
        if supply > MAX_SUPPLY_SATOSHI:
            raise RuntimeError("supply exceeded 21M after append")

        result = ProtocolBlockResult(
            block_index=block.index,
            block_hash=block.hash,
            hash_version=int(getattr(block, "hash_version", HASH_VERSION_V2) or HASH_VERSION_V2),
            h_adult=h_adult,
            r_block_satoshi=settle_budget,
            hbp_rate=settlement.hbp_rate,
            economic_root=(block.economics or {}).get("economic_root", eco),
            total_paid_satoshi=settlement.total_satoshi,
            supply_satoshi=supply,
            work_id=work_id,
            job_id=job_id,
            missing_preblocks=missing,
            requeued_work_ids=requeued,
            by_address_satoshi=settlement.by_address(),
            lines=[
                {
                    "address": ln.address,
                    "role": ln.role,
                    "machine_id": ln.machine_id,
                    "reward_satoshi": ln.reward_satoshi,
                }
                for ln in settlement.lines
            ],
            n_max=n_max,
            n_partitions=parts_n,
            job_payment=job_payment,
            phases=phases,
        )
        logger.debug(
            "protocol block=%s hash=%s H_adult=%s paid=%s supply=%s v=%s",
            result.block_index,
            result.block_hash[:16],
            h_adult,
            result.total_paid_satoshi,
            supply,
            result.hash_version,
        )
        return result
