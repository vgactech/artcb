"""R279 — multi-level platform trust + honest block_size_bytes."""

from __future__ import annotations

import json

from src.artcb.chain.manager import (
    ChainBlock,
    encode_jsonl_with_converged_size,
    measure_jsonl_sizes,
)
from src.artcb.consensus.platform_attest import (
    collect_platform_attestation,
    evaluate_node_platform_binding,
    node_binding_digest,
    override_platform_binding,
)


def _cloud_aws(**extra):
    base = {
        "document_ok": True,
        "pkcs7_present": True,
        "pkcs7_verified": False,
        "instance_id": "i-085b74abd1aaf04ee",
        "instance_type": "t3.small",
        "region": "eu-west-3",
    }
    base.update(extra)
    return base


def test_cloud_vm_is_l2_not_tpm() -> None:
    snap = collect_platform_attestation(
        declared_node_id="aws-node-3",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
        tpm={"present": False, "quote": None, "verdict": "ABSENT"},
        virt={"is_vm": True, "hostname": "n3", "machine_id": "abc", "dmi_uuid": "x"},
        aws=_cloud_aws(),
        ovh={"document_ok": False},
    )
    assert snap["platform_class"] == "cloud_instance_identity"
    assert snap["trust_level"] == 2
    assert snap["overall_platform_trust"] == "CLOUD_ATTESTED"
    assert snap["hardware_tpm_attestation"] == "NOT_AVAILABLE"
    assert snap["platform_identity_attestation"] == "AWS_CLOUD_ATTESTED"
    assert snap["certified_hardware_identity"] is False
    assert snap["tpm_quote_proven"] is False
    assert snap["attestation_crypto_verified"] is False
    v = snap["split_verdicts"]
    assert v["platform_level_observed"] == "PASS"
    assert v["platform_crypto_attestation"] == "NOT_PROVEN"
    assert v["hardware_tpm"] == "NOT_AVAILABLE"
    assert v["certification"] == "FAIL"
    assert v["aws_iid_rsa2048_pin"] == "NOT_PROVEN"


