"""Phase 173 — D-032 crypto policy B + OVH2 identity. No secrets."""

from __future__ import annotations

import ast
from pathlib import Path

from artcb.crypto_policy import (
    ED25519_ONLY_UNTIL,
    GENESIS_HASH,
    NETWORK_ID,
    PREFERRED_SIG,
    PROTOCOL_VERSION,
    accept_peer_suite,
    capabilities,
    fallback_still_open,
)
from artcb.devnet_validation import DV, ECONOMIC_V, PROFILE
from artcb.node_registry import NODES, secret_belongs_on_node

ROOT = Path(__file__).resolve().parents[1]


def test_economic_v_series_not_overwritten() -> None:
    assert "Snapshot at epoch start" in ECONOMIC_V["V-01"]
    assert DV["DV-01"]["letter"] == "C"
    assert DV["DV-03"]["letter"] == "B"
    assert DV["DV-07"]["letter"] == "C"
    assert PROFILE.startswith("B")
    assert ECONOMIC_V["V-07"]


def test_policy_b_prefers_mldsa_and_allows_ed25519_for_now() -> None:
    assert PREFERRED_SIG == "ML-DSA-65"
    assert NETWORK_ID == "artcb-devnet-1"
    assert PROTOCOL_VERSION == "173-devnet-1"
    assert GENESIS_HASH == "genesis-artcb-v2"
    assert fallback_still_open() is True
    assert ED25519_ONLY_UNTIL.startswith("2026-12-31")
    cap = capabilities(True)
    assert cap["local_suite"].startswith("hybrid:")
    assert cap["anti_downgrade"] is True
    assert cap["protocol_version"] == PROTOCOL_VERSION
    assert cap["genesis_hash"] == GENESIS_HASH
    ok, reason = accept_peer_suite(advertised="Ed25519", previously_seen=None, pqc_available_here=True)
    assert ok is True
    assert "temporary" in reason
    ok2, reason2 = accept_peer_suite(
        advertised="Ed25519",
        previously_seen="hybrid:ed25519+ML-DSA-65",
        pqc_available_here=True,
    )
    assert ok2 is False
    assert "anti_downgrade" in reason2
    ok3, _ = accept_peer_suite(advertised="ML-DSA-65", previously_seen=None, pqc_available_here=False)
    assert ok3 is True


def test_ovh2_has_live_identity() -> None:
    n2 = NODES["ovh-node-2"]
    assert n2.ssh_host == "151.80.107.29"
    assert "1fc10a3fb27d4511a8c7873cd16243f2" in n2.public_notes
    assert n2.doppler_project == "artcb-2"
    assert NODES["ovh-node-1"].ssh_host == "152.228.144.34"
    assert secret_belongs_on_node("ovh-node-2", "ARTCB_WALLET_PASSPHRASE")
    script = ROOT / "scripts" / "deploy_ovh2.sh"
    body = script.read_text(encoding="utf-8")
    assert "152.228.144.34 n'a PAS été modifié" in body
    assert "Refusing to deploy OVH2 script onto OVH1" in body


def test_api_main_parses_after_bootstrap_health_indent_fix() -> None:
    source = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "genesis_hash" in source
    assert "PROTOCOL_VERSION" in source


def test_init_and_rotate_scripts_never_echo_secrets() -> None:
    init = (ROOT / "scripts" / "init_remote_node.sh").read_text(encoding="utf-8")
    rotate = (ROOT / "scripts" / "rotate_aws_access_keys.py").read_text(encoding="utf-8")
    sim = (ROOT / "scripts" / "run_sim173_ovh2_pqc.py").read_text(encoding="utf-8")
    assert "Never prints seed" in init
    assert "body.pop(\"seed_hex\"" in init or "body.pop('seed_hex'" in init
    assert "secrets_printed" in rotate
    assert "152.228.144.34" in sim
    assert "Does not redeploy OVH1" in sim
