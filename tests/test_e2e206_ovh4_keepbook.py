"""Phase 206 — OVH4 SSH without rescue + keep-book origin/main.

Certification stays false. No genesis wipe. No rescue disk.
"""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import OPERATOR_MAINNET_CERTIFICATION_GO, certification_gate
from artcb.node_registry import NODES

ROOT = Path(__file__).resolve().parents[1]


def test_ovh4_registry_and_new_pubkey_comment() -> None:
    spec = NODES["ovh-node-4"]
    assert spec.doppler_project == "artcb-4"
    assert spec.doppler_token_env == "KEY_API_ARTCB_DOPPLER_4"
    assert spec.ssh_host == "91.134.45.8"
    pub = (ROOT / "deploy" / "artcb_ovh_node_4.pub").read_text(encoding="utf-8")
    assert pub.startswith("ssh-ed25519 ")
    assert "artcb-ovh-node-4-20260902" in pub
    assert spec.ssh_host != NODES["ovh-node-1"].ssh_host
    assert spec.ssh_host != NODES["ovh-node-2"].ssh_host


def test_inject_script_forbids_rescue_and_never_prints_pem() -> None:
    script = (ROOT / "scripts" / "inject_ssh_no_rescue.py").read_text(encoding="utf-8")
    assert "FORBID_RESCUE" in script
    assert "rescueMode" not in script
    assert "Never prints PEM" in script
    assert "KEY_API_ARTCB_DOPPLER_4" in script
    assert "load_node_ssh_keys.py" in script
    deploy = (ROOT / "scripts" / "deploy_ovh4.sh").read_text(encoding="utf-8")
    assert "Refusing to deploy OVH4 script onto OVH1" in deploy
    assert "Refusing to deploy OVH4 script onto OVH2" in deploy
    loader = (ROOT / "scripts" / "load_node_ssh_keys.py").read_text(encoding="utf-8")
    assert "KEY_API_ARTCB_DOPPLER_4" in loader
    assert "artcb-4" in loader


def test_keep_book_never_wipes_and_does_not_certify() -> None:
    sim = (ROOT / "scripts" / "run_sim203_mainnet_homogenize_bench.py").read_text(encoding="utf-8")
    assert "install.sh not executed" in sim
    assert "init_genesis.py not executed" in sim
    assert "blocks.jsonl not emptied" in sim
    gate = certification_gate()
    assert gate["certified_distributed_mainnet"] is False
    assert OPERATOR_MAINNET_CERTIFICATION_GO is False
    report = (ROOT / "rapports" / "206_ovh4_ssh_keepbook_2026-09-02.md").read_text(encoding="utf-8")
    assert "ad017bca05c2e3799c7dcd120ca1797968d499b6" in report
    assert "91.134.45.8" in report
    assert "sans rescue" in report.lower() or "without rescue" in report.lower()
    assert "NOT MAINNET CERTIFIED" in report
    assert "n4.artcb.me" in report
