"""R306 — P0 proof helpers: primary_of vs stored divergence is detectable."""

from __future__ import annotations

from artcb.consensus.pbft_view import primary_of
from artcb.node_registry import MAC_NODE_ID, OFFICIAL_COMPUTE_NODE_IDS, official_pbft_n_f_q, official_pbft_replica_ids


def test_primary_of_view15_is_ovh1_under_n5() -> None:
    ids = official_pbft_replica_ids()
    assert len(ids) == 5
    assert ids[15 % 5] == "ovh-node-1"
    assert primary_of(15) == "ovh-node-1"
    # historical N=4 residue would have been ids[15 % 4] == ovh-node-4
    assert OFFICIAL_COMPUTE_NODE_IDS[15 % 4] == "ovh-node-4"
    assert primary_of(15) != OFFICIAL_COMPUTE_NODE_IDS[15 % 4]


def test_membership_n5_mac_not_seed() -> None:
    assert official_pbft_n_f_q() == (5, 1, 3)
    assert MAC_NODE_ID in official_pbft_replica_ids()
    assert MAC_NODE_ID not in OFFICIAL_COMPUTE_NODE_IDS


def test_p0_script_exists_and_forbids_wipe() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "scripts" / "run_live306_p0_proof_matrix.py").read_text(
        encoding="utf-8"
    )
    assert "Never wipe" in text or "never wipe" in text.lower()
    assert "CERTIFIED_100=false" in text or "certified_100" in text
    assert "primary_of" in text
    assert "mac-node-local" in text
