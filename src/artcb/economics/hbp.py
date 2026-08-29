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


def hbp_rate(verified_humans: float | None = None, *, h_adult: float | None = None) -> float:
    """Share of the block reward reserved for the verified-human pool (H_adult 18+)."""
    humans_raw = h_adult if h_adult is not None else (
        0.0 if verified_humans is None else verified_humans
    )
    if humans_raw < 0:
        raise ValueError(f"h_adult/verified_humans must be >= 0, got {humans_raw}")
    humans = float(humans_raw)
    if humans <= HBP_PEAK_HUMANS:
        rate = HBP_START + (HBP_PEAK - HBP_START) * (humans / HBP_PEAK_HUMANS)
    elif humans >= HBP_END_HUMANS:
        rate = HBP_END
    else:
        span = HBP_END_HUMANS - HBP_PEAK_HUMANS
        rate = HBP_PEAK + (HBP_END - HBP_PEAK) * ((humans - HBP_PEAK_HUMANS) / span)
    logger.debug("HBP(H) h_adult=%s rate=%.10f", humans, rate)
    return rate


def hbp_rate_from_ratio(
    *,
    h_verified: float,
    h_adult_max: float,
    peak_humans: float = HBP_PEAK_HUMANS,
    end_humans: float = HBP_END_HUMANS,
) -> float:
    """V-07 provisional: 10→60→20 on H_verified / H_adult_max.

    Peak/end ratios are derived from the historical absolute anchors divided
    by H_adult_max. Not a frozen WPP lock. Live ``hbp_rate`` is unchanged.
    """
    if h_verified < 0:
        raise ValueError(f"h_verified must be >= 0, got {h_verified}")
    if h_adult_max <= 0:
        raise ValueError("h_adult_max must be > 0")
    ratio = float(h_verified) / float(h_adult_max)
    peak_ratio = min(1.0, float(peak_humans) / float(h_adult_max))
    end_ratio = min(1.0, float(end_humans) / float(h_adult_max))
    if ratio <= peak_ratio:
        rate = HBP_START + (HBP_PEAK - HBP_START) * (ratio / peak_ratio if peak_ratio else 0.0)
    elif ratio >= end_ratio:
        rate = HBP_END
    else:
        span = end_ratio - peak_ratio
        rate = HBP_PEAK + (HBP_END - HBP_PEAK) * ((ratio - peak_ratio) / span if span else 0.0)
    logger.debug(
        "HBP(ratio) h=%s max=%s ratio=%.6f peak_r=%.6f end_r=%.6f rate=%.10f",
        h_verified,
        h_adult_max,
        ratio,
        peak_ratio,
        end_ratio,
        rate,
    )
    return rate
