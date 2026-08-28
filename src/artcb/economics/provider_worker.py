"""Provider / Worker dynamic split — rapport 162.

Start 50/50. Same weighted principle as HBP.
Bounds 20–80% are **parameters** (ChatGPT suggestion in 162), not a frozen D-xxx.
"""

from __future__ import annotations

import logging
import math

from src.artcb.economics.satoshi import allocate_satoshi

logger = logging.getLogger("artcb.economics.provider_worker")

PROVIDER_START = 0.50
WORKER_START = 0.50
PROVIDER_MIN = 0.20
PROVIDER_MAX = 0.80


def clamp_provider_share(share: float) -> float:
    return min(PROVIDER_MAX, max(PROVIDER_MIN, float(share)))


def dynamic_provider_share(
    *,
    jobs_waiting: float,
    provider_availability: float,
    worker_availability: float,
) -> float:
    eps = 1e-9
    scarcity = (jobs_waiting + 1.0) * (worker_availability + eps) / (provider_availability + eps)
    delta = 0.05 * math.tanh(math.log(max(scarcity, eps)))
    share = clamp_provider_share(PROVIDER_START + delta)
    logger.debug(
        "provider_share jobs=%s P=%s W=%s -> %.6f",
        jobs_waiting,
        provider_availability,
        worker_availability,
        share,
    )
    return share


def split_pol_pool(
    pol_pool_satoshi: int,
    *,
    provider_share: float,
    provider_scores: dict[str, float],
    worker_scores: dict[str, float],
) -> tuple[dict[str, int], dict[str, int], int, int]:
    share = clamp_provider_share(provider_share)
    if not provider_scores:
        # No providers in this block: 100% of PoL pool to workers (mining path).
        worker = allocate_satoshi(worker_scores, pol_pool_satoshi)
        logger.debug("no provider scores — worker takes full PoL pool %s", pol_pool_satoshi)
        return {}, worker, 0, pol_pool_satoshi
    pools = allocate_satoshi({"provider": share, "worker": 1.0 - share}, pol_pool_satoshi)
    provider = allocate_satoshi(provider_scores, pools["provider"])
    worker = allocate_satoshi(worker_scores, pools["worker"])
    if sum(provider.values()) + sum(worker.values()) != pol_pool_satoshi:
        raise RuntimeError("provider/worker conservation broken")
    return provider, worker, pools["provider"], pools["worker"]
