"""R303 — SHA layers, restricted Doppler skip, membership still not live PBFT."""

from __future__ import annotations

from pathlib import Path

from artcb.node_registry import MAC_NODE_ID, OFFICIAL_COMPUTE_NODE_IDS, official_pbft_n_f_q, official_pbft_replica_ids

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "artcb_mac_doppler_run.sh"


def test_mac_doppler_wrapper_skips_restricted_sudo_name() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "MAC_SUDO_PASSWORD" in text
    assert "--only-secrets" in text
    assert '"secrets"' in text or "secrets" in text
    assert "--only-names" in text
    assert "never prints secret values" in text.lower()


def test_membership_still_five_seeds_still_four() -> None:
    assert official_pbft_n_f_q() == (5, 1, 3)
    ids = official_pbft_replica_ids()
    assert MAC_NODE_ID in ids
    assert MAC_NODE_ID not in OFFICIAL_COMPUTE_NODE_IDS
    assert len(OFFICIAL_COMPUTE_NODE_IDS) == 4
    assert len(ids) == 5
