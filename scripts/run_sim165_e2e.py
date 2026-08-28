#!/usr/bin/env python3
"""Simulation 165 — 164 ProtocolEngine + security ON + provider scores + Stripe isolation.

Does not overwrite simulations/20260828T200518Z_e2e164/.
"""

from __future__ import annotations

import os
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["ARTCB_SIM_TAG"] = "e2e165"
os.environ.setdefault("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")

if __name__ == "__main__":
    runpy.run_path(str(ROOT / "scripts" / "run_sim164_e2e.py"), run_name="__main__")
