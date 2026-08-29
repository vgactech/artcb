"""USD→ARTCB fee oracle.

ARTCB is not a listed public ticker. This module:

1. Probes public HTTPS feeds (CoinGecko ping, BTC/USD, USDT/USD, ARTCB
   ticker, Frankfurter USD→EUR) to prove live network access.
2. Price selection (never invented)::

     a) listed CoinGecko ``artcb`` USD if > 0  → live=True
     b) ``ARTCB_USD_PRICE`` env if > 0         → operator override, live=True, fallback_used
     c) otherwise live=False, artcb_usd=0, DEBUG « NOT live »

   BTC/USD and USDT/USD are **liveness probes only**. They are NEVER copied
   as the ARTCB price.

3. Conversion USD→satoshi is refused unless a positive price exists
   (listed, env, or explicit caller argument). Fees never mint (D-025 vault).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("artcb.economics.oracle")

COINGECKO_PING = "https://api.coingecko.com/api/v3/ping"
COINGECKO_BTC = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
COINGECKO_USDT = "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=usd"
COINGECKO_ARTCB = "https://api.coingecko.com/api/v3/simple/price?ids=artcb&vs_currencies=usd"
FRANKFURTER_USD_EUR = "https://api.frankfurter.app/latest?from=USD&to=EUR"
REQUEST_TIMEOUT_SEC = 8.0
ARTCB_UNLISTED_NOTE = (
    "ARTCB has no listed USD market. BTC/USDT probes are liveness-only and are "
    "NOT used as the ARTCB price. Pass ARTCB_USD_PRICE or wait for listing."
)


class OracleError(ValueError):
    """Raised when a live conversion is required but no authentic price exists."""


@dataclass(frozen=True)
class OracleQuote:
    artcb_usd: float | None
    live: bool
    source: str
    fetched_at: str
    probe_ok: bool
    probe_detail: str
    stub_reason: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OracleSnapshot:
    fetched_at: str
    source: str
    timeout_seconds: float
    probe_ok: bool
    probe_detail: str
    usdt_usd: float | None
    btc_usd: float | None
    usd_eur: float | None
    artcb_usd: float
    artcb_usd_source: str
    live: bool
    fallback_used: bool
    fallback_reason: str | None
    stub_reason: str | None
    note: str

    def to_dict(self) -> dict:
        return asdict(self)

    def digest(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_get_json(url: str, *, timeout: float = REQUEST_TIMEOUT_SEC) -> tuple[bool, dict | str]:
    req = Request(url, headers={"User-Agent": "ARTCB-oracle/164", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public HTTPS
            body = resp.read(16384)
            data = json.loads(body.decode("utf-8"))
            return True, data if isinstance(data, dict) else {"raw": data}
    except (URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        logger.debug("oracle HTTP failed url=%s err=%s", url.split("?")[0], type(exc).__name__)
        return False, f"{type(exc).__name__}"


def _cg_usd(body: dict | str, coin_id: str) -> float | None:
    if not isinstance(body, dict):
        return None
    nested = body.get(coin_id)
    if not isinstance(nested, dict):
        return None
    try:
        value = float(nested.get("usd"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def fetch_oracle_snapshot(
    *,
    snapshot_path: Path | None = None,
    timeout: float = REQUEST_TIMEOUT_SEC,
    force_stub: bool | None = None,
) -> OracleSnapshot:
    if force_stub is None:
        force_stub = os.getenv("ARTCB_ORACLE_FORCE_STUB", "").strip() in {"1", "true", "TRUE"}
    if force_stub:
        logger.debug("USD→ARTCB oracle NOT live (forced stub)")
        snap = OracleSnapshot(
            fetched_at=_now(),
            source="stub",
            timeout_seconds=timeout,
            probe_ok=False,
            probe_detail="forced stub",
            usdt_usd=None,
            btc_usd=None,
            usd_eur=None,
            artcb_usd=0.0,
            artcb_usd_source="stub",
            live=False,
            fallback_used=True,
            fallback_reason="ARTCB_ORACLE_FORCE_STUB — not a live ARTCB/USD price",
            stub_reason="ARTCB_ORACLE_FORCE_STUB — not a live ARTCB/USD price",
            note=ARTCB_UNLISTED_NOTE,
        )
        return snap

    ping_ok, ping_body = _http_get_json(COINGECKO_PING, timeout=timeout)
    btc_ok, btc_body = _http_get_json(COINGECKO_BTC, timeout=timeout) if ping_ok else (False, "skipped")
    usdt_ok, usdt_body = _http_get_json(COINGECKO_USDT, timeout=timeout) if ping_ok else (False, "skipped")
    artcb_ok, artcb_body = _http_get_json(COINGECKO_ARTCB, timeout=timeout) if ping_ok else (False, "skipped")
    fx_ok, fx_body = _http_get_json(FRANKFURTER_USD_EUR, timeout=timeout)

    btc_usd = _cg_usd(btc_body, "bitcoin") if btc_ok else None
    usdt_usd = _cg_usd(usdt_body, "tether") if usdt_ok else None
    listed = _cg_usd(artcb_body, "artcb") if artcb_ok else None
    usd_eur = None
    if fx_ok and isinstance(fx_body, dict):
        try:
            usd_eur = float((fx_body.get("rates") or {}).get("EUR"))
            if usd_eur is not None and usd_eur <= 0:
                usd_eur = None
        except (TypeError, ValueError):
            usd_eur = None

    operator = os.environ.get("ARTCB_USD_PRICE", "").strip()
    fallback_used = False
    fallback_reason: str | None = None
    live = False
    artcb_usd = 0.0
    source = "none"
    artcb_source = "none"

    if listed:
        artcb_usd = listed
        source = COINGECKO_ARTCB
        artcb_source = "coingecko:artcb"
        live = True
    elif operator:
        try:
            artcb_usd = float(operator)
        except ValueError as exc:
            raise OracleError("ARTCB_USD_PRICE must be a positive float") from exc
        if artcb_usd <= 0:
            raise OracleError("ARTCB_USD_PRICE must be > 0")
        source = "env:ARTCB_USD_PRICE"
        artcb_source = source
        live = True
        fallback_used = True
        fallback_reason = "operator override — ARTCB unlisted"
    else:
        logger.debug(
            "USD→ARTCB oracle NOT live — BTC/USDT probes are not an ARTCB price (%s)",
            ARTCB_UNLISTED_NOTE,
        )
        source = "coingecko" if ping_ok else "stub"
        artcb_source = "unlisted"
        live = False
        fallback_used = True
        fallback_reason = ARTCB_UNLISTED_NOTE

    detail = (
        f"ping={ping_ok} btc={btc_ok}:{btc_usd} usdt={usdt_ok}:{usdt_usd} "
        f"artcb_listed={bool(listed)} frankfurter={fx_ok}:{usd_eur}"
    )
    snap = OracleSnapshot(
        fetched_at=_now(),
        source=source,
        timeout_seconds=timeout,
        probe_ok=bool(ping_ok or fx_ok),
        probe_detail=detail if ping_ok else f"{detail} ping_err={ping_body}",
        usdt_usd=usdt_usd,
        btc_usd=btc_usd,
        usd_eur=usd_eur,
        artcb_usd=artcb_usd,
        artcb_usd_source=artcb_source,
        live=live,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        stub_reason=None if live and not fallback_used else fallback_reason,
        note=ARTCB_UNLISTED_NOTE,
    )
    if snapshot_path is not None:
        path = Path(snapshot_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    logger.debug(
        "oracle artcb_usd=%s source=%s live=%s fallback=%s digest=%s NOT_INVENTED",
        snap.artcb_usd,
        snap.artcb_usd_source,
        snap.live,
        snap.fallback_used,
        snap.digest()[:16],
    )
    return snap


def fetch_artcb_usd_quote(*, force_stub: bool | None = None) -> OracleQuote:
    snap = fetch_oracle_snapshot(force_stub=force_stub)
    return OracleQuote(
        artcb_usd=snap.artcb_usd if snap.live and snap.artcb_usd > 0 else None,
        live=snap.live and snap.artcb_usd > 0,
        source=snap.source,
        fetched_at=snap.fetched_at,
        probe_ok=snap.probe_ok,
        probe_detail=snap.probe_detail,
        stub_reason=snap.stub_reason,
    )


@dataclass(frozen=True)
class OracleConsensus:
    status: str  # quorum | OracleUnavailable
    median: float | None
    sources_ok: int
    min_sources: int
    quotes: tuple[float | None, ...]
    invented: bool

    def to_dict(self) -> dict:
        return asdict(self)


def oracle_median_or_unavailable(
    quotes: list[float | None],
    *,
    min_sources: int = 2,
) -> OracleConsensus:
    """V-33: median of authentic quotes. No quorum → OracleUnavailable, never invent."""
    valid = [float(q) for q in quotes if q is not None and float(q) > 0]
    if len(valid) < min_sources:
        logger.debug(
            "OracleUnavailable valid=%s min=%s invented=false",
            len(valid),
            min_sources,
        )
        return OracleConsensus(
            status="OracleUnavailable",
            median=None,
            sources_ok=len(valid),
            min_sources=min_sources,
            quotes=tuple(quotes),
            invented=False,
        )
    ordered = sorted(valid)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        med = ordered[mid]
    else:
        med = (ordered[mid - 1] + ordered[mid]) / 2.0
    return OracleConsensus(
        status="quorum",
        median=med,
        sources_ok=len(valid),
        min_sources=min_sources,
        quotes=tuple(quotes),
        invented=False,
    )


def require_artcb_usd_price(explicit_price: float | None = None) -> float:
    if explicit_price is not None:
        if explicit_price <= 0:
            raise OracleError("artcb_usd_price must be > 0 (never invent 0)")
        return float(explicit_price)
    snap = fetch_oracle_snapshot()
    if not snap.live or snap.artcb_usd <= 0:
        logger.debug("oracle NOT live — cannot convert USD→ARTCB without explicit price")
        raise OracleError(
            "USD→ARTCB oracle is NOT live (ARTCB unlisted). Pass an explicit governance price."
        )
    return snap.artcb_usd
