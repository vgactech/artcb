"""R347 — identity layer invariants (cartography, not uniqueness cert)."""

from src.artcb.identity.layers import (
    INVARIANTS,
    LAYER_STATUS,
    assert_invariants_documented,
    identity_map_snapshot,
)


def test_invariants_present() -> None:
    assert_invariants_documented()
    for key in (
        "I1_NODE_NEQ_USER",
        "I2_DEVICE_HOST_NEQ_USER",
        "I5_NO_USER_PRIVKEY_UPLOAD",
        "I6_WEBAUTHN_NEQ_UNIQUE_HUMAN",
        "I7_R345_SCOPE",
        "I8_KEEP_ANTI_FRAUD",
    ):
        assert key in INVARIANTS


def test_human_not_wired_to_wallet_create() -> None:
    assert LAYER_STATUS["USER_HUMAN"]["wired_to_wallet_create"] is False
    assert LAYER_STATUS["AUTHENTICATOR"]["proves_unique_human"] is False


def test_snapshot_honest_flags() -> None:
    s = identity_map_snapshot()
    assert s["certified_100"] is False
    assert s["unique_human"] is False
    assert s["r345_label"] == "CLIENT_DEVICE_BINDING_PASS"
    assert any(r["from"] == "USER_HUMAN" and "MISSING" in r["cardinality"] for r in s["relations_today"])
