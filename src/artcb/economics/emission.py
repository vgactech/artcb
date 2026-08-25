"""Emission schedule — 21M hard cap, 50 ARTCB genesis, 210_000-block epochs.

Mathematical identity (integer satoshi, no velocity, H <= 1M)::

    R_0 * HALVING_INTERVAL * 2  =  50 * 210_000 * 2  =  21_000_000

R(H) scales the *issued* reward down as verified-human population grows,
never above the schedule and never above the remaining hard-cap budget.

    R(H) = R_0 * (max(H, H_REF) / H_REF)^(-α)
    α    = ln(50) / ln(64)

so R(1M)=50 and R(64M)≈1, with no artificial floor at 1 ARTCB.
"""

from __future__ import annotations

import logging
import math

from src.artcb.economics.satoshi import artcb_to_satoshi
from src.artcb.tokenomics import (
    HALVING_INTERVAL,
    INITIAL_BLOCK_REWARD_ARTCB,
    INITIAL_BLOCK_REWARD_SATOSHI,
    MAX_HALVINGS,
    MAX_SUPPLY_SATOSHI,
    SATOSHI_PER_ARTCB,
)

logger = logging.getLogger("artcb.economics.emission")

# Population at which R(H) equals the genesis reward (50 ARTCB).
H_REF = 1_000_000
# α such that R(64 * H_REF) = 1 ARTCB.
REWARD_POPULATION_ALPHA = math.log(INITIAL_BLOCK_REWARD_ARTCB) / math.log(64.0)


def population_reward_artcb(verified_humans: float) -> float:
    """R(H) — population-scaled block reward in ARTCB.

    H <= H_REF (including 0 / unknown) → genesis reward 50 ARTCB.
    H > H_REF → strictly decreasing, no floor at 1.
    """
    if verified_humans < 0:
        raise ValueError(f"verified_humans must be >= 0, got {verified_humans}")
    humans = max(float(verified_humans), float(H_REF))
    reward = INITIAL_BLOCK_REWARD_ARTCB * (humans / H_REF) ** (-REWARD_POPULATION_ALPHA)
    logger.debug(
        "R(H) verified_humans=%s clamped=%s reward=%.10f",
        verified_humans,
        humans,
        reward,
    )
    return reward


def schedule_reward_satoshi(block_index: int, extra_epochs: int = 0) -> int:
    """Bitcoin-style schedule: R_0 >> (index // 210_000 + extra_epochs)."""
    if block_index < 0:
        raise ValueError(f"block_index must be >= 0, got {block_index}")
    if extra_epochs < 0:
        raise ValueError(f"extra_epochs must be >= 0, got {extra_epochs}")
    epoch = block_index // HALVING_INTERVAL + extra_epochs
    if epoch >= MAX_HALVINGS:
        return 0
    return INITIAL_BLOCK_REWARD_SATOSHI >> epoch


def issued_reward_satoshi(
    block_index: int,
    *,
    verified_humans: float = 0,
    extra_epochs: int = 0,
    issued_so_far_satoshi: int = 0,
) -> int:
    """Reward actually issued for this block.

    ``min(schedule, R(H), remaining_hard_cap)``.
    """
    if issued_so_far_satoshi < 0:
        raise ValueError("issued_so_far_satoshi must be >= 0")
    remaining = MAX_SUPPLY_SATOSHI - issued_so_far_satoshi
    if remaining <= 0:
        logger.debug("hard cap reached issued_so_far=%s", issued_so_far_satoshi)
        return 0
    scheduled = schedule_reward_satoshi(block_index, extra_epochs=extra_epochs)
    population = artcb_to_satoshi(population_reward_artcb(verified_humans))
    issued = min(scheduled, population, remaining)
    logger.debug(
        "issued_reward index=%s schedule=%s R(H)=%s remaining=%s -> %s",
        block_index,
        scheduled,
        population,
        remaining,
        issued,
    )
    return issued


def asymptotic_schedule_supply_satoshi() -> int:
    """Sum of the pure 50/210k schedule until reward hits 0 satoshi.

    Equals 21_000_000 ARTCB in integer satoshi when R_0 * H * 2 fits the
    satoshi grid (50 * 1e8 is a power-of-two-friendly integer).
    """
    total = 0
    for epoch in range(MAX_HALVINGS):
        reward = INITIAL_BLOCK_REWARD_SATOSHI >> epoch
        if reward == 0:
            break
        total += reward * HALVING_INTERVAL
        if total >= MAX_SUPPLY_SATOSHI:
            return MAX_SUPPLY_SATOSHI
    return min(total, MAX_SUPPLY_SATOSHI)


def cumulative_schedule_artcb(block_count: int) -> float:
    """Cumulative ARTCB issued after ``block_count`` blocks (H<=1M, no velocity)."""
    if block_count < 0:
        raise ValueError("block_count must be >= 0")
    total = 0
    remaining = block_count
    epoch = 0
    while remaining > 0 and epoch < MAX_HALVINGS:
        reward = INITIAL_BLOCK_REWARD_SATOSHI >> epoch
        if reward == 0:
            break
        take = min(remaining, HALVING_INTERVAL)
        total += reward * take
        remaining -= take
        epoch += 1
    return min(total, MAX_SUPPLY_SATOSHI) / SATOSHI_PER_ARTCB
