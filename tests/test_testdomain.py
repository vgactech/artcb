"""Tests TEST DOMAIN — rapport 357.

Couvre :
  1. Domain separation cryptographique (adresses MAINNET ≠ TEST pour la même clé)
  2. Machine à états WalletState (transitions valides, transitions invalides)
  3. TestAttestationProvider (émission, vérification, expiry, révocation)
  4. TestWalletFactory (profils A..J, wallets adversariaux, matrice de validation)
  5. wallet_device_binding — namespace TEST (registre séparé, moteur intact)
  6. Invariants cross-domain (TEST→MAINNET rejeté)
  7. Signatures domain-séparées (TEST signature ≠ MAINNET)
"""

from __future__ import annotations

import hashlib
import pytest

from nacl import signing as nacl_signing

# ──────────────────────────────────────────────────────────────────────────────
# 1. Domain separation — address.py
# ──────────────────────────────────────────────────────────────────────────────

from src.artcb.wallet.address import (
    DOMAIN_TAG_MAINNET,
    DOMAIN_TAG_TEST,
    generate_address,
    generate_address_with_domain_tag,
    generate_test_address,
    generate_mainnet_address_domain_separated,
    verify_address,
)


class TestDomainSeparationAddress:
    """Cryptographic domain separation: same key → different address on MAINNET vs TEST."""

    def setup_method(self):
        self.sk = nacl_signing.SigningKey.generate()
        self.pk_bytes = self.sk.verify_key.encode()

    def test_test_address_starts_with_artcbdev(self):
        addr = generate_test_address(self.pk_bytes)
        assert addr.startswith("artcbdev1"), f"Expected artcbdev1…, got {addr}"

    def test_mainnet_domain_separated_starts_with_artcb1(self):
        addr = generate_mainnet_address_domain_separated(self.pk_bytes)
        assert addr.startswith("artcb1"), f"Expected artcb1…, got {addr}"

    def test_same_key_different_domain_yields_different_address(self):
        """Core invariant: H(TEST || pk) ≠ H(MAINNET || pk)."""
        test_addr = generate_test_address(self.pk_bytes)
        main_addr = generate_mainnet_address_domain_separated(self.pk_bytes)
        assert test_addr != main_addr, "Domain separation FAILED: same address for TEST and MAINNET"

    def test_legacy_mainnet_differs_from_domain_separated_mainnet(self):
        """Legacy generate_address (no tag) ≠ domain-separated (with tag)."""
        legacy = generate_address(self.pk_bytes)
        domain_sep = generate_mainnet_address_domain_separated(self.pk_bytes)
        assert legacy != domain_sep, "Legacy and domain-separated mainnet addresses must differ"

    def test_test_address_is_valid_bech32(self):
        addr = generate_test_address(self.pk_bytes)
        assert verify_address(addr, prefix="artcbdev"), f"Invalid Bech32: {addr}"

    def test_domain_tag_changes_hash(self):
        tag_a = "ARTCB/WALLET/MAINNET/V1"
        tag_b = "ARTCB/WALLET/TEST/V1"
        addr_a = generate_address_with_domain_tag(self.pk_bytes, domain_tag=tag_a, prefix="artcb")
        addr_b = generate_address_with_domain_tag(self.pk_bytes, domain_tag=tag_b, prefix="artcbdev")
        assert addr_a != addr_b

    def test_empty_domain_tag_raises(self):
        with pytest.raises(ValueError, match="domain_tag must not be empty"):
            generate_address_with_domain_tag(self.pk_bytes, domain_tag="", prefix="artcb")

    def test_wrong_pubkey_size_raises(self):
        with pytest.raises(ValueError, match="32 bytes"):
            generate_address_with_domain_tag(b"short", domain_tag=DOMAIN_TAG_TEST, prefix="artcbdev")

    def test_deterministic_for_same_key(self):
        addr1 = generate_test_address(self.pk_bytes)
        addr2 = generate_test_address(self.pk_bytes)
        assert addr1 == addr2, "Address must be deterministic for the same key"


# ──────────────────────────────────────────────────────────────────────────────
# 2. WalletState machine
# ──────────────────────────────────────────────────────────────────────────────

