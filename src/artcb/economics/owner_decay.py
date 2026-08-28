"""Continuous OwnerDecay — rapport 162 (user GO).

M1 (first economically active machine of an owner) is **always 100%**.
Every extra machine (n≥2) shares the **same** P(N_economic):

    P(N) = 0.10 + 0.40 * exp(-k * (N-2))   for N ≥ 2
    P(2) = 50%
    P(3) = 49%   (user example — k is fitted to this identity)
    P(4) ≈ 48.025%  (user example ~48%)
    lim N→∞ P = 10%

N_economic counts ACTIVE/GRACE/OFFLINE/… — never a momentary ping.
The previous per-index calibration (38% @ 1000) is **superseded** by 162.

k is not a free magic number: it is derived from the user-locked P(3)=49%.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger("artcb.economics.owner_decay")

P_OWNER_FIRST = 1.0
P_OWNER_FLOOR = 0.10
P_OWNER_AT_TWO = 0.50
P_OWNER_AT_THREE = 0.49  # user GO 162
P_OWNER_AT_FOUR_TARGET = 0.48

# k such that 0.10 + 0.40 * e^{-k} = 0.49
OWNER_DECAY_K = -math.log((P_OWNER_AT_THREE - P_OWNER_FLOOR) / (P_OWNER_AT_TWO - P_OWNER_FLOOR))

# Archived 124 calibration (do not use for live payout).
LEGACY_CALIB_N_MID = 1_000
LEGACY_CALIB_P_MID = 0.38
LEGACY_CALIB_N_FAR = 100_000
LEGACY_CALIB_P_FAR = 0.1185


def fleet_owner_share(n_economic: int) -> float:
    """Owner share applied to **all** extra machines given current N_economic."""
    if n_economic < 1:
        raise ValueError(f"n_economic must be >= 1, got {n_economic}")
    if n_economic == 1:
        return P_OWNER_FIRST
    span = P_OWNER_AT_TWO - P_OWNER_FLOOR
    share = P_OWNER_FLOOR + span * math.exp(-OWNER_DECAY_K * (n_economic - 2))
    logger.debug("fleet_owner_share N=%s P=%.12f k=%.12f", n_economic, share, OWNER_DECAY_K)
    return share


def fleet_human_share(n_economic: int) -> float:
    return 1.0 - fleet_owner_share(n_economic)


def payout_owner_share(*, is_first_machine: bool, n_economic: int) -> float:
    """M1 always 100%; extras use fleet P(N_economic)."""
    if is_first_machine:
        logger.debug("payout M1=100%% (N_economic=%s ignored for M1)", n_economic)
        return P_OWNER_FIRST
    if n_economic < 2:
        # Extra machine while economic count says 1: treat as N=2 (50/50).
        n_economic = 2
    return fleet_owner_share(n_economic)


def owner_share(machine_index: int) -> float:
    """Compatibility wrapper.

    For index==1 → 100%. For index≥2 the share is the **fleet** P(N=index),
    i.e. all extras at that fleet size share the same rate (162), not the
    old per-index 38%@1000 curve.
    Prefer ``payout_owner_share`` + explicit ``n_economic`` at settlement.
    """
    if machine_index < 1:
        raise ValueError(f"machine_index must be >= 1, got {machine_index}")
    if machine_index == 1:
        return P_OWNER_FIRST
    return fleet_owner_share(machine_index)


def human_share(machine_index: int) -> float:
    return 1.0 - owner_share(machine_index)
