"""Integer satoshi allocation — conservation exacte (aucune création/destruction)."""

from __future__ import annotations

import math


def allocate_satoshi(shares: dict[str, float], total: int) -> dict[str, int]:
    """Largest-remainder allocation.

    Guarantee: ``sum(result.values()) == total`` when ``total >= 0`` and
    ``shares`` is non-empty with at least one positive weight. Zero/negative
    weights receive 0. Empty shares with ``total > 0`` is a protocol error.
    """
    if total < 0:
        raise ValueError(f"total satoshi must be >= 0, got {total}")
    if not shares:
        if total == 0:
            return {}
        raise ValueError("cannot allocate positive satoshi to empty shares")
    if total == 0:
        return {key: 0 for key in shares}

    clamped = {key: max(0.0, float(weight)) for key, weight in shares.items()}
    weight_sum = sum(clamped.values())
    if weight_sum <= 0.0:
        return {key: 0 for key in shares}

    raw = {key: total * weight / weight_sum for key, weight in clamped.items()}
    floors = {key: int(math.floor(value)) for key, value in raw.items()}
    remainder = total - sum(floors.values())
    order = sorted(
        raw.keys(),
        key=lambda key: (raw[key] - floors[key], key),
        reverse=True,
    )
    for key in order:
        if remainder <= 0:
            break
        floors[key] += 1
        remainder -= 1
    return floors


def artcb_to_satoshi(amount: float) -> int:
    """Round half-up toward nearest satoshi (1 ARTCB = 10^8 satoshi)."""
    from src.artcb.tokenomics import SATOSHI_PER_ARTCB

    if amount < 0:
        raise ValueError(f"ARTCB amount must be >= 0, got {amount}")
    return int(math.floor(amount * SATOSHI_PER_ARTCB + 0.5))


def satoshi_to_artcb(amount: int) -> float:
    from src.artcb.tokenomics import SATOSHI_PER_ARTCB

    return amount / SATOSHI_PER_ARTCB
