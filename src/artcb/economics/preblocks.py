"""Dynamic pre-blocks — partition work, never mint extra money.

Invariant::

    sum_i Reward(PB_i)  =  R_block

Pre-blocks split *work*, they do not multiply the block reward.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.artcb.economics.satoshi import allocate_satoshi

logger = logging.getLogger("artcb.economics.preblocks")


@dataclass(frozen=True)
class PreBlockShare:
    preblock_id: str
    weight: float
    reward_satoshi: int


def normalize_weights(weights: list[float]) -> list[float]:
    if not weights:
        raise ValueError("pre-block weights must be non-empty")
    clamped = [max(0.0, float(w)) for w in weights]
    total = sum(clamped)
    if total <= 0:
        raise ValueError("pre-block weights must sum to a positive value")
    return [w / total for w in clamped]


def partition_block_reward(
    r_block_satoshi: int,
    weights: list[float],
    *,
    prefix: str = "pb",
) -> list[PreBlockShare]:
    """Split R_block across pre-blocks proportionally to capacity weights."""
    if r_block_satoshi < 0:
        raise ValueError("r_block_satoshi must be >= 0")
    norm = normalize_weights(weights)
    shares = {f"{prefix}{i + 1}": w for i, w in enumerate(norm)}
    allocated = allocate_satoshi(shares, r_block_satoshi)
    result = [
        PreBlockShare(
            preblock_id=f"{prefix}{i + 1}",
            weight=norm[i],
            reward_satoshi=allocated[f"{prefix}{i + 1}"],
        )
        for i in range(len(norm))
    ]
    total = sum(item.reward_satoshi for item in result)
    if total != r_block_satoshi:
        raise RuntimeError(
            f"pre-block conservation broken: {total} != {r_block_satoshi}"
        )
    logger.debug(
        "partitioned R_block=%s into %s preblocks total=%s",
        r_block_satoshi,
        len(result),
        total,
    )
    return result
