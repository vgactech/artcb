"""Monthly settlement lock — 30 days after monthly finality (user GO 162)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger("artcb.economics.monthly_lock")

LOCK_DAYS = 30


def unlock_at_after_settlement(settled_at: datetime) -> datetime:
    if settled_at.tzinfo is None:
        settled_at = settled_at.replace(tzinfo=UTC)
    unlock = settled_at + timedelta(days=LOCK_DAYS)
    logger.debug("settled=%s unlock=%s", settled_at.isoformat(), unlock.isoformat())
    return unlock


def is_spendable(settled_at: datetime, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now >= unlock_at_after_settlement(settled_at)
