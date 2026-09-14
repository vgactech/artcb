"""R343 — ORG KYB + QR pairing + langage battery unit tests."""

from src.artcb.auth.qr_pairing import (
    PairingState,
    capability_matrix,
    consume_pairing,
    create_pairing_session,
    qr_payload,
)
from src.artcb.org.kyb import (
    OrgKybStatus,
    conflict_of_interest,
    creator_may_self_validate,
    public_commitment_stub,
    reward_eligible,
)
from src.artcb.reasoning.langage_battery import battery_summary


def test_org_reward_gate_and_no_self_validate() -> None:
    assert reward_eligible(OrgKybStatus.ORG_CREATED) is False
    assert reward_eligible(OrgKybStatus.ORG_ACTIVE) is True
    # R345: self-validate DENY; independent validator OK at this gate
    assert creator_may_self_validate(creator_id="A", validator_id="A") is False
    assert creator_may_self_validate(creator_id="A", validator_id="B") is True
    assert creator_may_self_validate(creator_id="", validator_id="B") is False
    assert conflict_of_interest(validator_id="U1", org_controller_ids=["U1"], ubo_ids=[]) is True
    assert conflict_of_interest(validator_id="U2", org_controller_ids=["U1"], ubo_ids=["U2"]) is True
    assert conflict_of_interest(validator_id="U3", org_controller_ids=["U1"], ubo_ids=["U2"]) is False
    c = public_commitment_stub("org1", "abc")
    assert c["includes_raw_documents"] is False


def test_creator_cannot_self_validate() -> None:
    assert creator_may_self_validate(creator_id="A", validator_id="A") is False
    assert creator_may_self_validate(creator_id="A", validator_id="B") is True


def test_qr_pairing_single_use_and_expiry() -> None:
    s = create_pairing_session(ttl_s=60)
    assert "pair/" in qr_payload(s)
    assert s.state == PairingState.UNUSED.value
    s2 = consume_pairing(s)
    assert s2.state == PairingState.USED.value
    s3 = consume_pairing(s2)
    assert s3.state == PairingState.REJECTED.value
    expired = create_pairing_session(ttl_s=1)
    expired.expires_ts_ns = expired.created_ts_ns  # force expire
    assert consume_pairing(expired).state == PairingState.EXPIRED.value


def test_capability_matrix_paths() -> None:
    assert capability_matrix(camera_available=True, authenticator_available=True)["recommended_path"] == "local_enroll"
    assert capability_matrix(camera_available=False, authenticator_available=False)["recommended_path"] == "qr_phone_required"


def test_langage_battery_not_certified() -> None:
    s = battery_summary()
    assert s["certified_100"] is False
    assert len(s["tests"]) == 12
