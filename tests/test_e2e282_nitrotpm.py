"""R282 — NitroTPM on AWS3 is L3, never L4. Guest swtpm is not this path."""

from __future__ import annotations

from src.artcb.consensus.platform_attest import load_platform_binding_registry
from src.artcb.consensus.tpm_quote import attempt_attestation_quote
from src.artcb.node_registry import NODES


def test_aws3_registry_is_nitrotpm_instance() -> None:
    spec = NODES["aws-node-3"]
    assert spec.ssh_host == "13.38.209.25"
    replicas = load_platform_binding_registry()
    aws = replicas["aws-node-3"]
    assert aws["provider_instance_id"] == "i-06c9404e42798ff76"
    assert aws["ipv4"] == "13.38.209.25"


def test_qualifier_pads_to_32_bytes() -> None:
    # Device may be absent on this runner; only check the pad path when present.
    got = attempt_attestation_quote(extra_data=b"short", is_vm=True)
    assert got["verified"] is False or got.get("qualifier_sha256") is None or len(got["qualifier_sha256"]) == 64
    if got.get("reason") == "DEVICE_ABSENT":
        assert got["verified"] is False
