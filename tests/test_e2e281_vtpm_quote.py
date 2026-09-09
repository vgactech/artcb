"""R281 — vTPM/TPM quote fail-closed. Guest swtpm is not hypervisor vTPM."""

from __future__ import annotations

from src.artcb.consensus.platform_attest import collect_platform_attestation, quote_present
from src.artcb.consensus.tpm_quote import attempt_attestation_quote, tpm_device_present


def test_quote_present_requires_verified() -> None:
    assert quote_present({"quote": None}) is False
    assert quote_present({"quote": {"ok": False, "reason": "DEVICE_ABSENT"}}) is False
    assert quote_present({"quote": {"verified": False, "reason": "QUOTE_FAILED"}}) is False
    assert quote_present({"quote": {"verified": True}}) is True


def test_attempt_quote_device_absent_on_this_runner() -> None:
    if tpm_device_present():
        return
    got = attempt_attestation_quote(extra_data=b"\x11" * 32, is_vm=True)
    assert got["verified"] is False
    assert got["reason"] == "DEVICE_ABSENT"
    assert got["quote"] is None
    assert got["kind"] == "vtpm"


def test_verified_vtpm_quote_is_l3_not_l4() -> None:
    snap = collect_platform_attestation(
        declared_node_id="lab-vm",
        attestation_public_key="k",
        tpm={"present": True, "quote": {"verified": True, "kind": "vtpm"}},
        virt={"is_vm": True, "hostname": "kvm", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert snap["platform_class"] == "vtpm"
    assert snap["trust_level"] == 3
    assert snap["overall_platform_trust"] == "VTPM_ATTESTED"
    assert snap["hardware_tpm_attestation"] == "NOT_APPLICABLE"
    assert snap["certified_hardware_identity"] is False
    assert snap["environment"] == "VM"
    assert snap["environment_profile"] == "VM_VTPM"
    assert snap["maximum_supported_level"] == 3
    assert snap["l3"] == "PASS"
    assert snap["l4"] == "NOT_APPLICABLE"
    assert snap["split_verdicts"]["platform_crypto_attestation"] == "PASS"
    assert snap["split_verdicts"]["certification"] == "PARTIAL"
    assert snap["profile_certified_100"] is False


def test_live_vms_without_device_stay_l2_not_l3() -> None:
    snap = collect_platform_attestation(
        declared_node_id="ovh-node-1",
        attestation_public_key="u3WrGfKSYatkntc6ctlZqDyHI/98yV2PfJ8FTC/IXSU=",
        tpm={"present": False, "quote": None},
        virt={"is_vm": True, "hostname": "n1", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": True, "uuid": "f2642e42-323c-4621-b0e8-a82ffb20f184"},
    )
    assert snap["trust_level"] == 2
    assert snap["overall_platform_trust"] == "CLOUD_ATTESTED"
    assert (snap.get("tpm") or {}).get("quote", {}).get("reason") == "DEVICE_ABSENT"
    assert snap["split_verdicts"]["platform_crypto_attestation"] == "NOT_PROVEN"
    assert snap["l3"] == "NOT_REACHABLE"
    assert snap["l4"] == "NOT_APPLICABLE"
    assert snap["split_verdicts"]["certification"] == "PASS"
    assert snap["profile_certified_100"] is False
