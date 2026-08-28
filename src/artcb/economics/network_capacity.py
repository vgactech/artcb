"""Dynamic N_max from measured capacity (rapport 162). Safety 0.75 is a parameter."""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("artcb.economics.network_capacity")

CAPACITY_SAFETY = 0.75  # 162 suggestion — not a frozen economic constant
N_MAX_TX_TESTNET_START = 100
N_MAX_POL_TESTNET_START = 50
N_MAX_HBP_TESTNET_START = 50


def n_max_from_capacity(
    *,
    cpu: float,
    ram: float,
    storage: float,
    bandwidth: float,
    latency: float,
    queue: float,
    error_rate: float,
    safety: float = CAPACITY_SAFETY,
) -> int:
    cpu_c = max(0.0, cpu)
    ram_c = max(0.0, ram)
    net_c = max(0.0, bandwidth) / max(latency, 1e-6)
    val_c = max(0.0, storage) / (1.0 + queue) / (1.0 + error_rate)
    raw = min(cpu_c, ram_c, net_c, val_c) * safety
    n_max = max(1, int(math.floor(raw)))
    logger.debug("N_max=%s cpu=%s ram=%s net=%s val=%s", n_max, cpu_c, ram_c, net_c, val_c)
    return n_max
