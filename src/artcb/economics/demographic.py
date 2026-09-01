"""Demographic reference — Model B (hashed dataset, community may publish a newer extract).

Q-E03 locked D-045: one dated UN WPP 2024 18+ extract. The protocol does **not**
auto-refresh this number. A later community extract is a new DemographicReference
with a new methodology_hash (still model B), not a silent overwrite.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass

logger = logging.getLogger("artcb.economics.demographic")

ADULT_AGE_YEARS = 18

# UN WPP 2024 Summary of Results (July 2024): world population "8.2 billion in 2024".
# The UN does not publish a pre-aggregated 18+ cell. Ages 18–24 are 7/10 of the
# official 15–24 band (uniform within the 5-year / 10-year group). Inputs below
# are World, Medium variant, year 2024 from the WPP 2024 age-group extract
# (OWID grapher population-by-age-group-with-projections, UN WPP 2024 processed).
WPP2024_FREEZE_INPUTS: dict[str, object] = {
    "dataset": "UN DESA World Population Prospects 2024",
    "publication_date": "2024-07-11",
    "variant": "Medium",
    "location": "World",
    "year": 2024,
    "official_total_rounded_billions": 8.2,
    "total_persons": 8_161_972_574,
    "age_65_plus": 832_893_768,
    "age_25_64": 4_041_127_584,
    "under_25": 3_287_364_224,
    "under_15": 2_016_800_739,
    "age_15_24": 1_270_563_485,
    "age_18_24_seven_tenths_of_15_24": 889_394_440,
    "h_adult_18_plus": 5_763_415_792,
    "interpolation": "age_18_24 = round((under_25 - under_15) * 7 / 10)",
    "community_updates": "new hashed DemographicReference; no auto-refresh",
    "summary_pdf": (
        "https://www.un.org/development/desa/pd/sites/"
        "www.un.org.development.desa.pd/files/files/documents/2024/Jul/"
        "wpp2024_summary_of_results_final_web.pdf"
    ),
}

H_ADULT_MAX = int(WPP2024_FREEZE_INPUTS["h_adult_18_plus"])
# Alias kept so older tests/imports that still say "provisional" compile.
H_ADULT_MAX_PROVISIONAL = H_ADULT_MAX
HBP_PEAK_STILL_PROVISIONAL = 4_150_000_000
HBP_END_STILL_PROVISIONAL = 8_300_000_000
HMAX_FROZEN = True


def wpp2024_methodology_hash() -> str:
    canonical = json.dumps(WPP2024_FREEZE_INPUTS, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def default_reference() -> DemographicReference:
    ref = DemographicReference(
        dataset_id="un-wpp-2024-world-18plus-medium-2024",
        source=(
            "UN DESA World Population Prospects 2024 Medium, World 2024. "
            "Official published total 8.2 billion (Summary of Results, 2024-07-11). "
            "No UN 18+ cell; 18+ = 25–64 + 65+ + 7/10 of (under-25 − under-15). "
            "Community may publish a newer hashed extract; this node does not auto-update."
        ),
        publication_date="2024-07-11",
        adult_population_estimate=float(H_ADULT_MAX),
        methodology_hash=wpp2024_methodology_hash(),
        effective_epoch=0,
    )
    logger.debug("demographic ref digest=%s adult_max=%s", ref.digest()[:16], ref.adult_population_estimate)
    return ref


def default_provisional_reference() -> DemographicReference:
    """D-045: no longer provisional. Alias kept for call sites."""
    return default_reference()
