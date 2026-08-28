"""Demographic reference — Model B (updatable under hashed dataset, 162)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass

logger = logging.getLogger("artcb.economics.demographic")

# NOT a frozen WPP extract. Provisional until a dated UN 18+ source is hashed in.
H_ADULT_MAX_PROVISIONAL = 5_820_000_000
HBP_PEAK_STILL_PROVISIONAL = 4_150_000_000
HBP_END_STILL_PROVISIONAL = 8_300_000_000
ADULT_AGE_YEARS = 18


@dataclass(frozen=True)
class DemographicReference:
    dataset_id: str
    source: str
    publication_date: str
    adult_population_estimate: float
    methodology_hash: str
    effective_epoch: int

    def to_dict(self) -> dict:
        return asdict(self)

    def digest(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_provisional_reference() -> DemographicReference:
    ref = DemographicReference(
        dataset_id="provisional-not-wpp-freeze",
        source="estimation only — Q-E03 still open for dated UN WPP 18+",
        publication_date="2026-08-28",
        adult_population_estimate=H_ADULT_MAX_PROVISIONAL,
        methodology_hash="pending",
        effective_epoch=0,
    )
    logger.debug("demographic ref digest=%s adult_max=%s", ref.digest()[:16], ref.adult_population_estimate)
    return ref