from src.artcb.testdomain.wallet_states import (
    ADVERSARIAL_STATES,
    CERT_THRESHOLDS,
    HAPPY_PATH_SEQUENCE,
    WalletState,
    WalletStateError,
    certification_percent_to_state,
    compute_certification_percent,
    validate_transition,
)


class TestWalletStateMachine:

    def test_happy_path_all_transitions_valid(self):
        """All consecutive transitions in the happy path must succeed."""
        for i in range(len(HAPPY_PATH_SEQUENCE) - 1):
            src = HAPPY_PATH_SEQUENCE[i]
            dst = HAPPY_PATH_SEQUENCE[i + 1]
            validate_transition(src, dst)  # must not raise

    def test_skip_to_cert100_from_key_only_is_rejected(self):
        """KEY_ONLY → CERT_100 must be rejected (skips intermediate steps)."""
        with pytest.raises(WalletStateError):
            validate_transition(WalletState.KEY_ONLY, WalletState.CERT_100)

    def test_cert50_to_active_is_rejected(self):
        """CERT_50 → ACTIVE is forbidden (below 100 % quorum)."""
        with pytest.raises(WalletStateError):
            validate_transition(WalletState.CERT_50, WalletState.ACTIVE)

    def test_revoked_to_active_is_rejected(self):
        """REVOKED → ACTIVE is forbidden without RECOVERY."""
        with pytest.raises(WalletStateError):
            validate_transition(WalletState.REVOKED, WalletState.ACTIVE)

    def test_adversarial_states_have_no_valid_transition(self):
        """Any adversarial state → anything must raise WalletStateError."""
        for adv_state in ADVERSARIAL_STATES:
            with pytest.raises(WalletStateError, match="terminal"):
                validate_transition(adv_state, WalletState.KEY_ONLY)

    def test_active_to_suspended_then_back(self):
        validate_transition(WalletState.ACTIVE, WalletState.SUSPENDED)
        validate_transition(WalletState.SUSPENDED, WalletState.ACTIVE)

    def test_revoked_recovery_restart(self):
        validate_transition(WalletState.REVOKED, WalletState.RECOVERY)
        validate_transition(WalletState.RECOVERY, WalletState.KEY_ONLY)

    def test_rotation_cycle(self):
        validate_transition(WalletState.ACTIVE, WalletState.ROTATION_PENDING)
        validate_transition(WalletState.ROTATION_PENDING, WalletState.ROTATED)
        validate_transition(WalletState.ROTATED, WalletState.ACTIVE)

    def test_certification_percent_to_state(self):
        assert certification_percent_to_state(0) == WalletState.IDENTITY_ATTESTED
        assert certification_percent_to_state(9) == WalletState.IDENTITY_ATTESTED
        assert certification_percent_to_state(10) == WalletState.CERT_10
        assert certification_percent_to_state(25) == WalletState.CERT_25
        assert certification_percent_to_state(50) == WalletState.CERT_50
        assert certification_percent_to_state(75) == WalletState.CERT_75
        assert certification_percent_to_state(100) == WalletState.CERT_100
        assert certification_percent_to_state(200) == WalletState.CERT_100

    def test_compute_certification_percent_deduplicates(self):
        certifiers = ["v1", "v2", "v2", "v3"]  # v2 duplicated
        pct = compute_certification_percent(certifiers, required=10)
        assert pct == 30  # 3 unique / 10 * 100

    def test_compute_certification_percent_zero_required(self):
        assert compute_certification_percent(["v1"], required=0) == 0

    def test_cert_thresholds_complete(self):
        for state in (
            WalletState.CERT_10, WalletState.CERT_25, WalletState.CERT_50,
            WalletState.CERT_75, WalletState.CERT_100,
        ):
            assert state in CERT_THRESHOLDS


# ──────────────────────────────────────────────────────────────────────────────
# 3. TestAttestationProvider
# ──────────────────────────────────────────────────────────────────────────────

from src.artcb.testdomain.attestation import TestAttestation, TestAttestationProvider


