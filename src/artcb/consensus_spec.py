"""Consensus parameters extracted from the actual ARTCB code (DV-05 C).

These are documentation constants, not a live BFT engine. The live HTTP
API does not run a Byzantine replica protocol between OVH/AWS nodes.
"""

from __future__ import annotations

from typing import Any, Final

from artcb.economics.economic_snapshot import DEFAULT_FINALITY_CONFIRMATIONS

# Live P2P/API: no N/F/Q Byzantine formula is enforced.
LIVE_BFT_IMPLEMENTED: Final[bool] = False

# Simulation-only (replicated_settlement.Cluster.majority): Q = n//2 + 1
SIM_SETTLEMENT_QUORUM: Final[str] = "n//2+1"

# Simulation-only finality (economic_snapshot / distributed.is_final)
SIM_FINALITY_CONFIRMATIONS: Final[int] = DEFAULT_FINALITY_CONFIRMATIONS

# Classical BFT inequality is NOT wired to live nodes.
CLASSICAL_BFT: Final[str] = "N >= 3F+1 is a literature bound, not ARTCB live consensus"

# With 3 live machines we cannot claim F=1 BFT even if we wanted 3F+1.
THREE_NODE_BFT_F: Final[int | None] = None


def public_spec() -> dict[str, Any]:
    return {
        "live_bft_implemented": LIVE_BFT_IMPLEMENTED,
        "sim_settlement_quorum": SIM_SETTLEMENT_QUORUM,
        "sim_finality_confirmations": SIM_FINALITY_CONFIRMATIONS,
        "classical_bft_note": CLASSICAL_BFT,
        "three_live_nodes_bft_f": THREE_NODE_BFT_F,
        "dv05": "BLOCKED until a live BFT engine exists and DV-04 PASS on 4 nodes",
        "canonical_tip_sim": "longest valid chain; tie -> lexicographically smaller hash (distributed.py)",
    }
