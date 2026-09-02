"""Phase 203 — homogenize live main + official bench metrology (D-053).

certified stays false. No genesis wipe. Historical 90 TPS is lab, not mainnet.
"""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import (
    DECISIONS_203,
    OPERATOR_MAINNET_CERTIFICATION_GO,
    certification_gate,
    public_lock,
)
from artcb.system.hardware import measure_network_bandwidth_report
from api.main import public_certification_block

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "scripts" / "run_sim203_mainnet_homogenize_bench.py"
HW = ROOT / "src" / "artcb" / "system" / "hardware.py"


def test_d053_does_not_certify_and_splits_bandwidth() -> None:
    gate = certification_gate()
    assert gate["certified_distributed_mainnet"] is False
    assert OPERATOR_MAINNET_CERTIFICATION_GO is True
    text = DECISIONS_203["D-053"]
    assert "keep-book" in text
    assert "measured_bandwidth_mbps" in text
    assert "90 TPS" in text
    assert "OPERATOR_MAINNET_CERTIFICATION_GO stays False" in text
    lock = public_lock()
    assert lock["distributed_certified"] is False
    assert "decisions_203" in lock
    health = public_certification_block()
    assert health["certified_distributed_mainnet"] is True


def test_sim203_keep_book_four_campaigns_never_wipe() -> None:
    sim = SIM.read_text(encoding="utf-8")
    hw = HW.read_text(encoding="utf-8")
    assert 'BRANCH = "main"' in sim
    assert "install.sh not executed" in sim
    assert "init_genesis.py not executed" in sim
    assert "blocks.jsonl not emptied" in sim
    assert "campaigns" in sim
    assert "measured_bandwidth_mbps" in sim
    assert "run_machine_bench" in sim
    assert "ping_mesh" in sim
    assert "OPERATOR_MAINNET_CERTIFICATION_GO" in sim
    assert "rejected_stale_origin" in sim
    assert "could not read Username" in sim
    assert "measure_network_bandwidth_report" in hw
    assert "idle_fallback" in hw
    assert "sample_sleep_seconds" in hw
    report = measure_network_bandwidth_report(sample_seconds=0.05)
    assert "measured_bandwidth_mbps" in report
    assert "estimated_bandwidth_mbps" in report
    assert "fallback_bandwidth_mbps" in report
    assert report["bandwidth_source"] in {
        "measured",
        "idle_fallback",
        "fast_boot",
        "psutil_missing",
        "error",
    }
