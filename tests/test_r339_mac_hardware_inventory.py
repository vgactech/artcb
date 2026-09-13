"""R339 — Mac inventory / H1 enrollment honesty."""

from src.artcb.platform.mac_hardware_inventory import (
    build_enrollment_bundle,
    collect_mac_hardware_inventory,
    ensure_node_keypair,
)


def test_inventory_does_not_claim_h3_without_rot() -> None:
    inv = collect_mac_hardware_inventory()
    assert inv.protocol.startswith("r339")
    # On MacBookAir7,1 class hosts: no H3 claim
    if not inv.security.get("apple_silicon") and not inv.security.get("t2") and not inv.security.get("tpm"):
        assert inv.assurance_h in {"H0", "H1"}
        assert inv.native_c04 == "UNSUPPORTED_HARDWARE"
    assert inv.fingerprint_v2 is None or len(inv.fingerprint_v2) == 64


def test_enrollment_bundle_not_c04_pass() -> None:
    b = build_enrollment_bundle()
    assert b["c04_pass"] is False
    assert b["certified_100"] is False
    assert "public_key_b64" in b["node_key"]
    assert b["hardware"]["assurance_h"] in {"H0", "H1", "H3"}  # H3 only if rot candidate


def test_node_key_idempotent(tmp_path) -> None:
    p = tmp_path / "k.key"
    a = ensure_node_keypair(p)
    b = ensure_node_keypair(p)
    assert a["public_key_b64"] == b["public_key_b64"]
    assert a["created"] is True
    assert b["created"] is False


def test_challenge_response_does_not_claim_h3(tmp_path) -> None:
    from src.artcb.platform.mac_hardware_inventory import sign_node_challenge

    p = tmp_path / "k.key"
    ensure_node_keypair(p)
    signed = sign_node_challenge(b"artcb-challenge-r339", p)
    assert signed["assurance_ceiling"] == "H1"
    assert signed["does_not_prove"] == "hardware_root_of_trust"
    assert "signature_b64" in signed
