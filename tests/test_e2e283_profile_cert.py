"""R283 — environment-first profile certification. L4 is not a universal gate."""

from __future__ import annotations

from src.artcb.consensus.platform_attest import collect_platform_attestation, evaluate_node_platform_binding


def test_ovh_l2_profile_pass_l4_not_applicable() -> None:
    snap = collect_platform_attestation(
        declared_node_id="ovh-node-1",
        attestation_public_key="u3WrGfKSYatkntc6ctlZqDyHI/98yV2PfJ8FTC/IXSU=",
        tpm={"present": False, "quote": None},
        virt={"is_vm": True, "hostname": "n1", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": True, "uuid": "f2642e42-323c-4621-b0e8-a82ffb20f184"},
    )
    assert snap["environment"] == "CLOUD_VM"
    assert snap["maximum_supported_level"] == 2
    assert snap["attested_level"] == 2
    assert snap["l3"] == "NOT_REACHABLE"
    assert snap["l4"] == "NOT_APPLICABLE"
    assert snap["hardware_tpm_attestation"] == "NOT_APPLICABLE"
    assert snap["profile_certification"] == "PASS"
    assert snap["split_verdicts"]["certification"] == "PASS"
    assert snap["profile_certified_100"] is False
    assert snap["certified_hardware_identity"] is False


def test_aws_l3_quote_is_partial_not_l4() -> None:
    snap = collect_platform_attestation(
        declared_node_id="aws-node-3",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
        tpm={
            "present": True,
            "quote": {"verified": True, "kind": "vtpm", "ek_manufacturer_verified": False},
        },
        virt={"is_vm": True, "hostname": "n3", "machine_id": "m", "dmi_uuid": "d"},
        aws={
            "document_ok": True,
            "instance_id": "i-06c9404e42798ff76",
            "instance_type": "t3.small",
            "region": "eu-west-3",
        },
        ovh={"document_ok": False},
    )
    assert snap["environment"] == "CLOUD_VM"
    assert snap["environment_profile"] == "CLOUD_VM_VTPM"
    assert snap["maximum_supported_level"] == 3
    assert snap["attested_level"] == 3
    assert snap["overall_platform_trust"] == "VTPM_ATTESTED"
    assert snap["l3"] == "PASS"
    assert snap["l4"] == "NOT_APPLICABLE"
    assert snap["hardware_tpm_attestation"] == "NOT_APPLICABLE"
    assert snap["certified_hardware_identity"] is False
    assert snap["attestation_crypto_verified"] is True
    assert snap["quote_freshness"] == "NOT_PROVEN"
    assert snap["ek_ak_provenance"] == "NOT_PROVEN"
    assert snap["profile_certification"] == "PARTIAL"
    assert snap["profile_certified_100"] is False
    assert snap["split_verdicts"]["certification"] != "FAIL"


def test_l3_freshness_and_ek_do_not_imply_certified_100() -> None:
    snap = collect_platform_attestation(
        declared_node_id="aws-node-3",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
        tpm={
            "present": True,
            "quote": {
                "verified": True,
                "kind": "vtpm",
                "freshness_bound": True,
                "binding_prefix_hex": "ab" * 16,
                "ek_manufacturer_verified": False,
            },
        },
        virt={"is_vm": True, "hostname": "n3", "machine_id": "abc", "dmi_uuid": "x"},
        aws={
            "document_ok": True,
            "instance_id": "i-06c9404e42798ff76",
            "region": "eu-west-3",
        },
        ovh={"document_ok": False},
    )
    assert snap["quote_freshness"] == "PASS"
    assert snap["quote_node_binding"] == "PASS"
    assert snap["ek_ak_provenance"] == "NOT_PROVEN"
    assert snap["profile_certification"] == "PARTIAL"
    assert snap["profile_certified_100"] is False
    assert snap["l4"] == "NOT_APPLICABLE"


def test_identity_mismatch_fails_profile() -> None:
    snap = collect_platform_attestation(
        declared_node_id="ovh-node-4",
        attestation_public_key="fiXJqTRUFuDYPQkh8q8UuzilVyK8sshJANQkDmfjNBs=",
        tpm={"present": False, "quote": None},
        virt={"is_vm": True, "hostname": "n4", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": True, "uuid": "6470522e-1561-4741-9254-5f58b909eeb9"},
    )
    assert snap["binding"]["identity_mismatch"] is True
    assert snap["profile_certification"] == "FAIL"
    assert snap["split_verdicts"]["certification"] == "FAIL"
    assert snap["l4"] == "NOT_APPLICABLE"


def test_vm_cannot_be_l4_even_with_quote() -> None:
    snap = collect_platform_attestation(
        declared_node_id="lab-vm",
        attestation_public_key="k",
        tpm={"present": True, "quote": {"verified": True, "kind": "vtpm"}},
        virt={"is_vm": True, "hostname": "kvm", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert snap["trust_level"] == 3
    assert snap["certified_hardware_identity"] is False
    assert snap["l4"] == "NOT_APPLICABLE"
    assert snap["hardware_tpm_attestation"] == "NOT_APPLICABLE"
    assert snap["split_verdicts"]["l4"] == "NOT_APPLICABLE"


def test_binding_helper_still_matches_aws3() -> None:
    bind = evaluate_node_platform_binding(
        declared_node_id="aws-node-3",
        observed_instance_id="i-06c9404e42798ff76",
        observed_provider="aws",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
    )
    assert bind["binding_verified"] is True
    assert bind["identity_mismatch"] is False
