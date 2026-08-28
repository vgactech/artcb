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


def usd_to_artcb_satoshi(usd: float, *, artcb_usd_price: float | None = None) -> int:
    """Oracle price required. Price=0 is a protocol error, not free txs."""
    from src.artcb.economics.oracle import require_artcb_usd_price
    from src.artcb.tokenomics import SATOSHI_PER_ARTCB

    price = require_artcb_usd_price(artcb_usd_price)
    if usd < 0:
        raise ValueError("usd must be >= 0")
    artcb = usd / price
    satoshi = int(artcb * SATOSHI_PER_ARTCB + 0.5)
    logger.debug("usd=%.9f price=%s -> satoshi=%s", usd, price, satoshi)
    return satoshi


def quote_fee_satoshi(
    *,
    congestion: float = 0.0,
    artcb_usd_price: float | None = None,
    snapshot_path=None,
) -> dict:
    """USD fee quote converted with a live (or documented-fallback) oracle.

    This never mints. Fees are quoted in satoshi to be paid from existing
    balances into the UniversalDividendVault.
    """
    from src.artcb.economics.oracle import OracleSnapshot, fetch_oracle_snapshot

    quote = quote_fee_usd(congestion=congestion)
    if artcb_usd_price is not None:
        if artcb_usd_price <= 0:
            raise ValueError("artcb_usd_price must be > 0 (oracle)")
        price = artcb_usd_price
        snap: OracleSnapshot | None = None
        satoshi = usd_to_artcb_satoshi(quote.quoted_usd, artcb_usd_price=price)
    else:
        snap = fetch_oracle_snapshot(snapshot_path=snapshot_path)
        price = snap.artcb_usd
        if not snap.live or price <= 0:
            logger.debug("oracle NOT live — fee satoshi unavailable (price not invented)")
            return {
                "quoted_usd": quote.quoted_usd,
                "cap_usd": quote.cap_usd,
                "floor_usd": quote.floor_usd,
                "congestion": quote.congestion,
                "fee_source": quote.source,
                "artcb_usd": 0.0,
                "fee_satoshi": None,
                "mints": False,
                "destination": "UniversalDividendVault",
                "oracle": snap.to_dict(),
                "live": False,
            }
        satoshi = usd_to_artcb_satoshi(quote.quoted_usd, artcb_usd_price=price)
    payload = {
        "quoted_usd": quote.quoted_usd,
        "cap_usd": quote.cap_usd,
        "floor_usd": quote.floor_usd,
        "congestion": quote.congestion,
        "fee_source": quote.source,
        "artcb_usd": price,
        "fee_satoshi": satoshi,
        "mints": False,
        "destination": "UniversalDividendVault",
        "live": True,
        "oracle": snap.to_dict() if snap is not None else {"artcb_usd_source": "caller"},
    }
    logger.debug("fee satoshi=%s usd=%.9f price=%s", satoshi, quote.quoted_usd, price)
    return payload
