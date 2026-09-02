"""Phase 207 — official nodes and clones follow GitHub origin/main automatically.

Keep-book only. Certification stays false. PR #51 rescue must stay out of main.
"""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import OPERATOR_MAINNET_CERTIFICATION_GO, certification_gate
from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS, PUBLIC_HEALTH_URLS

ROOT = Path(__file__).resolve().parents[1]


def test_four_official_compute_nodes_and_public_health() -> None:
    assert OFFICIAL_COMPUTE_NODE_IDS == (
        "ovh-node-1",
        "ovh-node-2",
        "aws-node-3",
        "ovh-node-4",
    )
    assert NODES["ovh-node-1"].ssh_host == "152.228.144.34"
    assert NODES["ovh-node-2"].ssh_host == "151.80.107.29"
    assert NODES["aws-node-3"].ssh_host == "51.44.222.232"
    assert NODES["ovh-node-4"].ssh_host == "91.134.45.8"
    assert PUBLIC_HEALTH_URLS["ovh-node-1"] == "https://artcb.me/health"
    assert PUBLIC_HEALTH_URLS["ovh-node-2"] == "https://n2.artcb.me/health"
    assert PUBLIC_HEALTH_URLS["aws-node-3"] == "https://n3.artcb.me/health"
    assert PUBLIC_HEALTH_URLS["ovh-node-4"] == "https://n4.artcb.me/health"


def test_follow_main_script_keep_book_and_modes() -> None:
    script = (ROOT / "scripts" / "artcb_follow_main.sh").read_text(encoding="utf-8")
    assert "blocks.jsonl not emptied" in script
    assert "install.sh not executed" in script
    assert "init_genesis.py not executed" in script
    assert "rescue not used" in script
    assert "reset --hard" in script
    assert "merge --ff-only" in script
    assert "FETCH_METHOD=tarball" in script
    assert "credential.helper=" in script
    assert "http.version=HTTP/1.1" in script
    assert "ARTCB_FOLLOW_MODE=official" in script or 'MODE="official"' in script
    assert "clone tree dirty" in script
    timer = (ROOT / "scripts" / "artcb-follow-main.timer").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=5min" in timer
    service = (ROOT / "scripts" / "artcb-follow-main.service").read_text(encoding="utf-8")
    assert "ARTCB_FOLLOW_MODE=official" in service
    assert "artcb_follow_main.sh" in service


def test_install_sh_wires_follow_main_for_new_clones() -> None:
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "install_follow_main.sh" in install
    assert "Suivi automatique de GitHub origin/main" in install
    helper = (ROOT / "scripts" / "install_follow_main.sh").read_text(encoding="utf-8")
    assert "artcb-follow-main.timer" in helper
    assert "artcb_follow_main.sh" in helper
    assert "ff-only" in helper
    sync = (ROOT / "scripts" / "artcb_sync_official_nodes.py").read_text(encoding="utf-8")
    assert "PR #51 rescue not merged" in sync
    assert "blocks.jsonl not emptied" in sync
    assert "--install" in sync


def test_follow_main_does_not_certify_and_rapport_has_live_sha() -> None:
    gate = certification_gate()
    assert gate["certified_distributed_mainnet"] is False
    assert OPERATOR_MAINNET_CERTIFICATION_GO is False
    report = (ROOT / "rapports" / "207_follow_main_all_nodes_2026-09-02.md").read_text(encoding="utf-8")
    assert "NOT MAINNET CERTIFIED" in report
    assert "ad017bca05c2e3799c7dcd120ca1797968d499b6" in report
    assert "152.228.144.34" in report
    assert "151.80.107.29" in report
    assert "51.44.222.232" in report
    assert "91.134.45.8" in report
    assert "PR #51" in report
    assert "sans rescue" in report.lower() or "not merged" in report.lower()
    docs = (ROOT / "docs" / "FOLLOW_MAIN.md").read_text(encoding="utf-8")
    assert "artcb_follow_main.sh" in docs
    assert "install.sh" in docs
