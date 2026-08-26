#!/usr/bin/env python3
"""Simulation réelle du protocole économique D-023 — logs JSON (DEBUG).

Usage:
  PYTHONPATH=src python3 scripts/simulate_economics.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from artcb.economics.emission import (  # noqa: E402
    issued_reward_satoshi,
    population_reward_artcb,
)
from artcb.economics.hbp import hbp_rate
from artcb.economics.owner_decay import owner_share
from artcb.economics.settlement import MachineContribution, settle_block
from artcb.tokenomics import (  # noqa: E402
    EMISSION_MODEL,
    INITIAL_BLOCK_REWARD_ARTCB,
    MAX_SUPPLY_ARTCB,
    SATOSHI_PER_ARTCB,
)

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
stamp = datetime.now(UTC).strftime("%Y%m%d")
log_path = LOG_DIR / f"{stamp}_economics_protocol.json"

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("artcb.simulate_economics")


def main() -> dict:
    same_late = issued_reward_satoshi(210_000)
    same_early = issued_reward_satoshi(0)
    r_h_table = {
        str(h): population_reward_artcb(h)
        for h in (0, 1_000_000, 10_000_000, 64_000_000, 100_000_000, 1_000_000_000)
    }
    hbp_table = {
        str(h): hbp_rate(h)
        for h in (0, 100_000_000, 1_000_000_000, 4_150_000_000, 8_300_000_000)
    }
    owner_table = {
        str(n): owner_share(n)
        for n in (1, 2, 3, 4, 5, 10, 100, 1_000, 10_000, 100_000)
    }

    machines = [
        MachineContribution("A1", "A", 1, None, 1.0),
        MachineContribution("A2", "A", 2, "B", 1.0),
        MachineContribution("A3", "A", 3, "C", 1.0),
        MachineContribution("D1", "D", 1, None, 1.0),
    ]
    r_block = 50 * SATOSHI_PER_ARTCB
    settlement = settle_block(
        r_block_satoshi=r_block,
        verified_humans=100_000_000,
        machines=machines,
    )
    by_addr_artcb = {
        addr: sat / SATOSHI_PER_ARTCB for addr, sat in settlement.by_address().items()
    }

    r_1b = issued_reward_satoshi(0, verified_humans=1_000_000_000)
    settlement_1b = settle_block(
        r_block_satoshi=r_1b,
        verified_humans=1_000_000_000,
        machines=machines,
    )

    payload = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "identity": {
            "R0": INITIAL_BLOCK_REWARD_ARTCB,
            "emission_model": EMISSION_MODEL,
            "halving_removed": True,
            "index_210k_still_50": same_late == same_early == int(50 * SATOSHI_PER_ARTCB),
            "max_supply": MAX_SUPPLY_ARTCB,
        },
        "r_h_artcb": r_h_table,
        "hbp_rate": hbp_table,
        "owner_share": owner_table,
        "settlement_100m_R50": {
            "r_block_artcb": 50.0,
            "hbp_rate": settlement.hbp_rate,
            "total_artcb": settlement.total_satoshi / SATOSHI_PER_ARTCB,
            "conservation_ok": settlement.total_satoshi == r_block,
            "by_address_artcb": by_addr_artcb,
        },
        "settlement_1b": {
            "r_block_artcb": r_1b / SATOSHI_PER_ARTCB,
            "hbp_rate": settlement_1b.hbp_rate,
            "hbp_pool_artcb": settlement_1b.hbp_pool_satoshi / SATOSHI_PER_ARTCB,
            "work_pool_artcb": settlement_1b.work_pool_satoshi / SATOSHI_PER_ARTCB,
            "conservation_ok": settlement_1b.total_satoshi == r_1b,
        },
    }
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.debug("wrote %s", log_path)
    print(json.dumps(payload, indent=2))
    print(f"\nlog: {log_path}")
    return payload


if __name__ == "__main__":
    main()