class TestAttestationProviderTests:

    def setup_method(self):
        self.provider = TestAttestationProvider()
        self.test_addr = "artcbdev1qtest000"

    def test_issue_returns_attestation(self):
        att = self.provider.issue(self.test_addr)
        assert att.attestation_type == "TEST"
        assert att.subject_id.startswith("TEST-HUMAN-")
        assert att.device_id.startswith("TEST-DEVICE-")
        assert att.wallet_address == self.test_addr
        assert att.signature != ""

    def test_issued_attestation_is_valid(self):
        att = self.provider.issue(self.test_addr)
        ok, reason = att.is_valid_for_test()
        assert ok, f"Expected valid, got: {reason}"

    def test_signature_verifies(self):
        att = self.provider.issue(self.test_addr)
        ok, reason = self.provider.verify(att)
        assert ok, f"Signature should be valid: {reason}"

    def test_corrupted_signature_rejected(self):
        att = self.provider.issue(self.test_addr)
        att.signature = "deadbeef" * 8
        ok, reason = self.provider.verify(att)
        assert not ok

    def test_expired_attestation_is_invalid(self):
        att = self.provider.issue(self.test_addr, expired=True)
        assert att.is_expired()
        ok, reason = att.is_valid_for_test()
        assert not ok
        assert "expired" in reason

    def test_revoked_attestation_is_invalid(self):
        att = self.provider.issue(self.test_addr, revoked=True)
        ok, reason = att.is_valid_for_test()
        assert not ok
        assert "revoked" in reason

    def test_sequential_subject_ids_are_unique(self):
        att1 = self.provider.issue(self.test_addr)
        att2 = self.provider.issue(self.test_addr)
        assert att1.subject_id != att2.subject_id

    def test_issue_batch(self):
        addrs = [f"artcbdev1qaddr{i:04d}" for i in range(5)]
        batch = self.provider.issue_batch(addrs)
        assert len(batch) == 5
        subject_ids = [a.subject_id for a in batch]
        assert len(set(subject_ids)) == 5, "Subject IDs must be unique"

    def test_canonical_payload_is_deterministic(self):
        att = self.provider.issue(self.test_addr)
        p1 = att.canonical_payload()
        p2 = att.canonical_payload()
        assert p1 == p2

    def test_fingerprint_changes_on_revoked(self):
        att = self.provider.issue(self.test_addr)
        fp1 = att.fingerprint()
        att.revoked = True
        fp2 = att.fingerprint()
        assert fp1 != fp2

    def test_wrong_address_prefix_rejected(self):
        att = self.provider.issue(self.test_addr)
        att.wallet_address = "artcb1qmainnet"  # wrong domain prefix
        ok, reason = att.is_valid_for_test()
        assert not ok
        assert "wrong_domain_prefix" in reason


# ──────────────────────────────────────────────────────────────────────────────
# 4. TestWalletFactory — profils A..J + adversariaux
# ──────────────────────────────────────────────────────────────────────────────

from src.artcb.testdomain.factory import TestWallet, TestWalletFactory
from src.artcb.testdomain.policy import TEST_DOMAIN_TAG, TEST_NETWORK_ID, TEST_GENESIS_HASH


