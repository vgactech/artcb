"""ARTCB rapport-162 simulation core — real arithmetic, no economic mocks.

Uses live `src.artcb.economics` where D-024 already matches 162, and the
162-validated formulas where the branch still implements the older model.

Derived (not invented) constants:
    OWNER_DECAY_K from user examples N=2→50%, N=3→49% (P(N)=0.10+0.40*e^{-k(N-2)})
    TARGET_BLOCK_SECONDS = 600 from TOKENOMICS_ARTCB §4.1 (already documented)
    FEE_CAP_USD from OpenChainBench 2026-08-26 Base p50 native transfer
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from src.artcb.economics.emission import (
    H_REF,
    REWARD_POPULATION_ALPHA,
    issued_reward_satoshi,
    population_reward_artcb,
)
from src.artcb.economics.hbp import HBP_END_HUMANS, HBP_PEAK_HUMANS, hbp_rate
from src.artcb.economics.owner_decay import owner_share as live_owner_share_by_index
from src.artcb.economics.preblocks import partition_block_reward
from src.artcb.economics.satoshi import allocate_satoshi, artcb_to_satoshi, satoshi_to_artcb
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.tokenomics import (
    INITIAL_BLOCK_REWARD_ARTCB,
    MAX_SUPPLY_ARTCB,
    SATOSHI_PER_ARTCB,
)

logger = logging.getLogger("artcb.sim.r162")

# --- 162-validated / already-documented ---
Q_FINDER = 100
FINDER_ATTESTATIONS_PER_DAY_SIM = 25  # user estimate 20–30; 272.16 discarded
H_BOOTSTRAP = 1
CREATOR_GENESIS_VERIFIED = True
TARGET_BLOCK_SECONDS = 600.0  # TOKENOMICS §4.1, not a new magic number
PROVIDER_START = 0.50
WORKER_START = 0.50
PROVIDER_MIN = 0.20  # ChatGPT suggestion in 162 — PARAMETER, not frozen D-xxx
PROVIDER_MAX = 0.80
LOCK_DAYS = 30
MAX_EXTERNAL_BINDINGS = 1
P_OWNER_FLOOR = 0.10
P_OWNER_AT_TWO = 0.50
P_OWNER_AT_THREE_EXAMPLE = 0.49  # user GO 162
P_OWNER_AT_FOUR_EXAMPLE = 0.48

# k such that 0.10 + 0.40 * exp(-k) = 0.49
OWNER_DECAY_K = -math.log((P_OWNER_AT_THREE_EXAMPLE - P_OWNER_FLOOR) / (P_OWNER_AT_TWO - P_OWNER_FLOOR))

# Observed cheapest fee-charging public chain (OpenChainBench 2026-08-26):
# Base native transfer p50 = $0.000311. Solana p50 = $0.000484.
# Spark "free" is not a comparable fee market. Cap is USD-referenced, not ARTCB.
FEE_CAP_USD_OBSERVED = 0.000311
FEE_FLOOR_USD_ANTISPAM = 0.000001  # 1e-6 USD — order of magnitude, not frozen ARTCB
HBP_ANCHORS_PROVISIONAL = True  # 4.15e9 / 8.3e9 still not WPP 18+ freeze

ECONOMIC_STATES_COUNTING = frozenset(
    {"REGISTERED", "ATTESTED", "ACTIVE", "GRACE", "DEACTIVATION_REQUESTED", "OFFLINE"}
)
ECONOMIC_STATES_EXITED = frozenset({"TRANSFERRED", "RETIRED", "COMPROMISED"})


def fleet_owner_share(n_economic: int) -> float:
    """P_owner for EVERY extra machine (n>=2) given current economic fleet size.

    M1 is always 100% and is not this function.
    User 162: N=2 → 50%, N=3 → 49% all extras, N=4 → 48% all extras, → 10%.
    """
    if n_economic < 2:
        return 1.0
    span = P_OWNER_AT_TWO - P_OWNER_FLOOR
    share = P_OWNER_FLOOR + span * math.exp(-OWNER_DECAY_K * (n_economic - 2))
    logger.debug("fleet_owner_share N=%s P=%.10f k=%.10f", n_economic, share, OWNER_DECAY_K)
    return share


def fleet_human_share(n_economic: int) -> float:
    if n_economic < 2:
        return 0.0
    return 1.0 - fleet_owner_share(n_economic)


def machine_owner_payout_share(*, is_first_machine: bool, n_economic: int) -> float:
    if is_first_machine:
        return 1.0
    return fleet_owner_share(n_economic)


def emission_rate_artcb_per_target_interval(verified_adults: float) -> float:
    """R(H) per TARGET_BLOCK_SECONDS — demographic, not calendar."""
    return population_reward_artcb(verified_adults)


def reward_per_block_artcb(
    verified_adults: float,
    *,
    remaining_artcb: float,
    actual_block_interval_seconds: float = TARGET_BLOCK_SECONDS,
) -> float:
    """Time-normalized: 10× faster blocks ⇒ 1/10 reward/block. User GO 162.

    Does NOT reintroduce 210k. Index is unused.
    """
    if actual_block_interval_seconds <= 0:
        raise ValueError("actual_block_interval_seconds must be > 0")
    r_h = emission_rate_artcb_per_target_interval(verified_adults)
    r_block = r_h * (actual_block_interval_seconds / TARGET_BLOCK_SECONDS)
    issued = min(r_block, max(0.0, remaining_artcb))
    logger.debug(
        "R_block H=%s interval=%s R(H)=%.10f issued=%.10f remaining=%.10f",
        verified_adults,
        actual_block_interval_seconds,
        r_h,
        issued,
        remaining_artcb,
    )
    return issued


def days_to_exhaust_at_constant_r(
    r_per_block: float,
    interval_seconds: float,
    remaining: float = MAX_SUPPLY_ARTCB,
) -> float:
    if r_per_block <= 0 or interval_seconds <= 0:
        return math.inf
    blocks_per_day = 86_400.0 / interval_seconds
    per_day = r_per_block * blocks_per_day
    return remaining / per_day if per_day > 0 else math.inf


def finder_active_needed(new_adults_per_day: float, attestations_per_finder_day: float = FINDER_ATTESTATIONS_PER_DAY_SIM) -> float:
    needed = new_adults_per_day * Q_FINDER
    return needed / attestations_per_finder_day if attestations_per_finder_day else math.inf


def partition_id(work_id: str, epoch: int, parent_root: str, n_partitions: int) -> int:
    if n_partitions < 1:
        raise ValueError("n_partitions must be >= 1")
    material = f"{work_id}|{epoch}|{parent_root}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    return int(digest, 16) % n_partitions


def economic_root(parts: dict[str, str]) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def weighted_split(pool_satoshi: int, scores: dict[str, float]) -> dict[str, int]:
    return allocate_satoshi(scores, pool_satoshi)


def provider_worker_split(
    pol_pool_satoshi: int,
    *,
    provider_share: float,
    provider_scores: dict[str, float],
    worker_scores: dict[str, float],
) -> tuple[dict[str, int], dict[str, int], int, int]:
    provider_share = min(PROVIDER_MAX, max(PROVIDER_MIN, provider_share))
    pools = allocate_satoshi(
        {"provider": provider_share, "worker": 1.0 - provider_share},
        pol_pool_satoshi,
    )
    return (
        weighted_split(pools["provider"], provider_scores),
        weighted_split(pools["worker"], worker_scores),
        pools["provider"],
        pools["worker"],
    )


def dynamic_provider_share(
    *,
    jobs_waiting: float,
    provider_availability: float,
    worker_availability: float,
) -> float:
    """Heuristic 162: rare Providers raise their pool, rare Workers raise Worker pool.

    Clamped to [20%, 80%]. Parameter, not a frozen D-xxx.
    """
    eps = 1e-9
    scarcity = (jobs_waiting + 1.0) * (worker_availability + eps) / (provider_availability + eps)
    # scarcity > 1 → more jobs/workers relative to providers → raise provider share
    delta = 0.05 * math.tanh(math.log(max(scarcity, eps)))
    return min(PROVIDER_MAX, max(PROVIDER_MIN, PROVIDER_START + delta))


@dataclass
class FeeQuote:
    base_usd: float
    congestion: float
    quoted_usd: float
    cap_usd: float
    floor_usd: float

    def to_dict(self) -> dict:
        return asdict(self)


def quote_fee_usd(*, congestion: float = 0.0) -> FeeQuote:
    """ARTCB fee in USD reference; conversion to ARTCB is oracle (not frozen)."""
    cong = max(0.0, float(congestion))
    raw = FEE_FLOOR_USD_ANTISPAM * (1.0 + cong)
    quoted = min(FEE_CAP_USD_OBSERVED, max(FEE_FLOOR_USD_ANTISPAM, raw))
    return FeeQuote(
        base_usd=FEE_FLOOR_USD_ANTISPAM,
        congestion=cong,
        quoted_usd=quoted,
        cap_usd=FEE_CAP_USD_OBSERVED,
        floor_usd=FEE_FLOOR_USD_ANTISPAM,
    )


def n_max_from_capacity(
    *,
    cpu: float,
    ram: float,
    storage: float,
    bandwidth: float,
    latency: float,
    queue: float,
    error_rate: float,
    safety: float = 0.75,
) -> int:
    """Dynamic N_max. safety=0.75 is 162's suggested margin — parameter."""
    cpu_c = max(0.0, cpu)
    ram_c = max(0.0, ram)
    net_c = max(0.0, bandwidth) / max(latency, 1e-6)
    val_c = max(0.0, storage) / (1.0 + queue) / (1.0 + error_rate)
    raw = min(cpu_c, ram_c, net_c, val_c) * safety
    return max(1, int(math.floor(raw)))


def dump_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.debug("wrote %s bytes=%s", path, path.stat().st_size)
