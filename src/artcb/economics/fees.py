"""Fees (ARTCB only for PoL) + USD-referenced cap — rapport 162.

fee = base + congestion, never above the cheapest observed public-chain
native-transfer p50 (OpenChainBench 2026-08-26: Base USD 0.000311).

Conversion USD→ARTCB is oracle-mediated and MUST NOT decide consensus
directly: nodes agree on a FeeOracle snapshot hash, then apply the formula.
Spark "free" is excluded (not a comparable fee market).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("artcb.economics.fees")

# Observed cheapest fee-charging L2 native transfer (not a frozen ARTCB amount).
FEE_CAP_USD_OBSERVED = 0.000311
FEE_CAP_SOURCE = "OpenChainBench Base native transfer p50 2026-08-26"
FEE_FLOOR_USD_PARAMETER = 0.000001  # anti-spam order of magnitude — not D-xxx
SOLANA_P50_USD_OBSERVED = 0.000484


@dataclass(frozen=True)
class FeeQuote:
    base_usd: float
    congestion: float
    quoted_usd: float
    cap_usd: float
    floor_usd: float
    source: str


def quote_fee_usd(*, congestion: float = 0.0) -> FeeQuote:
    cong = max(0.0, float(congestion))
    raw = FEE_FLOOR_USD_PARAMETER * (1.0 + cong)
    quoted = min(FEE_CAP_USD_OBSERVED, max(FEE_FLOOR_USD_PARAMETER, raw))
    quote = FeeQuote(
        base_usd=FEE_FLOOR_USD_PARAMETER,
        congestion=cong,
        quoted_usd=quoted,
        cap_usd=FEE_CAP_USD_OBSERVED,
        floor_usd=FEE_FLOOR_USD_PARAMETER,
        source=FEE_CAP_SOURCE,
    )
    logger.debug("fee quote usd=%.9f congestion=%s cap=%s", quoted, cong, FEE_CAP_USD_OBSERVED)
    return quote


def usd_to_artcb_satoshi(usd: float, *, artcb_usd_price: float) -> int:
    """Oracle price required. Price=0 is a protocol error, not free txs."""
    if artcb_usd_price <= 0:
        raise ValueError("artcb_usd_price must be > 0 (oracle)")
    if usd < 0:
        raise ValueError("usd must be >= 0")
    from src.artcb.tokenomics import SATOSHI_PER_ARTCB

    artcb = usd / artcb_usd_price
    satoshi = int(artcb * SATOSHI_PER_ARTCB + 0.5)
    logger.debug("usd=%.9f price=%s -> satoshi=%s", usd, artcb_usd_price, satoshi)
    return satoshi
