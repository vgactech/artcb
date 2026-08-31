"""Phase 175 — OVH4 identity, isolation, deploy guards. No secrets."""

from __future__ import annotations

from pathlib import Path

from artcb.devnet_validation import DECISIONS_174, DECISIONS_175, DV
from artcb.node_registry import NODES, SHARED_DOPPLER_PROJECT, secret_belongs_on_node, secret_must_stay_shared

ROOT = Path(__file__).resolve().parents[1]


def test_four_isolated_doppler_projects() -> None:
    projects = {spec.doppler_project for spec in NODES.values()}
    assert projects == {
        SHARED_DOPPLER_PROJECT,
        "artcb-2",
        "artcb3",
        "artcb-4",
    }
    assert NODES["ovh-node-4"].doppler_project == "artcb-4"
    assert NODES["ovh-node-4"].doppler_token_env == "KEY_API_ARTCB_DOPPLER_4"
    assert NODES["ovh-node-4"].provider == "ovh"
    assert "926bb1d6755e4f2c98ae9db06ef44e4f" in NODES["ovh-node-4"].public_notes
    assert "xy4589-ovh" in NODES["ovh-node-4"].public_notes
    assert NODES["ovh-node-1"].ssh_host == "152.228.144.34"
    assert NODES["ovh-node-2"].ssh_host == "151.80.107.29"
    assert NODES["ovh-node-4"].ssh_host == "91.134.45.8"
    assert NODES["ovh-node-4"].ssh_host != "152.228.144.34"
    assert NODES["ovh-node-4"].ssh_host != "151.80.107.29"


def test_ovh4_secrets_stay_on_node_and_stripe_stays_shared() -> None:
    assert secret_belongs_on_node("ovh-node-4", "OVH_APPLICATION_SECRET")
    assert secret_belongs_on_node("ovh-node-4", "ARTCB_WALLET_PASSPHRASE")
    assert not secret_belongs_on_node("ovh-node-4", "KEY_API_STRIPE")
    assert secret_must_stay_shared("KEY_API_STRIPE")
    assert secret_must_stay_shared("BOB_API_KEY")


def test_d037_does_not_overwrite_d033_or_d034() -> None:
    assert DV["DV-04"]["letter"] == "C"
    assert DECISIONS_174["D-034"].startswith("A")
    assert "OVH1" in DECISIONS_174["D-036"]
    assert "NODE4" in DECISIONS_175["D-037"]
    assert "174-devnet-1" in DECISIONS_175["D-037"]
    assert "5b4b24ae" in DECISIONS_175["D-037"]


def test_deploy_ovh4_refuses_ovh1_and_ovh2() -> None:
    body = (ROOT / "scripts" / "deploy_ovh4.sh").read_text(encoding="utf-8")
    assert "Refusing to deploy OVH4 script onto OVH1" in body
    assert "Refusing to deploy OVH4 script onto OVH2" in body
    assert "artcb-4" in body
    assert "ovh-node-4" in body
    assert "152.228.144.34 n'a PAS été modifié" in body
    prov = (ROOT / "scripts" / "provision_ovh4_instance.py").read_text(encoding="utf-8")
    assert "926bb1d6755e4f2c98ae9db06ef44e4f" in prov
    assert "Never falls back to process OVH_*" in prov
    assert "152.228.144.34" in prov
    init = (ROOT / "scripts" / "init_remote_node.sh").read_text(encoding="utf-8")
    assert "Never prints seed" in init
    sim = (ROOT / "scripts" / "run_sim175_ovh4_node.py").read_text(encoding="utf-8")
    assert "Does not redeploy OVH1" in sim
    assert "DV-04 FINAL stays BLOCKED" in sim
    assert "152.228.144.34" in sim
