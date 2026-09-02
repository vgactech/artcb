"""Phase 189 — D-043 freeze V-01…V-07 and open artcb-mainnet-1. No secrets."""

from __future__ import annotations

from pathlib import Path

from artcb.crypto_policy import (
    ED25519_ONLY_UNTIL,
    GENESIS_HASH,
    NETWORK_ID,
    PROTOCOL_VERSION,
)
from artcb.devnet_validation import (
    DECISIONS_189,
    ECONOMIC_V,
    ECONOMIC_V_LOCKED,
    certification_gate,
    public_lock,
)
from artcb.economics.economic_snapshot import (
    DEFAULT_FINALITY_CONFIRMATIONS,
    DEFAULT_GRACE_SECONDS,
    ECONOMIC_RULES_VERSION,
)
from artcb.economics.hbp import HBP_END_HUMANS, HBP_PEAK_HUMANS

ROOT = Path(__file__).resolve().parents[1]


def test_d043_locks_economics_and_opens_mainnet_identity() -> None:
    assert NETWORK_ID == "artcb-mainnet-1"
    assert PROTOCOL_VERSION == "189-mainnet-1"
    assert GENESIS_HASH == "genesis-artcb-mainnet-1"
    assert ECONOMIC_V_LOCKED is True
    assert ECONOMIC_RULES_VERSION == "D-025+V01-V07-locked-D043"
    assert DEFAULT_GRACE_SECONDS == 24 * 3600
    assert DEFAULT_FINALITY_CONFIRMATIONS == 2
    assert HBP_PEAK_HUMANS == 4_150_000_000
    assert HBP_END_HUMANS == 8_300_000_000
    assert "Snapshot at epoch start" in ECONOMIC_V["V-01"]
    assert "next epoch" in ECONOMIC_V["V-02"]
    assert "24h" in ECONOMIC_V["V-03"]
    assert "next snapshot" in ECONOMIC_V["V-04"]
    assert "N=2" in ECONOMIC_V["V-05"]
    assert "DemographicReference" in ECONOMIC_V["V-06"]
    assert "10→60→20" in ECONOMIC_V["V-07"]
    text = DECISIONS_189["D-043"]
    assert "artcb-mainnet-1" in text
    assert "certified_distributed_mainnet" in text
    assert "2026-12-31" in text
    lock = public_lock()
    assert lock["economic_v_locked"] is True
    assert lock["distributed_certified"] is False
    assert ED25519_ONLY_UNTIL.startswith("2026-12-31")


def test_certification_still_blocked_without_dv02() -> None:
    gate = certification_gate(
        {
            "DV-01": "PASS",
            "DV-02": "PARTIAL",
            "DV-03": "PASS",
            "DV-04": "PASS",
            "DV-05": "PASS",
            "DV-06": "PARTIAL",
            "DV-07": "PASS",
        }
    )
    assert gate["certified_distributed_mainnet"] is False
    assert "DV-02" in gate["dv_not_pass"]
    assert gate["economic_v_locked"] is True
    assert gate["live_bft_implemented"] is True


def test_sim189_refuses_init_genesis_and_invented_cert() -> None:
    sim = (ROOT / "scripts" / "run_sim189_mainnet_genesis.py").read_text(encoding="utf-8")
    assert "Never invent SHA" in sim
    assert "init_genesis.py" in sim
    assert "certified_distributed_mainnet" in sim
    assert "blocks.jsonl.bak-d043-testbook" in sim
    assert "install.sh" in sim
    assert "STOP_ALL" in sim
    assert "faucet" in sim.lower()
