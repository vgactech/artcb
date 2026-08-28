#!/usr/bin/env python3
"""Simulation 165 first slice — multi-node scaffolding (NOT a certification).

Nodes A/B/C/D, latency, partition, reorg are **placeholders**.
This does not claim production-secure oracle, full Sybil resistance,
or multi-node certification.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("sim165.multinode")


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "simulations" / f"{stamp}_multinode165_scaffold"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "simulation": "165-multinode-scaffold",
        "utc": stamp,
        "certified": False,
        "claims": {
            "production_secure_oracle": False,
            "full_sybil_resistance": False,
            "multi_node_certification": False,
        },
        "nodes": [
            {"id": "A", "role": "miner", "latency_ms": 12},
            {"id": "B", "role": "miner", "latency_ms": 35},
            {"id": "C", "role": "observer", "latency_ms": 80},
            {"id": "D", "role": "partitioned", "latency_ms": None, "partition": True},
        ],
        "planned": ["latency injection", "partition heal", "reorg window"],
        "status": "scaffold_only",
    }
    path = out_dir / "scaffold.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("wrote %s certified=false", path)
    print(f"SIM165_MULTINODE_DIR={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
