"""Phase 173 — D-032 crypto policy B + OVH2 identity. No secrets."""

from __future__ import annotations

from pathlib import Path

from artcb.crypto_policy import (
    ED25519_ONLY_UNTIL,
    PREFERRED_SIG,
    accept_peer_suite,
    capabilities,
    fallback_still_open,
)
from artcb.devnet_validation import DV, ECONOMIC_V, PROFILE
from artcb.node_registry import NODES


def test_economic_v_series_not_overwritten() -> None:
    assert "Snapshot at epoch start" in ECONOMIC_V["V-01"]
    assert DV["DV-01"]["letter"] == "C"
    assert DV["DV-03"]["letter"] == "B"
    assert DV["DV-07"]["letter"] == "C"
    assert PROFILE.startswith("B")
    assert ECONOMIC_V["V-07"]


def test_policy_b_prefers_mldsa_and_allows_ed25519_for_now() -> None:
    assert PREFERRED_SIG == "ML-DSA-65"
    assert fallback_still_open() is True
    assert ED25519_ONLY_UNTIL.startswith("2026-12-31")
    cap = capabilities(True)
    assert cap["local_suite"].startswith("hybrid:")
    assert cap["anti_downgrade"] is True
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
    script = Path(__file__).resolve().parents[1] / "scripts" / "deploy_ovh2.sh"
    body = script.read_text(encoding="utf-8")
    assert "152.228.144.34 n'a PAS été modifié" in body
    assert "Refusing to deploy OVH2 script onto OVH1" in body
