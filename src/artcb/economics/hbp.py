"""Human Baseline Pool — HBP(H): 10% → 60% → 20%.

Anchors (protocol lock, simulation 2026-08-25)::

    H = 0           → 10 %
    H = 4.15e9      → 60 %
    H = 8.30e9      → 20 %

Linear on each segment. Independent of R(H) and of P_owner(n).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("artcb.economics.hbp")

HBP_START = 0.10
HBP_PEAK = 0.60
HBP_END = 0.20
HBP_PEAK_HUMANS = 4_150_000_000
HBP_END_HUMANS = 8_300_000_000


def hbp_rate(verified_humans: float) -> float:
    """Share of the block reward reserved for the verified-human pool."""
    if verified_humans < 0:
        raise ValueError(f"verified_humans must be >= 0, got {verified_humans}")
    humans = float(verified_humans)
    if humans <= HBP_PEAK_HUMANS:
        rate = HBP_START + (HBP_PEAK - HBP_START) * (humans / HBP_PEAK_HUMANS)
    elif humans >= HBP_END_HUMANS:
        rate = HBP_END
    else:
        span = HBP_END_HUMANS - HBP_PEAK_HUMANS
        rate = HBP_PEAK + (HBP_END - HBP_PEAK) * ((humans - HBP_PEAK_HUMANS) / span)
    logger.debug("HBP(H) verified_humans=%s rate=%.10f", humans, rate)
    return rate
