"""R284 — UNKNOWN ≠ BARE_METAL; swtpm ≠ L3; CERTIFIED_100 denominator."""

from __future__ import annotations

from src.artcb.consensus.platform_attest import collect_platform_attestation, parse_tpm2_properties
from src.artcb.consensus.tpm_kind import KIND_SOFTWARE, KIND_UNKNOWN, classify_tpm_kind
from src.artcb.trace.agent_run import AgentRunLedger, policy_hash


def test_unknown_virt_is_not_bare_metal() -> None:
    snap = collect_platform_attestation(
        declared_node_id="ghost",
        attestation_public_key="",
        tpm={"present": False, "quote": None},
        virt={"is_vm": False, "environment_certainty": "UNKNOWN", "hostname": "x"},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert snap["environment"] == "UNKNOWN"
    assert snap["environment_certainty"] == "UNKNOWN"
    assert snap["environment_profile"] == "UNKNOWN"
    assert snap["certified_hardware_identity"] is False
    assert snap["maximum_verified_level"] == 0
    assert snap["l4"] == "NOT_PROVEN"
    assert snap["profile_certification"] == "NOT_PROVEN"


def test_swtpm_never_grants_l3() -> None:
    snap = collect_platform_attestation(
        declared_node_id="aws-node-3",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
        tpm={
            "present": True,
            "software_tpm": True,
            "manufacturer": "SW",
            "vendor": "swtpm",
            "quote": {"verified": True, "kind": "vtpm"},
        },
        virt={"is_vm": True, "environment_certainty": "VM_PROVEN", "hostname": "n3"},
        aws={
            "document_ok": True,
            "instance_id": "i-06c9404e42798ff76",
            "region": "eu-west-3",
        },
        ovh={"document_ok": False},
    )
    assert snap["tpm_kind"] == KIND_SOFTWARE
    assert snap["trust_level"] == 2
    assert snap["maximum_theoretical_level"] == 2
    assert snap["maximum_verified_level"] == 2
    assert snap["l3"] == "NOT_APPLICABLE"
    assert snap["certified_hardware_identity"] is False
    assert snap["attestation_crypto_verified"] is False
    assert snap["overall_platform_trust_precise"] == "CLOUD_IDENTITY_OBSERVED"


def test_device_present_alone_is_unknown_not_l3() -> None:
    kind = classify_tpm_kind(
        tpm={"present": True},
        virt={"is_vm": True, "environment_certainty": "VM_PROVEN"},
    )
    assert kind == KIND_UNKNOWN
    snap = collect_platform_attestation(
        declared_node_id="lab-vm",
        attestation_public_key="k",
        tpm={"present": True, "quote": {"verified": True, "kind": "vtpm"}},
        virt={"is_vm": True, "environment_certainty": "VM_PROVEN", "hostname": "kvm"},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert snap["tpm_kind"] == KIND_UNKNOWN
    assert snap["trust_level"] <= 2
    assert snap["maximum_verified_level"] <= 2
    assert snap["l3"] != "PASS"


def test_nitrotpm_quote_is_l3_not_l4() -> None:
    snap = collect_platform_attestation(
        declared_node_id="aws-node-3",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
        tpm={
            "present": True,
            "manufacturer": "AMZN",
            "vendor": "NitroTPM v1.0",
            "quote": {"verified": True, "kind": "vtpm", "freshness_bound": True, "binding_prefix_hex": "ab" * 16},
        },
        virt={"is_vm": True, "environment_certainty": "VM_PROVEN", "hostname": "n3"},
        aws={"document_ok": True, "instance_id": "i-06c9404e42798ff76", "region": "eu-west-3"},
        ovh={"document_ok": False},
    )
    assert snap["tpm_kind"] == "NITROTPM"
    assert snap["environment_profile"] == "CLOUD_VM_VTPM"
    assert snap["trust_level"] == 3
    assert snap["maximum_theoretical_level"] == 3
    assert snap["maximum_verified_level"] == 3
    assert snap["l4"] == "NOT_APPLICABLE"
    assert snap["freshness_kind"] == "LOCAL_GENERATED"
    assert "ek_ak_provenance" in snap["missing_requirements"] or snap["ek_provenance_verified"] == "NOT_PROVEN"
    assert snap["profile_certified_100"] is False
    assert snap["policy_id"] == "284-environment-classification"
    assert snap["policy_hash"] == policy_hash()


def test_not_reachable_does_not_count_as_certified() -> None:
    snap = collect_platform_attestation(
        declared_node_id="ovh-baremetal-1",
        attestation_public_key="ak",
        tpm={"present": False, "quote": None},
        virt={"is_vm": False, "bare_metal_proven": True, "environment_certainty": "BARE_METAL_PROVEN", "hostname": "dell"},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert snap["environment"] == "BARE_METAL"
    assert snap["l4"] == "NOT_REACHABLE"
    assert snap["profile_certified_100"] is False
    assert "hardware_tpm_present" in snap["missing_requirements"]


def test_parse_amzn_properties() -> None:
    got = parse_tpm2_properties(
        "TPM2_PT_MANUFACTURER:\n  raw: 0x414D5A4E\n  value: AMZN\n"
        "TPM2_PT_VENDOR_STRING_1:\n  value: Nitro\n"
        "TPM2_PT_VENDOR_STRING_2:\n  value: TPM\n"
    )
    assert got["manufacturer"] == "AMZN"
    assert "Nitro" in got["vendor"]


def test_agent_run_hash_chain_breaks_on_tamper() -> None:
    led = AgentRunLedger(run_id="AR-284-TEST", agent_id="cursor", prompt_hash="abc", code_sha="0" * 40)
    led.add("INPUT_RECEIVED", status="PASS")
    led.add("TEST_EXECUTED", status="PASS", output_hash="d")
    tip = led.events[-1]["chain_hash"]
    led.events[0]["status"] = "TAMPER"
    rebuilt = AgentRunLedger(run_id="AR-284-TEST", agent_id="cursor", prompt_hash="abc", code_sha="0" * 40)
    for ev in led.events:
        rebuilt.add(ev["action"], status=ev["status"], output_hash=ev.get("output_hash") or "")
    assert rebuilt.events[-1]["chain_hash"] != tip