class TestWalletFactoryProfiles:

    def setup_method(self):
        self.factory = TestWalletFactory()

    def test_profile_a_key_only(self):
        w = self.factory.create("A")
        assert w.state == WalletState.KEY_ONLY
        assert w.wallet_id.startswith("artcbdev1")
        assert not w.adversarial

    def test_profile_b_device_bound(self):
        w = self.factory.create("B")
        assert w.state == WalletState.DEVICE_BOUND
        assert w.attestation is not None

    def test_profile_c_identity_bound(self):
        w = self.factory.create("C")
        assert w.state == WalletState.IDENTITY_BOUND

    def test_profile_d_cert10(self):
        w = self.factory.create("D")
        assert w.state == WalletState.CERT_10
        assert w.certification_percent() == 10

    def test_profile_e_cert50(self):
        w = self.factory.create("E")
        assert w.state == WalletState.CERT_50
        assert w.certification_percent() == 50

    def test_profile_f_active(self):
        w = self.factory.create("F")
        assert w.state == WalletState.ACTIVE
        assert w.certification_percent() == 100

    def test_profile_g_expired(self):
        w = self.factory.create("G")
        assert w.state == WalletState.EXPIRED

    def test_profile_h_revoked(self):
        w = self.factory.create("H")
        assert w.state == WalletState.REVOKED

    def test_profile_i_invalid_signature(self):
        w = self.factory.create("I")
        assert w.state == WalletState.INVALID_SIGNATURE
        assert w.adversarial

    def test_profile_j_replay(self):
        w = self.factory.create("J")
        assert w.state == WalletState.REPLAY
        assert w.adversarial

    def test_all_profiles_have_artcbdev_address(self):
        for profile in ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"):
            w = self.factory.create(profile)
            assert w.wallet_id.startswith("artcbdev1"), \
                f"Profile {profile}: expected artcbdev1 prefix, got {w.wallet_id}"

    def test_unique_addresses_across_profiles(self):
        wallets = [self.factory.create(p) for p in ("A", "B", "C", "F")]
        addresses = [w.wallet_id for w in wallets]
        assert len(set(addresses)) == len(addresses), "Wallet addresses must be unique"

    def test_history_is_populated_for_active_wallet(self):
        w = self.factory.create("F")
        assert len(w.history) > 0
        states_in_history = [h["to"] for h in w.history]
        assert WalletState.ACTIVE.value in states_in_history

    def test_sign_payload_includes_domain(self):
        w = self.factory.create("F")
        sig = w.sign_payload({"action": "transfer", "amount": 1})
        assert isinstance(sig, str)
        assert len(sig) == 128  # Ed25519 sig = 64 bytes → 128 hex chars

    def test_nonce_increments_on_sign(self):
        w = self.factory.create("F")
        assert w.nonce == 0
        w.sign_payload({"x": 1})
        assert w.nonce == 1
        w.sign_payload({"x": 2})
        assert w.nonce == 2

    def test_create_batch_returns_correct_count(self):
        batch = self.factory.create_batch(7, "B")
        assert len(batch) == 7
        assert all(w.state == WalletState.DEVICE_BOUND for w in batch)

    def test_to_dict_contains_required_fields(self):
        w = self.factory.create("F")
        d = w.to_dict()
        for key in ("wallet_id", "state", "profile", "domain", "network_id", "genesis_hash",
                    "certification_percent", "certifiers_count", "history"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_domain_is_test(self):
        w = self.factory.create("F")
        assert w.to_dict()["domain"] == "TEST"
        assert w.to_dict()["network_id"] == TEST_NETWORK_ID
        assert w.to_dict()["genesis_hash"] == TEST_GENESIS_HASH

    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            self.factory.create("Z")  # type: ignore


class TestWalletFactoryAdversarial:

    def setup_method(self):
        self.factory = TestWalletFactory()

    @pytest.mark.parametrize("fault", [
        "BAD_SIGNATURE", "WRONG_DEVICE", "EXPIRED", "REVOKED",
        "REPLAY", "WRONG_NONCE", "DUPLICATE_VALIDATOR",
        "INSUFFICIENT_QUORUM", "WRONG_NETWORK", "WRONG_GENESIS",
        "WRONG_DOMAIN", "UNAUTHORIZED_AGENT",
    ])
    def test_adversarial_wallet_is_marked(self, fault):
        w = self.factory.create_adversarial(fault)
        assert w.adversarial, f"Fault {fault}: wallet should be adversarial"
        assert w.adversarial_reason != ""
        assert w.state in ADVERSARIAL_STATES or w.state in (
            WalletState.EXPIRED, WalletState.REVOKED
        ), f"Fault {fault}: unexpected state {w.state}"

    def test_adversarial_wallet_has_artcbdev_address(self):
        w = self.factory.create_adversarial("WRONG_DOMAIN")
        assert w.wallet_id.startswith("artcbdev1")

    def test_unknown_fault_raises(self):
        with pytest.raises(ValueError, match="Unknown fault"):
            self.factory.create_adversarial("DOES_NOT_EXIST")

    def test_validation_matrix_has_all_cases(self):
        matrix = self.factory.create_validation_matrix()
        assert "PROFILE_A" in matrix
        assert "PROFILE_F" in matrix
        assert "ADVERSARIAL_WRONG_DOMAIN" in matrix
        assert "ADVERSARIAL_REPLAY" in matrix
        # Matrix must have both PASS and REJECT cases
        pass_cases = [k for k in matrix if k.startswith("PROFILE_") and "ADVERSARIAL" not in k]
        reject_cases = [k for k in matrix if "ADVERSARIAL" in k]
        assert len(pass_cases) >= 6
        assert len(reject_cases) >= 10


# ──────────────────────────────────────────────────────────────────────────────
# 5. wallet_device_binding — namespace TEST
# ──────────────────────────────────────────────────────────────────────────────

import tempfile
from pathlib import Path

from src.artcb.security.wallet_device_binding import (
    WalletDeviceBindingError,
    WalletDeviceBindingStore,
    is_test_wallet_name,
)


class TestWalletDeviceBindingTestNamespace:

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self.store = WalletDeviceBindingStore(Path(self._tmpdir))

    def test_is_test_wallet_name_artcbdev(self):
        assert is_test_wallet_name("artcbdev1qtest")
        assert is_test_wallet_name("test_my_wallet")
        assert is_test_wallet_name("TEST-WALLET-001")

    def test_is_test_wallet_name_production_false(self):
        assert not is_test_wallet_name("default")
        assert not is_test_wallet_name("vgactech")
        assert not is_test_wallet_name("cursor-cloud-agent")

    def test_test_namespace_allows_multiple_wallets_same_device(self):
        fp = "abcd1234" * 4
        self.store.check_and_bind(wallet_name="test_wallet_001", device_fingerprint=fp, wallet_namespace="TEST")
        self.store.check_and_bind(wallet_name="test_wallet_002", device_fingerprint=fp, wallet_namespace="TEST")
        self.store.check_and_bind(wallet_name="test_wallet_003", device_fingerprint=fp, wallet_namespace="TEST")
        # No exception raised — TEST allows multiple wallets per device

    def test_test_namespace_stored_in_separate_file(self):
        fp = "fp_test_001" * 3
        self.store.check_and_bind(wallet_name="test_abc", device_fingerprint=fp, wallet_namespace="TEST")
        test_bindings = self.store.list_test_bindings()
        prod_bindings = self.store.list_bindings()
        assert len(test_bindings) == 1
        assert len(prod_bindings) == 0, "TEST wallet must NOT appear in PRODUCTION registry"

    def test_production_namespace_still_enforces_single_wallet(self):
        fp = "fp_prod_001" * 3
        self.store.check_and_bind(wallet_name="my_prod_wallet", device_fingerprint=fp)
        with pytest.raises(WalletDeviceBindingError):
            self.store.check_and_bind(wallet_name="second_prod_wallet", device_fingerprint=fp)

    def test_namespace_by_explicit_parameter_not_by_name(self):
        """R358 §5: namespace is determined ONLY by wallet_namespace param, not wallet_name.

        wallet_name="artcbdev1qfoo" WITHOUT wallet_namespace="TEST"
        → goes to PRODUCTION registry (1 per device enforced).
        """
        fp = "fp_auto_001" * 3
        # No wallet_namespace="TEST" → PRODUCTION path regardless of name prefix
        self.store.check_and_bind(wallet_name="artcbdev1qfoo", device_fingerprint=fp)
        # Second artcbdev name on same device → must raise (PRODUCTION 1-per-device rule)
        with pytest.raises(WalletDeviceBindingError):
            self.store.check_and_bind(wallet_name="artcbdev1qbar", device_fingerprint=fp)
        # Only the PRODUCTION registry was touched
        assert len(self.store.list_bindings()) == 1
        assert len(self.store.list_test_bindings()) == 0

    def test_production_bind_is_idempotent(self):
        """R358 §6: same wallet+device bound twice → no duplicate in PRODUCTION registry."""
        fp = "fp_idem_prod" * 3
        self.store.check_and_bind(wallet_name="my_wallet", device_fingerprint=fp)
        self.store.check_and_bind(wallet_name="my_wallet", device_fingerprint=fp)  # idempotent
        assert len(self.store.list_bindings()) == 1

    def test_test_bind_is_idempotent(self):
        """R358 §6: same wallet+device bound twice in TEST → no duplicate."""
        fp = "fp_idem_test" * 3
        self.store.check_and_bind(wallet_name="test_w", device_fingerprint=fp, wallet_namespace="TEST")
        self.store.check_and_bind(wallet_name="test_w", device_fingerprint=fp, wallet_namespace="TEST")
        self.store.check_and_bind(wallet_name="test_w", device_fingerprint=fp, wallet_namespace="TEST")
        assert len(self.store.list_test_bindings()) == 1  # exactly one record, no duplicates

    def test_same_test_wallet_name_different_device_rejected(self):
        fp1 = "device_fp_aaa" * 3
        fp2 = "device_fp_bbb" * 3
        self.store.check_and_bind(wallet_name="test_unique_name", device_fingerprint=fp1, wallet_namespace="TEST")
        with pytest.raises(WalletDeviceBindingError, match="déjà lié"):
            self.store.check_and_bind(wallet_name="test_unique_name", device_fingerprint=fp2, wallet_namespace="TEST")

    def test_get_test_binding_returns_record(self):
        fp = "fp_get_001" * 3
        self.store.check_and_bind(wallet_name="test_get_me", device_fingerprint=fp, wallet_namespace="TEST")
        rec = self.store.get_test_binding("test_get_me")
        assert rec is not None
        assert rec["wallet_name"] == "test_get_me"
        assert rec["namespace"] == "TEST"


# ──────────────────────────────────────────────────────────────────────────────
# 6. Cross-domain invariants (policy.py)
# ──────────────────────────────────────────────────────────────────────────────

from src.artcb.testdomain.policy import (
    TEST_NETWORK_ID,
    TEST_GENESIS_HASH,
    TEST_PROTOCOL_VERSION,
    accept_test_peer_protocol,
    domain_of_address,
    is_test_address,
    is_mainnet_address,
    reject_cross_domain_transfer,
    test_capabilities,
)
from src.artcb.crypto_policy import NETWORK_ID, GENESIS_HASH, PROTOCOL_VERSION


class TestCrossDomainPolicy:

    def test_network_ids_are_different(self):
        assert TEST_NETWORK_ID != NETWORK_ID

    def test_genesis_hashes_are_different(self):
        assert TEST_GENESIS_HASH != GENESIS_HASH

    def test_protocol_versions_are_different(self):
        assert TEST_PROTOCOL_VERSION != PROTOCOL_VERSION

    def test_is_test_address(self):
        assert is_test_address("artcbdev1qfoo")
        assert not is_test_address("artcb1qfoo")

    def test_is_mainnet_address(self):
        assert is_mainnet_address("artcb1qfoo")
        assert is_mainnet_address("artcb2foo")
        assert not is_mainnet_address("artcbdev1qfoo")

    def test_domain_of_address(self):
        assert domain_of_address("artcbdev1qfoo") == "TEST"
        assert domain_of_address("artcb1qfoo") == "MAINNET"
        assert domain_of_address("unknown_prefix") == "UNKNOWN"

    def test_test_to_mainnet_transfer_rejected(self):
        rejected, reason = reject_cross_domain_transfer("artcbdev1qsender", "artcb1qrecipient")
        assert rejected
        assert "TEST→MAINNET" in reason

    def test_mainnet_to_test_transfer_rejected(self):
        rejected, reason = reject_cross_domain_transfer("artcb1qsender", "artcbdev1qrecipient")
        assert rejected
        assert "MAINNET→TEST" in reason

    def test_same_domain_transfer_allowed(self):
        rejected, reason = reject_cross_domain_transfer("artcbdev1qsender", "artcbdev1qrecipient")
        assert not rejected

    def test_test_peer_protocol_accepts_correct_ids(self):
        ok, reason = accept_test_peer_protocol(
            advertised_network_id=TEST_NETWORK_ID,
            advertised_protocol_version=TEST_PROTOCOL_VERSION,
            advertised_genesis_hash=TEST_GENESIS_HASH,
        )
        assert ok, reason

    def test_test_peer_rejects_mainnet_ids(self):
        ok, reason = accept_test_peer_protocol(
            advertised_network_id=NETWORK_ID,
            advertised_protocol_version=PROTOCOL_VERSION,
            advertised_genesis_hash=GENESIS_HASH,
        )
        assert not ok
        assert "network_id_mismatch" in reason

    def test_test_peer_rejects_missing_fields(self):
        ok, reason = accept_test_peer_protocol(
            advertised_network_id=None,
            advertised_protocol_version=None,
            advertised_genesis_hash=None,
        )
        assert not ok
        assert "legacy_missing" in reason

    def test_capabilities_dict_has_correct_domain(self):
        caps = test_capabilities()
        assert caps["domain"] == "TEST"
        assert caps["network_id"] == TEST_NETWORK_ID
        assert caps["validation_engine"] == "SAME_AS_MAINNET"
        assert caps["test_to_mainnet_allowed"] is False


# ──────────────────────────────────────────────────────────────────────────────
# 7. Domain-separated signatures
# ──────────────────────────────────────────────────────────────────────────────

class TestDomainSeparatedSignatures:
    """A TEST signature cannot be valid on MAINNET and vice-versa."""

    def setup_method(self):
        self.factory = TestWalletFactory()

    def test_test_wallet_sign_includes_network_id_in_payload(self):
        """The signed payload must embed TEST network identifiers."""
        import json as _json
        w = self.factory.create("F")
        # We reconstruct what sign_payload signs
        payload = {"action": "test_op", "value": 42}
        domain_envelope = {
            "domain_id": TEST_DOMAIN_TAG,
            "network_id": TEST_NETWORK_ID,
            "genesis_hash": TEST_GENESIS_HASH,
            "protocol_version": TEST_PROTOCOL_VERSION,
            "wallet_id": w.wallet_id,
            "nonce": 0,
            "payload": payload,
        }
        msg = _json.dumps(domain_envelope, sort_keys=True, ensure_ascii=False).encode("utf-8")
        sig_hex = w.sign_payload(payload)
        sig_bytes = bytes.fromhex(sig_hex)
        # Verify with the actual signing key
        w.signing_key.verify_key.verify(msg, sig_bytes)  # must not raise

    def test_different_wallet_cannot_verify_other_wallet_sig(self):
        """Signature from wallet A is invalid under wallet B's public key."""
        from nacl.exceptions import BadSignatureError
        w_a = self.factory.create("F")
        w_b = self.factory.create("F")
        sig_hex = w_a.sign_payload({"x": 1})
        sig_bytes = bytes.fromhex(sig_hex)
        import json as _json
        payload_dict = {
            "domain_id": TEST_DOMAIN_TAG,
            "network_id": TEST_NETWORK_ID,
            "genesis_hash": TEST_GENESIS_HASH,
            "protocol_version": TEST_PROTOCOL_VERSION,
            "wallet_id": w_a.wallet_id,
            "nonce": 0,
            "payload": {"x": 1},
        }
        msg = _json.dumps(payload_dict, sort_keys=True, ensure_ascii=False).encode("utf-8")
        with pytest.raises(BadSignatureError):
            w_b.signing_key.verify_key.verify(msg, sig_bytes)

# ──────────────────────────────────────────────────────────────────────────────
# 8. P0-B Audit: TEST signature rejetée par le vérificateur MAINNET
# ──────────────────────────────────────────────────────────────────────────────

class TestMainnetVerifierRejectsTestSignature:
    """Prouver que chain/manager.verify_block_signature() rejette une signature TEST.

    Le vérificateur MAINNET signe/vérifie block_hash.encode("utf-8").
    TestWallet.sign_payload() signe un JSON {"domain_id": "ARTCB/WALLET/TEST/V1", ...}.
    Ces deux messages sont structurellement incompatibles → BadSignatureError.

    R358 audit §4: la séparation n'est pas seulement visuelle (préfixe artcbdev),
    elle est cryptographique via des messages différents.
    """

    def setup_method(self):
        self.factory = TestWalletFactory()

    def test_test_signature_cannot_verify_as_mainnet_block_hash(self):
        """Signature produite par sign_payload(TEST) est invalide sur block_hash MAINNET."""
        from nacl.exceptions import BadSignatureError
        w = self.factory.create("F")
        # Simulate a MAINNET block hash (hex string, 64 chars)
        fake_block_hash = "a" * 64
        mainnet_message = fake_block_hash.encode("utf-8")

        # Produce a TEST signature (envelope contains domain_id, network_id, etc.)
        test_sig_hex = w.sign_payload({"action": "op", "amount": 100})
        test_sig_bytes = bytes.fromhex(test_sig_hex)

        # MAINNET verifier reconstructs block_hash.encode() and verifies
        # → message mismatch → BadSignatureError
        with pytest.raises(BadSignatureError):
            w.signing_key.verify_key.verify(mainnet_message, test_sig_bytes)

    def test_mainnet_block_signature_cannot_verify_as_test_payload(self):
        """Signature produite sur block_hash MAINNET est invalide sur envelope TEST."""
        from nacl.exceptions import BadSignatureError
        import json as _json
        sk = nacl_signing.SigningKey.generate()
        pk_bytes = sk.verify_key.encode()

        # Simulate MAINNET: sign block_hash directly (no domain envelope)
        fake_block_hash = "b" * 64
        mainnet_signed = sk.sign(fake_block_hash.encode("utf-8"))
        mainnet_sig_bytes = mainnet_signed.signature

        # TEST verifier reconstructs full envelope including domain_id
        test_addr = generate_test_address(pk_bytes)
        test_envelope = {
            "domain_id": TEST_DOMAIN_TAG,
            "network_id": TEST_NETWORK_ID,
            "genesis_hash": TEST_GENESIS_HASH,
            "protocol_version": TEST_PROTOCOL_VERSION,
            "wallet_id": test_addr,
            "nonce": 0,
            "payload": {"action": "op"},
        }
        test_message = _json.dumps(test_envelope, sort_keys=True, ensure_ascii=False).encode("utf-8")

        with pytest.raises(BadSignatureError):
            sk.verify_key.verify(test_message, mainnet_sig_bytes)

    def test_verify_block_signature_rejects_test_sig(self):
        """chain.manager.verify_block_signature() rejette une signature TEST.

        Appel direct de verify_hybrid_and_or_window avec le message MAINNET
        (block_hash.encode()) et une signature TEST → False.
        """
        from src.artcb.crypto.hybrid import verify_hybrid_and_or_window
        w = self.factory.create("F")
        # Test wallet produces an Ed25519 signature over the TEST envelope
        test_sig_hex = w.sign_payload({"x": 1})

        # MAINNET verifier uses block_hash as message
        mainnet_message = ("c" * 64).encode("utf-8")

        ok = verify_hybrid_and_or_window(
            message=mainnet_message,
            signature_value=f"ed25519:{test_sig_hex}",
            ed25519_public_key=w.signing_key.verify_key.encode(),
            pqc_public_key=None,
        )
        assert not ok, "MAINNET verifier must reject a TEST signature"

class TestChainManagerVerifierRejectsTestSignature:
    """Test direct de ChainManager.verify_block_signature() — audit §5.

    Prouve que le chemin COMPLET
      TEST signature → ChainManager.verify_block_signature() → False
    est fermé, pas seulement le primitif verify_hybrid_and_or_window.
    """

    def setup_method(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.factory = TestWalletFactory()

    def test_chain_manager_rejects_test_wallet_signature(self):
        """ChainManager.verify_block_signature(block_hash, test_sig) → False."""
        from pathlib import Path
        from src.artcb.chain.manager import ChainManager

        # Instancier un ChainManager minimal (tmpdir, sans security pour éviter dépendances)
        blocks_path = Path(self._tmpdir) / "blocks.jsonl"
        key_path = Path(self._tmpdir) / "chain.key"
        cm = ChainManager(blocks_path=blocks_path, key_path=key_path, enable_security=False)

        # Wallet TEST produit une signature sur son envelope JSON
        w = self.factory.create("F")
        test_sig_hex = w.sign_payload({"action": "test_op", "val": 1})

        # MAINNET vérifie: message = block_hash.encode()
        fake_block_hash = "d" * 64
        result = cm.verify_block_signature(fake_block_hash, f"ed25519:{test_sig_hex}")
        assert result is False, (
            "ChainManager.verify_block_signature() doit rejeter une signature TEST"
        )

    def test_chain_manager_accepts_its_own_signature(self):
        """Sanity check: ChainManager vérifie sa propre signature sur son propre block_hash."""
        from pathlib import Path
        from src.artcb.chain.manager import ChainManager

        blocks_path = Path(self._tmpdir) / "blocks2.jsonl"
        key_path = Path(self._tmpdir) / "chain2.key"
        cm = ChainManager(blocks_path=blocks_path, key_path=key_path, enable_security=False)

        # Signer un hash fictif avec la clé MAINNET du ChainManager
        fake_block_hash = "e" * 64
        mainnet_sig = cm._sign_block(fake_block_hash)

        # Le même ChainManager doit accepter sa propre signature
        result = cm.verify_block_signature(fake_block_hash, mainnet_sig)
        assert result is True, "ChainManager doit accepter sa propre signature"
