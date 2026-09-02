"""Consensus parameters extracted from the actual ARTCB code (DV-05 C).

Live HTTP exposes prepare/commit (188) between protocol-compatible peers.
N=4 → F=1 → Q=3. Block append is still longest public chain, not PBFT.
certified_distributed_mainnet remains a separate lock.
"""

from __future__ import annotations

from typing import Any, Final

from artcb.economics.economic_snapshot import DEFAULT_FINALITY_CONFIRMATIONS

LIVE_BFT_IMPLEMENTED: Final[bool] = True

# Historical sim (replicated_settlement.Cluster.majority): Q = n//2 + 1
SIM_SETTLEMENT_QUORUM: Final[str] = "n//2+1"

SIM_FINALITY_CONFIRMATIONS: Final[int] = DEFAULT_FINALITY_CONFIRMATIONS

CLASSICAL_BFT: Final[str] = "N >= 3F+1, Q = 2F+1 (live prepare/commit 188)"

# Four live machines: F=1. Three machines cannot claim F=1.
THREE_NODE_BFT_F: Final[int | None] = None
FOUR_NODE_BFT_F: Final[int] = 1
FOUR_NODE_BFT_Q: Final[int] = 3


def public_spec() -> dict[str, Any]:
    return {
        "live_bft_implemented": LIVE_BFT_IMPLEMENTED,
        "sim_settlement_quorum": SIM_SETTLEMENT_QUORUM,
        "sim_finality_confirmations": SIM_FINALITY_CONFIRMATIONS,
        "classical_bft_note": CLASSICAL_BFT,
        "three_live_nodes_bft_f": THREE_NODE_BFT_F,
        "four_live_nodes_bft_f": FOUR_NODE_BFT_F,
        "four_live_nodes_bft_q": FOUR_NODE_BFT_Q,
        "dv05": "LIVE engine exists; PASS only after honest/offline/delay/double-proposal/divergence on 4 nodes",
        "canonical_tip_sim": "longest valid chain; tie -> lexicographically smaller hash (distributed.py)",
        "scope": "settlement_prepare_commit",
        "not_block_append_bft": True,
    }
