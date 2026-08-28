"""Block settlement — rapport 162.

Envelope::

    R_block → HBP(H) + PoL
    PoL     → ProviderPool + WorkerPool   (50/50 start if provider_scores given)
    Worker  → machines by work_weight
    machine n=1 → owner 100%
    machine n≥2 → owner P(N_economic), human 1-P  (same P for all extras)

HBP is weighted by contribution scores when provided, else equal among
unique verified humans (legacy fallback).
sum of all legs = R_block.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.artcb.economics.hbp import hbp_rate
from src.artcb.economics.owner_decay import payout_owner_share
from src.artcb.economics.provider_worker import PROVIDER_START, split_pol_pool
from src.artcb.economics.satoshi import allocate_satoshi, satoshi_to_artcb

logger = logging.getLogger("artcb.economics.settlement")


@dataclass(frozen=True)
class MachineContribution:
    machine_id: str
    owner_address: str
    machine_index: int
    bound_human_address: str | None
    work_weight: float
    n_economic: int | None = None
    is_first_machine: bool | None = None
    hbp_contribution: float = 1.0
    provider_score: float = 0.0


@dataclass
class SettlementLine:
    address: str
    role: str
    machine_id: str | None
    reward_satoshi: int
    share: float


@dataclass
class SettlementResult:
    r_block_satoshi: int
    verified_humans: float
    hbp_rate: float
    work_pool_satoshi: int
    hbp_pool_satoshi: int
    provider_pool_satoshi: int = 0
    worker_pool_satoshi: int = 0
    economic_parts: dict = field(default_factory=dict)
    lines: list[SettlementLine] = field(default_factory=list)

    @property
    def total_satoshi(self) -> int:
        return sum(line.reward_satoshi for line in self.lines)

    def by_address(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for line in self.lines:
            totals[line.address] = totals.get(line.address, 0) + line.reward_satoshi
        return totals


def _n_economic_for(machine: MachineContribution, machines: list[MachineContribution]) -> int:
    if machine.n_economic is not None:
        return machine.n_economic
    return max(
        1,
        sum(1 for other in machines if other.owner_address == machine.owner_address),
    )


def _is_first(machine: MachineContribution) -> bool:
    if machine.is_first_machine is not None:
        return machine.is_first_machine
    return machine.machine_index == 1


def settle_block(
    *,
    r_block_satoshi: int,
    verified_humans: float | None = None,
    h_adult: float | None = None,
    machines: list[MachineContribution],
    provider_scores: dict[str, float] | None = None,
    provider_share: float | None = None,
    hbp_scores: dict[str, float] | None = None,
) -> SettlementResult:
    if r_block_satoshi < 0:
        raise ValueError("r_block_satoshi must be >= 0")
    if not machines:
        raise ValueError("settlement requires at least one machine")

    humans = h_adult if h_adult is not None else (
        0.0 if verified_humans is None else verified_humans
    )
    rate = hbp_rate(h_adult=humans)
    pools = allocate_satoshi({"hbp": rate, "work": 1.0 - rate}, r_block_satoshi)
    hbp_pool = pools["hbp"]
    work_pool = pools["work"]

    worker_scores = {m.machine_id: max(0.0, m.work_weight) for m in machines}
    if sum(worker_scores.values()) <= 0:
        raise ValueError("machine work weights must sum to a positive value")

    scores_p = provider_scores if provider_scores else {
        m.owner_address: m.provider_score for m in machines if m.provider_score > 0
    }
    share = PROVIDER_START if provider_share is None else provider_share
    provider_pay, worker_pay, provider_pool, worker_pool = split_pol_pool(
        work_pool,
        provider_share=share,
        provider_scores=scores_p,
        worker_scores=worker_scores,
    )

    lines: list[SettlementLine] = []

    def _add(address: str, role: str, machine_id: str | None, satoshi: int) -> None:
        share_of_block = (
            satoshi_to_artcb(satoshi) / satoshi_to_artcb(r_block_satoshi) if r_block_satoshi else 0.0
        )
        lines.append(
            SettlementLine(
                address=address,
                role=role,
                machine_id=machine_id,
                reward_satoshi=satoshi,
                share=share_of_block,
            )
        )

    for address, satoshi in provider_pay.items():
        _add(address, "provider", None, satoshi)

    for machine in machines:
        envelope = worker_pay.get(machine.machine_id, 0)
        n_econ = _n_economic_for(machine, machines)
        first = _is_first(machine)
        p_owner = payout_owner_share(is_first_machine=first, n_economic=n_econ)
        if first:
            _add(machine.owner_address, "owner", machine.machine_id, envelope)
            continue
        if not machine.bound_human_address:
            raise ValueError(
                f"machine {machine.machine_id} index {machine.machine_index} "
                "requires a bound verified human"
            )
        split = allocate_satoshi(
            {"owner": p_owner, "human": 1.0 - p_owner},
            envelope,
        )
        _add(machine.owner_address, "owner", machine.machine_id, split["owner"])
        _add(machine.bound_human_address, "human", machine.machine_id, split["human"])

    humans_weights: dict[str, float] = {}
    if hbp_scores:
        humans_weights = {addr: max(0.0, w) for addr, w in hbp_scores.items() if addr}
    else:
        seen: set[str] = set()
        for machine in machines:
            for address in (machine.owner_address, machine.bound_human_address):
                if address and address not in seen:
                    seen.add(address)
                    humans_weights[address] = max(0.0, machine.hbp_contribution)
    if hbp_pool > 0:
        if not humans_weights:
            raise ValueError("HBP pool is non-zero but no verified human is present")
        hbp_split = allocate_satoshi(humans_weights, hbp_pool)
        for address, satoshi in hbp_split.items():
            _add(address, "hbp", None, satoshi)

    parts = {
        "r_block_satoshi": r_block_satoshi,
        "h_adult": humans,
        "hbp_pool_satoshi": hbp_pool,
        "provider_pool_satoshi": provider_pool,
        "worker_pool_satoshi": worker_pool,
        "lines": [(ln.address, ln.role, ln.machine_id, ln.reward_satoshi) for ln in lines],
    }
    result = SettlementResult(
        r_block_satoshi=r_block_satoshi,
        verified_humans=humans,
        hbp_rate=rate,
        work_pool_satoshi=work_pool,
        hbp_pool_satoshi=hbp_pool,
        provider_pool_satoshi=provider_pool,
        worker_pool_satoshi=worker_pool,
        economic_parts=parts,
        lines=lines,
    )
    if result.total_satoshi != r_block_satoshi:
        raise RuntimeError(
            f"settlement conservation broken: {result.total_satoshi} != {r_block_satoshi}"
        )
    logger.debug(
        "settled R=%s H_adult=%s HBP=%.6f work=%s provider=%s worker=%s lines=%s",
        r_block_satoshi,
        humans,
        rate,
        work_pool,
        provider_pool,
        worker_pool,
        len(lines),
    )
    return result


class OwnerCannotCutPaymentError(RuntimeError):
    """Owner A cannot reduce bound-human B's protocol payment."""


def reject_owner_payment_cut(*_args, **_kwargs) -> None:
    logger.debug("owner payment cut rejected IMPOSSIBLE")
    raise OwnerCannotCutPaymentError(
        "IMPOSSIBLE: owner cannot cut a bound-human settlement line"
    )
