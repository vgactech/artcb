"""Phase 204 — OVH2 rescue SSH recovery + 3-node origin/main keep-book (D-054).

certified stays false. No genesis wipe. Historical 90 TPS is lab, not mainnet.
Isolated tempdir TPS is not distributed mainnet TPS. OVH4 stays blocked
without KEY_API_ARTCB_DOPPLER_4.
"""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import (
    DECISIONS_204,
    OPERATOR_MAINNET_CERTIFICATION_GO,
    certification_gate,
    public_lock,
)

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "scripts" / "run_sim204_three_node_main_homogenize.py"
INJECT = ROOT / "scripts" / "inject_ovh2_ssh_via_rescue.py"
REPORT = ROOT / "rapports" / "204_mainnet_three_node_homogenize_2026-09-02.md"


def test_d054_does_not_certify_and_refuses_90tps_as_mainnet() -> None:
    gate = certification_gate()
    assert gate["certified_distributed_mainnet"] is False
    assert OPERATOR_MAINNET_CERTIFICATION_GO is False
    text = DECISIONS_204["D-054"]
    assert "rescue" in text
    assert "blocks.jsonl" in text
    assert "KEY_API_ARTCB_DOPPLER_4" in text
    assert "90 TPS" in text
    assert ".venv" in text
    assert "OPERATOR_MAINNET_CERTIFICATION_GO stays False" in text
    lock = public_lock()
    assert lock["distributed_certified"] is False
    assert "decisions_204" in lock


def test_sim204_and_rescue_script_never_wipe() -> None:
    sim = SIM.read_text(encoding="utf-8")
    inj = INJECT.read_text(encoding="utf-8")
    assert "Does not wipe blocks.jsonl" in sim
    assert "Does not flip certified_distributed_mainnet" in sim
    assert "cas_b_official_distributed_bench" in sim
    assert "historical_90_tps_is_lab_not_mainnet" in sim
    assert "BOOK_PRESERVED" in inj
    assert "install.sh not executed" in inj
    assert "init_genesis.py not executed" in inj
    assert "Never prints" in inj
    assert "49G" in inj
    assert REPORT.is_file()
    report = REPORT.read_text(encoding="utf-8")
    assert "NOT MAINNET CERTIFIED" in report
    assert "90 TPS" in report
    assert "ad017bca05c2e3799c7dcd120ca1797968d499b6" in report
