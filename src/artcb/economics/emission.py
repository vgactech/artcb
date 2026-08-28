"""Emission — 21M hard cap, R(H) only. No block-index schedule.

Locked 2026-08-26 (user + rapports 158–159, D-024)::

    R_block = min(R(H), remaining_21M)

R(H) scales the issued reward as verified-human population grows::

    R(H) = R_0 * (max(H, H_REF) / H_REF)^(-α)
    α    = ln(50) / ln(64)

so R(1M)=50 and R(64M)≈1, with no artificial floor at 1 ARTCB.

REMOVED from the live path (rapport 161)::

    - HALVING_INTERVAL = 210_000  (Bitcoin-style epoch)
    - schedule = R0 >> (block_index // 210_000)
    - extra_epochs / epoch_dyn = floor(log2(velocity_24h / 144))
    - identity 50 × 210_000 × 2 as an *emission* schedule
      (21M remains the hard cap only — D-014)

Deprecated helpers below exist only to document the removed arithmetic.
They must not be called from ChainManager.append_block.
"""

from __future__ import annotations

import logging
import math
import warnings

from src.artcb.economics.satoshi import artcb_to_satoshi
from src.artcb.tokenomics import (
    DEPRECATED_HALVING_INTERVAL,
    INITIAL_BLOCK_REWARD_ARTCB,
    INITIAL_BLOCK_REWARD_SATOSHI,
    MAX_HALVINGS,
    MAX_SUPPLY_SATOSHI,
    SATOSHI_PER_ARTCB,
    TARGET_BLOCK_SECONDS,
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


def issued_reward_satoshi(
    block_index: int = 0,
    *,
    verified_humans: float = 0,
    issued_so_far_satoshi: int = 0,
    extra_epochs: int = 0,
    actual_block_interval_seconds: float | None = None,
) -> int:
    """Reward actually issued: min(R(H) * dt/T, remaining_hard_cap).

    ``block_index`` is kept for call-site compatibility and logging only.
    It does **not** reduce the reward (D-024 — no 210k).

    ``actual_block_interval_seconds`` (rapport 162 GO): if the chain is 10×
    faster than ``TARGET_BLOCK_SECONDS`` (600 s, TOKENOMICS §4.1), each
    block issues 1/10 of R(H). This is **not** a calendar halving.

    ``extra_epochs`` is accepted then ignored (removed velocity/halving path).
    """
    if block_index < 0:
        raise ValueError(f"block_index must be >= 0, got {block_index}")
    if issued_so_far_satoshi < 0:
        raise ValueError("issued_so_far_satoshi must be >= 0")
    if extra_epochs:
        logger.warning(
            "extra_epochs=%s ignored — velocity/halving removed from emission (D-024)",
            extra_epochs,
        )
    remaining = MAX_SUPPLY_SATOSHI - issued_so_far_satoshi
    if remaining <= 0:
        logger.debug("hard cap reached issued_so_far=%s", issued_so_far_satoshi)
        return 0
    r_h = population_reward_artcb(verified_humans)
    interval = (
        float(actual_block_interval_seconds)
        if actual_block_interval_seconds is not None
        else TARGET_BLOCK_SECONDS
    )
    if interval <= 0:
        raise ValueError("actual_block_interval_seconds must be > 0")
    scaled = r_h * (interval / TARGET_BLOCK_SECONDS)
    population = artcb_to_satoshi(scaled)
    issued = min(population, remaining)
    logger.debug(
        "issued_reward index=%s (unused) H=%s interval=%s R(H)=%.10f scaled=%.10f remaining=%s -> %s",
        block_index,
        verified_humans,
        interval,
        r_h,
        scaled,
        remaining,
        issued,
    )
    return issued


def schedule_reward_satoshi(block_index: int, extra_epochs: int = 0) -> int:
    """REMOVED live path — Bitcoin-style 210k schedule, kept as historical record.

    Do not use for new blocks. See issued_reward_satoshi.
    """
    warnings.warn(
        "schedule_reward_satoshi is removed from emission (D-024 geopopulation). "
        "Live reward is min(R(H), remaining_21M).",
        DeprecationWarning,
        stacklevel=2,
    )
    if block_index < 0:
        raise ValueError(f"block_index must be >= 0, got {block_index}")
    if extra_epochs < 0:
        raise ValueError(f"extra_epochs must be >= 0, got {extra_epochs}")
    epoch = block_index // DEPRECATED_HALVING_INTERVAL + extra_epochs
    if epoch >= MAX_HALVINGS:
        return 0
    return INITIAL_BLOCK_REWARD_SATOSHI >> epoch


def asymptotic_schedule_supply_satoshi() -> int:
    """Historical sum of the removed 50/210k schedule (not the live emission)."""
    warnings.warn(
        "asymptotic_schedule_supply_satoshi documents the removed 210k calendar.",
        DeprecationWarning,
        stacklevel=2,
    )
    total = 0
    for epoch in range(MAX_HALVINGS):
        reward = INITIAL_BLOCK_REWARD_SATOSHI >> epoch
        if reward == 0:
            break
        total += reward * DEPRECATED_HALVING_INTERVAL
        if total >= MAX_SUPPLY_SATOSHI:
            return MAX_SUPPLY_SATOSHI
    return min(total, MAX_SUPPLY_SATOSHI)


def cumulative_schedule_artcb(block_count: int) -> float:
    """Historical cumulative ARTCB of the removed 210k calendar (H<=1M)."""
    warnings.warn(
        "cumulative_schedule_artcb documents the removed 210k calendar.",
        DeprecationWarning,
        stacklevel=2,
    )
    if block_count < 0:
        raise ValueError("block_count must be >= 0")
    total = 0
    remaining = block_count
    epoch = 0
    while remaining > 0 and epoch < MAX_HALVINGS:
        reward = INITIAL_BLOCK_REWARD_SATOSHI >> epoch
        if reward == 0:
            break
        take = min(remaining, DEPRECATED_HALVING_INTERVAL)
        total += reward * take
        remaining -= take
        epoch += 1
    return min(total, MAX_SUPPLY_SATOSHI) / SATOSHI_PER_ARTCB
