"""Continuous owner share P_owner(n) — no 50/40/30/20/10 steps.

Calibration (simulation ARTCB 2026-08-25)::

    P_owner(1)        = 100 %
    P_owner(2)        ≈  50 %
    P_owner(1_000)    ≈  38 %
    P_owner(100_000)  ≈  11.85 %
    lim n→∞           =  10 %

For n ≥ 2::

    P(n) = floor + span / (1 + ((n-2)/τ)^β)

τ and β are fitted at import time from the mid/far calibration points so
those anchors are identities, not approximations.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("artcb.economics.owner_decay")

P_OWNER_FIRST = 1.0
P_OWNER_FLOOR = 0.10
P_OWNER_AT_TWO = 0.50
CALIB_N_MID = 1_000
CALIB_P_MID = 0.38
CALIB_N_FAR = 100_000
CALIB_P_FAR = 0.1185


def _g_from_p(share: float) -> float:
    span = P_OWNER_AT_TWO - P_OWNER_FLOOR
    return (share - P_OWNER_FLOOR) / span


def _fit_tau_beta() -> tuple[float, float]:
    g_mid = _g_from_p(CALIB_P_MID)
    g_far = _g_from_p(CALIB_P_FAR)
    x_mid = float(CALIB_N_MID - 2)
    x_far = float(CALIB_N_FAR - 2)
    rhs_mid = (1.0 / g_mid) - 1.0
    rhs_far = (1.0 / g_far) - 1.0
    beta = math.log(rhs_far / rhs_mid) / math.log(x_far / x_mid)
    tau = x_mid / (rhs_mid ** (1.0 / beta))
    return tau, beta


OWNER_DECAY_TAU, OWNER_DECAY_BETA = _fit_tau_beta()


def owner_share(machine_index: int) -> float:
    """P_owner(n) for the n-th machine of a given owner (1-based)."""
    if machine_index < 1:
        raise ValueError(f"machine_index must be >= 1, got {machine_index}")
    if machine_index == 1:
        return P_OWNER_FIRST
    span = P_OWNER_AT_TWO - P_OWNER_FLOOR
    scaled = ((machine_index - 2) / OWNER_DECAY_TAU) ** OWNER_DECAY_BETA
    share = P_OWNER_FLOOR + span / (1.0 + scaled)
    logger.debug("P_owner(n=%s)=%.10f", machine_index, share)
    return share


def human_share(machine_index: int) -> float:
    """Complement 1 - P_owner(n). Zero on the owner's first machine."""
    return 1.0 - owner_share(machine_index)
