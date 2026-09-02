"""Phase 187 — D-041 same public book, DV-04 C four-node lock text. No secrets."""

from __future__ import annotations

from pathlib import Path

from artcb.consensus_spec import LIVE_BFT_IMPLEMENTED
from artcb.devnet_validation import DECISIONS_186, DECISIONS_187, DV, public_lock

ROOT = Path(__file__).resolve().parents[1]


def test_d041_adopts_existing_book_not_a_merge() -> None:
    assert DV["DV-04"]["letter"] == "C"
    assert "D-036" in DECISIONS_186["D-040"]
    text = DECISIONS_187["D-041"]
    assert "8d542e49" in text
    assert "cc61f710" in text
    assert "not a merge" in text
    assert "wallets" in text.lower() or "chain.key" in text
    assert "certified mainnet" in text.lower() or "Not certified" in text
    lock = public_lock()
    assert lock["distributed_certified"] is False
    assert lock["decisions_187"]["D-041"] == text
    assert LIVE_BFT_IMPLEMENTED is True


def test_dv04_spec_counts_ovh1_after_d041() -> None:
    spec = (ROOT / "validation" / "DV-04" / "SPEC.md").read_text(encoding="utf-8")
    assert "152.228.144.34" in spec
    assert "174-devnet-1" in spec
    assert "legacy (no protocol_version)" not in spec
    assert "D-041" in spec
    assert "certified_distributed_mainnet" in spec


def test_sim187_refuses_invented_merge_and_ovh1_as_ovh4() -> None:
    sim = (ROOT / "scripts" / "run_sim187_dv04_four_node.py").read_text(encoding="utf-8")
    assert "Never invent SHA" in sim
    assert "certified_distributed_mainnet stays false" in sim
    assert "ovh4_ip_missing_or_forbidden" in sim
    assert "restart_ovh1" in sim
    assert "four_equal_after_restart" in sim
    assert "sudo systemctl restart artcb" in sim
