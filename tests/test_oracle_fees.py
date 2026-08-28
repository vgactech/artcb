"""USD→ARTCB oracle — never invent a listed price."""

from __future__ import annotations

import pytest

from src.artcb.economics.fees import quote_fee_satoshi, quote_fee_usd
from src.artcb.economics.oracle import (
    OracleError,
    fetch_artcb_usd_quote,
    fetch_oracle_snapshot,
    require_artcb_usd_price,
)


def test_forced_stub_is_not_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_ORACLE_FORCE_STUB", "1")
    quote = fetch_artcb_usd_quote()
    assert quote.live is False
    assert quote.artcb_usd is None
    snap = fetch_oracle_snapshot()
    assert snap.live is False
    assert snap.artcb_usd == 0.0
    fee = quote_fee_satoshi()
    assert fee["mints"] is False
    assert fee["live"] is False
    assert fee["fee_satoshi"] is None


def test_explicit_price_converts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_ORACLE_FORCE_STUB", "1")
    sat = quote_fee_satoshi(artcb_usd_price=1.0)
    assert sat["fee_satoshi"] > 0
    assert sat["mints"] is False
    q = quote_fee_usd(congestion=1e9)
    assert q.quoted_usd <= q.cap_usd


def test_require_price_without_live_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARTCB_ORACLE_FORCE_STUB", "1")
    with pytest.raises(OracleError, match="NOT live"):
        require_artcb_usd_price()
    assert require_artcb_usd_price(2.5) == 2.5
