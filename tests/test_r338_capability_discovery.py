"""R338 — capability discovery tests."""

from src.artcb.platform.capability_discovery import classify_c04, discover_mac_root_of_trust


def test_discover_returns_required_fields() -> None:
    d = discover_mac_root_of_trust()
    assert d["protocol"] == "r338-capability-discovery-v1"
    assert "C04_verdict" in d
    assert d["security_equivalence_to_hardware_rot"] is False
    assert d["certified_100"] is False


def test_classify_unsupported() -> None:
    assert (
        classify_c04(capability={"C04_verdict": "UNSUPPORTED_HARDWARE"}, crypto_attested=True)
        == "UNSUPPORTED_HARDWARE"
    )


def test_classify_not_proven_without_crypto() -> None:
    assert classify_c04(capability={"C04_verdict": "NOT_PROVEN"}, crypto_attested=None) == "NOT_PROVEN"
