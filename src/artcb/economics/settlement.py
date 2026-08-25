"""Block settlement — owner / bound-human / HBP, conservation of R_block.

For a machine M_{A,n} with normalized work weight W::

    Reward_owner  = W * R(H) * (1 - HBP(H)) * P_owner(n)
    Reward_human  = W * R(H) * (1 - HBP(H)) * (1 - P_owner(n))
    Reward_HBP    = R(H) * HBP(H)   (split among unique verified humans
                                     participating in the block)

sum of all legs = R_block. Pre-blocks must already sum to the same R_block
before this function is called.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.artcb.economics.hbp import hbp_rate
from src.artcb.economics.owner_decay import human_share, owner_share
from src.artcb.economics.satoshi import allocate_satoshi, satoshi_to_artcb

logger = logging.getLogger("artcb.economics.settlement")


@dataclass(frozen=True)
class MachineContribution:
    machine_id: str
    owner_address: str
    machine_index: int
    bound_human_address: str | None
    work_weight: float


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
    lines: list[SettlementLine] = field(default_factory=list)

    @property
    def total_satoshi(self) -> int:
        return sum(line.reward_satoshi for line in self.lines)

    def by_address(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for line in self.lines:
            totals[line.address] = totals.get(line.address, 0) + line.reward_satoshi
        return totals


def settle_block(
    *,
    r_block_satoshi: int,
    verified_humans: float,
    machines: list[MachineContribution],
) -> SettlementResult:
    if r_block_satoshi < 0:
        raise ValueError("r_block_satoshi must be >= 0")
    if not machines:
        raise ValueError("settlement requires at least one machine")

    rate = hbp_rate(verified_humans)
    pools = allocate_satoshi(
        {"hbp": rate, "work": 1.0 - rate},
        r_block_satoshi,
    )
    hbp_pool = pools["hbp"]
    work_pool = pools["work"]

    work_weights = {
        m.machine_id: max(0.0, m.work_weight) for m in machines
    }
    if sum(work_weights.values()) <= 0:
        raise ValueError("machine work weights must sum to a positive value")
    machine_work = allocate_satoshi(work_weights, work_pool)

    lines: list[SettlementLine] = []
    for machine in machines:
        envelope = machine_work[machine.machine_id]
        p_owner = owner_share(machine.machine_index)
        p_human = human_share(machine.machine_index)
        if machine.machine_index == 1:
            legs = {f"owner:{machine.owner_address}": 1.0}
        else:
            if not machine.bound_human_address:
                raise ValueError(
                    f"machine {machine.machine_id} index {machine.machine_index} "
                    "requires a bound verified human"
                )
            legs = {
                f"owner:{machine.owner_address}": p_owner,
                f"human:{machine.bound_human_address}": p_human,
            }
        split = allocate_satoshi(legs, envelope)
        for key, satoshi in split.items():
            role, address = key.split(":", 1)
            share = satoshi_to_artcb(satoshi) / satoshi_to_artcb(r_block_satoshi) if r_block_satoshi else 0.0
            lines.append(
                SettlementLine(
                    address=address,
                    role=role,
                    machine_id=machine.machine_id,
                    reward_satoshi=satoshi,
                    share=share,
                )
            )

    humans = []
    seen: set[str] = set()
    for machine in machines:
        for address in (machine.owner_address, machine.bound_human_address):
            if address and address not in seen:
                seen.add(address)
                humans.append(address)
    if hbp_pool > 0:
        if not humans:
            raise ValueError("HBP pool is non-zero but no verified human is present")
        hbp_weights = {f"hbp:{addr}": 1.0 for addr in humans}
        hbp_split = allocate_satoshi(hbp_weights, hbp_pool)
        for key, satoshi in hbp_split.items():
            _, address = key.split(":", 1)
            share = satoshi_to_artcb(satoshi) / satoshi_to_artcb(r_block_satoshi) if r_block_satoshi else 0.0
            lines.append(
                SettlementLine(
                    address=address,
                    role="hbp",
                    machine_id=None,
                    reward_satoshi=satoshi,
                    share=share,
                )
            )

    result = SettlementResult(
        r_block_satoshi=r_block_satoshi,
        verified_humans=verified_humans,
        hbp_rate=rate,
        work_pool_satoshi=work_pool,
        hbp_pool_satoshi=hbp_pool,
        lines=lines,
    )
    if result.total_satoshi != r_block_satoshi:
        raise RuntimeError(
            f"settlement conservation broken: {result.total_satoshi} != {r_block_satoshi}"
        )
    logger.debug(
        "settled R_block=%s H=%s HBP=%.6f work=%s hbp=%s lines=%s",
        r_block_satoshi,
        verified_humans,
        rate,
        work_pool,
        hbp_pool,
        len(lines),
    )
    return result
