"""Phase 192 — hardware A–E, ovh-baremetal-1 slot, OVH3 quote without inventing credit."""

from __future__ import annotations

from pathlib import Path

from api.main import REPLIT_CORS_ORIGIN_REGEX
from artcb.devnet_validation import DECISIONS_192, certification_gate, public_lock
from artcb.node_registry import NODES, secret_belongs_on_node
from artcb.p2p.public_url import peer_host_is_stale_link_local
from artcb.security.hardware_identity import (
    HARDWARE_ASSURANCE_LEVELS,
    classify_hardware_assurance,
    public_machine_view,
    tpm_sysfs_facts,
)

ROOT = Path(__file__).resolve().parents[1]


def test_assurance_levels_a_to_e_are_honest() -> None:
    assert set(HARDWARE_ASSURANCE_LEVELS) == {"A", "B", "C", "D", "E"}
    physical = classify_hardware_assurance(
        tpm_device_present=True, chassis_virtual=False
    )
    assert physical["hardware_assurance_level"] == "A"
    assert physical["tpm_kind"] == "physical"
    assert physical["invented"] is False
    vtpm = classify_hardware_assurance(tpm_device_present=True, chassis_virtual=True)
    assert vtpm["hardware_assurance_level"] == "B"
    assert vtpm["tpm_kind"] == "virtual"
    tee = classify_hardware_assurance(
        tpm_device_present=False, chassis_virtual=True, tee_kind="sev"
    )
    assert tee["hardware_assurance_level"] == "C"
    hsm = classify_hardware_assurance(
        tpm_device_present=False, chassis_virtual=True, hsm_bound=True
    )
    assert hsm["hardware_assurance_level"] == "D"
    software = classify_hardware_assurance(
        tpm_device_present=False, chassis_virtual=True
    )
    assert software["hardware_assurance_level"] == "E"
    assert software["tpm_kind"] == "absent"
    assert software["hardware_kind"] == "software"


def test_absent_tpm_never_becomes_nitro_or_sev() -> None:
    facts = tpm_sysfs_facts()
    view = public_machine_view(None)
    assert "hardware_assurance_level" in view
    assert view["hardware_assurance_level"] in HARDWARE_ASSURANCE_LEVELS
    if not facts["tpm_device_present"]:
        assert view["tpm_device_present"] is False
        assert view["tpm_kind"] == "absent"
        assert view["hardware_assurance_level"] not in {"A", "B"}
        assert view["tee_detected"] is False or view["tee_kind"] in {"sev", "sgx", "tdx", "nitro_enclaves"}
        if not view["tee_detected"] and not view["hsm_bound"]:
            assert view["hardware_assurance_level"] == "E"
            assert view["pcr0_sha256"] is None


def test_ovh_baremetal_slot_is_not_ovh1() -> None:
    spec = NODES["ovh-baremetal-1"]
    assert spec.node_id == "ovh-baremetal-1"
    assert spec.node_id != "ovh-node-1"
    assert spec.ssh_host != "152.228.144.34"
    assert spec.ssh_host != "91.134.45.8"
    assert spec.doppler_project == "artcb-baremetal-1"
    assert spec.doppler_token_env == "KEY_API_ARTCB_DOPPLER_BAREMETAL"
    assert spec.provider == "ovh-baremetal"
    assert "152.228.144.34" not in spec.public_notes or "Never reuse" in spec.public_notes
    assert NODES["ovh-node-1"].ssh_host == "152.228.144.34"
    assert secret_belongs_on_node("ovh-baremetal-1", "OVH3_APPLICATION_KEY")
    assert not secret_belongs_on_node("ovh-baremetal-1", "KEY_API_STRIPE")


def test_cors_regex_has_no_named_replit_account() -> None:
    assert REPLIT_CORS_ORIGIN_REGEX == r"https://.*\.(replit\.app|repl\.co|replit\.dev)"
    main = (ROOT / "src" / "api" / "main.py").read_text(encoding="utf-8")
    cfg = (ROOT / "src" / "artcb" / "config.py").read_text(encoding="utf-8")
    assert "vgacofficiel.replit" not in main
    assert "vgac42371" not in main
    assert "vgacofficiel.replit" not in cfg
    assert "allow_origin_regex=REPLIT_CORS_ORIGIN_REGEX" in main


def test_stale_169254_is_recognized() -> None:
    assert peer_host_is_stale_link_local("169.254.169.254") is True
    assert peer_host_is_stale_link_local("152.228.144.34") is False
    assert peer_host_is_stale_link_local("demo-app--someuser.replit.app") is False


def test_quote_script_does_not_invent_ten_euros() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from ovh_baremetal_quote import measure_ovh3_credit, quote

    credit = measure_ovh3_credit()
    assert credit["invented"] is False
    assert credit.get("balance_eur") is None
    assert credit.get("ok") is False
    quoted = quote(want_order=True)
    assert quoted["invented_balance"] is False
    assert quoted["order"]["executed"] is False
    cheapest = quoted["selected"]
    assert cheapest is not None
    assert cheapest["planCode"] == "25skb012"
    assert cheapest["price_eur"] == 9.99


def test_d046_keeps_certification_false() -> None:
    assert "D-046" in DECISIONS_192
    assert "OVH3_APPLICATION_KEY" in DECISIONS_192["D-046"]
    lock = public_lock()
    assert "decisions_192" in lock
    gate = certification_gate(
        {
            "DV-01": "PASS",
            "DV-02": "PASS",
            "DV-03": "PASS",
            "DV-04": "PASS",
            "DV-05": "PASS",
            "DV-06": "PASS",
            "DV-07": "PASS",
        }
    )
    assert gate["certified_distributed_mainnet"] is False


def test_sim192_forbids_wipe_and_replit_hosts() -> None:
    sim = (ROOT / "scripts" / "run_sim192_hw_baremetal.py").read_text(encoding="utf-8")
    assert "install.sh" in sim
    assert "init_genesis.py" in sim
    assert "init-node" in sim
    assert "vgac42371" not in sim
    assert "vgacofficiel" not in sim
    assert "Never invent" in sim