def test_ovh_vm_is_l2_not_tpm() -> None:
    snap = collect_platform_attestation(
        declared_node_id="ovh-node-2",
        attestation_public_key="sTLG+A4+n2iKHYMZzsPw2WxzNj5+B12c23A8ykt4BzE=",
        tpm={"present": False, "quote": None},
        virt={"is_vm": True, "hostname": "n2", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": True, "uuid": "6470522e-1561-4741-9254-5f58b909eeb9"},
    )
    assert snap["trust_level"] == 2
    assert snap["overall_platform_trust"] == "CLOUD_ATTESTED"
    assert snap["hardware_tpm_attestation"] == "NOT_AVAILABLE"
    assert snap["platform_identity_attestation"] == "OVH_CLOUD_ATTESTED"
    assert snap["certified_hardware_identity"] is False
    v = snap["split_verdicts"]
    assert v["platform_level_observed"] == "PASS"
    assert v["platform_crypto_attestation"] == "NOT_PROVEN"
    assert v["hardware_tpm"] == "NOT_AVAILABLE"
    assert v["certification"] == "FAIL"
    assert v["aws_iid_rsa2048_pin"] == "NOT_APPLICABLE"


def test_vtpm_without_quote_stays_below_l3() -> None:
    snap = collect_platform_attestation(
        declared_node_id="aws-node-3",
        attestation_public_key="k",
        tpm={"present": True, "quote": None},
        virt={"is_vm": True, "hostname": "v", "machine_id": "m", "dmi_uuid": "d"},
        aws=_cloud_aws(),
        ovh={"document_ok": False},
    )
    assert snap["platform_class"] == "vtpm"
    assert snap["vtpm_attestation"] == "VTPM_PRESENT_QUOTE_MISSING"
    assert snap["trust_level"] == 2  # cloud document is the completed proof
    assert snap["overall_platform_trust"] == "CLOUD_ATTESTED"
    assert snap["certified_hardware_identity"] is False


def test_bare_metal_tpm_quote_is_l4() -> None:
    snap = collect_platform_attestation(
        declared_node_id="ovh-baremetal-1",
        attestation_public_key="ak",
        tpm={"present": True, "quote": {"verified": True, "ak": "real"}},
        virt={"is_vm": False, "hostname": "dell", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert snap["platform_class"] == "tpm_hardware"
    assert snap["trust_level"] == 4
    assert snap["overall_platform_trust"] == "TPM_ATTESTED"
    assert snap["hardware_tpm_attestation"] == "TPM_HARDWARE_ATTESTED"
    assert snap["certified_hardware_identity"] is True
    v = snap["split_verdicts"]
    assert v["platform_level_observed"] == "PASS"
    assert v["platform_crypto_attestation"] == "PASS"
    assert v["hardware_tpm"] == "TPM_HARDWARE_ATTESTED"
    assert v["certification"] == "FAIL"


def test_generic_vm_is_l1() -> None:
    snap = collect_platform_attestation(
        declared_node_id="lab-vm",
        attestation_public_key="",
        tpm={"present": False, "quote": None},
        virt={"is_vm": True, "hostname": "lab", "machine_id": "m", "dmi_uuid": "d"},
        aws={"document_ok": False},
        ovh={"document_ok": False},
    )
    assert snap["platform_class"] == "vm_unattested"
    assert snap["trust_level"] == 1
    assert snap["overall_platform_trust"] == "VM_UNATTESTED"
    assert snap["certified_hardware_identity"] is False


def test_env_cannot_usurp_platform_instance() -> None:
    rows = {
        "ovh-node-2": {
            "provider": "ovh",
            "provider_instance_id": "6470522e-1561-4741-9254-5f58b909eeb9",
            "ed25519_b64": "sTLG+A4+n2iKHYMZzsPw2WxzNj5+B12c23A8ykt4BzE=",
        },
        "ovh-node-4": {
            "provider": "ovh",
            "provider_instance_id": "22dc6a47-5b79-4084-82d7-eabb4f5b2680",
            "ed25519_b64": "fiXJqTRUFuDYPQkh8q8UuzilVyK8sshJANQkDmfjNBs=",
        },
    }
    with override_platform_binding(rows):
        bind = evaluate_node_platform_binding(
            declared_node_id="ovh-node-4",
            observed_instance_id="6470522e-1561-4741-9254-5f58b909eeb9",
            observed_provider="ovh",
            attestation_public_key="sTLG+A4+n2iKHYMZzsPw2WxzNj5+B12c23A8ykt4BzE=",
        )
    assert bind["identity_mismatch"] is True
    assert bind["platform_bound_node_id"] == "ovh-node-2"
    assert bind["binding_verified"] is False


def test_matching_instance_binds() -> None:
    bind = evaluate_node_platform_binding(
        declared_node_id="aws-node-3",
        observed_instance_id="i-085b74abd1aaf04ee",
        observed_provider="aws",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
    )
    assert bind["identity_mismatch"] is False
    assert bind["binding_verified"] is True
    assert bind["platform_bound_node_id"] == "aws-node-3"
    expected = node_binding_digest(
        network_id="artcb-official",
        node_id="aws-node-3",
        provider="aws",
        provider_instance_id="i-085b74abd1aaf04ee",
        attestation_public_key="eJsXlnBP1o1/Oq1v9zQ0z8n1Al3jBtJ4M/KLSESb34Q=",
    )
    assert bind["node_binding"] == expected


def test_block_size_bytes_equals_utf8_line() -> None:
    block = ChainBlock(
        index=1,
        timestamp="2026-09-09T00:00:00+00:00",
        prev_hash="0" * 64,
        graph_root="1" * 64,
        merkle_root="1" * 64,
        pol_score=0.1,
        hash="2" * 64,
        signature="sig",
        graph_id="g",
        visibility="public",
        block_reward=50,
        contributors=[{"address": "artcb1x", "pol_score": 0.1}],
        hash_version=1,
    )
    line = block.to_json_line()
    payload = json.loads(line)
    assert payload["block_size_bytes"] == len(line.encode("utf-8"))
    sizes = measure_jsonl_sizes(line + "\n")
    assert sizes["claimed_matches_line"] == 1
    assert sizes["file_bytes"] == sizes["line_bytes"] + 1
    assert sizes["payload_bytes"] < sizes["line_bytes"]


def test_import_line_includes_pbft_cert_in_size() -> None:
    """Sidecar cert is ~39 KiB; size must be measured after it is attached."""
    payload = {
        "index": 9,
        "timestamp": "2026-09-09T00:00:00+00:00",
        "prev_hash": "0" * 64,
        "graph_root": "g",
        "merkle_root": "m",
        "pol_score": 0.1,
        "hash": "h" * 64,
        "signature": "s",
        "pbft_cert": {"commits": ["x" * 8000], "seq": 9, "digest": "h" * 64},
    }
    line = encode_jsonl_with_converged_size(dict(payload))
    obj = json.loads(line)
    assert obj["block_size_bytes"] == len(line.encode("utf-8"))
    assert obj["block_size_bytes"] > 8000


def test_block_size_converges_across_digit_widths() -> None:
    payload = {"index": 0, "blob": "x" * 990}
    line = encode_jsonl_with_converged_size(payload)
    measured = len(line.encode("utf-8"))
    assert json.loads(line)["block_size_bytes"] == measured
    # crossing 1000 / 10000 must still converge
    payload2 = {"index": 1, "blob": "y" * 9990}
    line2 = encode_jsonl_with_converged_size(payload2)
    assert json.loads(line2)["block_size_bytes"] == len(line2.encode("utf-8"))


def test_aws_iid_pin_fails_closed_on_junk() -> None:
    from src.artcb.consensus.platform_attest import verify_aws_iid_rsa2048_pin

    got = verify_aws_iid_rsa2048_pin(
        document='{"instanceId":"i-085b74abd1aaf04ee","region":"eu-west-3"}',
        rsa2048_body="not-a-pkcs7",
        region="eu-west-3",
    )
    assert got["verified"] is False
    assert got["reason"] != "ok"


def test_split_verdicts_never_certify_from_cloud_observe() -> None:
    from src.artcb.consensus.platform_attest import split_platform_verdicts

    v = split_platform_verdicts(
        overall="CLOUD_ATTESTED",
        hardware_tpm="NOT_AVAILABLE",
        attestation_crypto_verified=False,
        certified_hardware_identity=False,
        iid_pin={"verified": True, "reason": "ok"},
        recast_cloud_as_tpm=False,
    )
    assert v["platform_level_observed"] == "PASS"
    assert v["aws_iid_rsa2048_pin"] == "PASS"
    assert v["platform_crypto_attestation"] == "NOT_PROVEN"
    assert v["certification"] == "FAIL"
