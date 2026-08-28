#!/usr/bin/env python3
"""Post-implementation check: live src.artcb.economics vs rapport 162 GO."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.artcb.economics.emission import issued_reward_satoshi, population_reward_artcb
from src.artcb.economics.owner_decay import OWNER_DECAY_K, fleet_owner_share, payout_owner_share
from src.artcb.economics.settlement import MachineContribution, settle_block
from src.artcb.tokenomics import SATOSHI_PER_ARTCB, TARGET_BLOCK_SECONDS

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("artcb.sim.r162.post")

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def main() -> None:
    r50 = issued_reward_satoshi(0)
    r210k = issued_reward_satoshi(210_000)
    r10s = issued_reward_satoshi(0, actual_block_interval_seconds=10.0)
    payload = {
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "live_now_matches_162": {
            "index_210k_does_not_cut": r50 == r210k == 50 * SATOSHI_PER_ARTCB,
            "time_norm_10s_is_1_60": r10s == r50 // 60,
            "target_block_seconds": TARGET_BLOCK_SECONDS,
            "owner_decay_k": OWNER_DECAY_K,
            "m1_at_n1e6": payout_owner_share(is_first_machine=True, n_economic=1_000_000),
            "fleet_p3": fleet_owner_share(3),
            "fleet_p4": fleet_owner_share(4),
            "fleet_p1000_no_longer_38pct": fleet_owner_share(1000),
        },
    }
    r_block = 50 * SATOSHI_PER_ARTCB
    machines = [
        MachineContribution("A1", "A", 1, None, 1.0),
        MachineContribution("A2", "A", 2, "B", 1.0),
        MachineContribution("A3", "A", 3, "C", 1.0),
        MachineContribution("D1", "D", 1, None, 1.0),
    ]
    result = settle_block(r_block_satoshi=r_block, verified_humans=100_000_000, machines=machines)
    a2 = next(ln.reward_satoshi for ln in result.lines if ln.machine_id == "A2" and ln.role == "owner")
    a3 = next(ln.reward_satoshi for ln in result.lines if ln.machine_id == "A3" and ln.role == "owner")
    payload["settlement"] = {
        "conservation": result.total_satoshi == r_block,
        "a2_owner_equals_a3_owner": a2 == a3,
        "a2_owner_satoshi": a2,
        "a3_owner_satoshi": a3,
        "R_H_100m": population_reward_artcb(100_000_000),
    }
    path = OUT / "11_post_impl_live.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("wrote %s", path)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
