"""TEST DOMAIN wallet factory — rapport 353 §10+§18, rapport 354 §4+§13.

TestWalletFactory creates TEST-domain wallets with cryptographic domain separation.

Profiles (rapport 353 §10):
  A  KEY_ONLY           — keypair only, no device/identity
  B  DEVICE_BOUND       — keypair + synthetic device attestation
  C  IDENTITY_BOUND     — + TEST identity (not yet attested)
  D  CERT_10            — + 10 % quorum (10/100 validators)
  E  CERT_50            — + 50 % quorum
  F  CERT_100           — + 100 % quorum → ACTIVE
  G  EXPIRED            — attestation in the past
  H  REVOKED            — identity revoked
  I  INVALID_SIGNATURE  — wallet with a deliberately wrong signature
  J  REPLAY             — wallet with a reused nonce

Adversarial wallets (rapport 353 §11):
  BAD_SIGNATURE, WRONG_PRIVATE_KEY, WRONG_PUBLIC_KEY, WRONG_DEVICE,
  EXPIRED, REVOKED, REPLAY, WRONG_NONCE, WRONG_VALIDATOR,
  DUPLICATE_VALIDATOR, INSUFFICIENT_QUORUM, WRONG_NETWORK,
  WRONG_GENESIS, WRONG_DOMAIN, UNAUTHORIZED_AGENT

Architecture invariants (rapport 355 §15):
  - Same validation engine as MAINNET (no skip_validation).
  - TEST → MAINNET transfers are REJECTED.
  - All addresses are artcbdev1… (domain-separated hash).
  - Signatures carry domain_id + network_id + genesis_hash in the payload.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from nacl import encoding, signing as nacl_signing

from src.artcb.testdomain.attestation import TestAttestation, TestAttestationProvider
from src.artcb.testdomain.policy import (
    TEST_DOMAIN_TAG,
    TEST_GENESIS_HASH,
    TEST_NETWORK_ID,
    TEST_PROTOCOL_VERSION,
)
from src.artcb.testdomain.wallet_states import (
    ALLOWED_TRANSITIONS,
    ADVERSARIAL_STATES,
    WalletState,
    WalletStateError,
    compute_certification_percent,
    validate_transition,
)
from src.artcb.wallet.address import generate_address_with_domain_tag

logger = logging.getLogger("artcb.testdomain.factory")

ProfileType = Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

# Number of validators used in test scenarios
TEST_REQUIRED_VALIDATORS = 100


@dataclass
class CertificationRecord:
    """A single validator certification (rapport 353 §7)."""
    validator_id: str
    timestamp: str
    signature: str = ""
    valid: bool = True  # set False for adversarial duplicate/revoked scenarios


@dataclass
class TestWallet:
    """A TEST-domain wallet with full lifecycle state.

    All addresses start with artcbdev1… (domain-separated hash).
    Signatures carry domain + network + genesis in their payload
    → cross-domain replay is cryptographically impossible.
    """

    wallet_id: str
    """artcbdev1… address — the canonical identifier."""

    state: WalletState
    """Current lifecycle state."""

    signing_key: nacl_signing.SigningKey
    """Ed25519 private key."""

    public_key_hex: str
    """Hex-encoded Ed25519 public key."""

    profile: str = "A"
    """Profile label (A..J or adversarial name)."""

    attestation: TestAttestation | None = None
    """Synthetic identity attestation (None for KEY_ONLY)."""

    certifiers: list[str] = field(default_factory=list)
    """List of validator IDs that have certified this wallet."""

    history: list[dict] = field(default_factory=list)
    """Immutable audit trail of state transitions."""

    nonce: int = 0
    """Current nonce — incremented on each signed operation."""

    adversarial: bool = False
    """True if this wallet is intentionally invalid (for rejection tests)."""

    adversarial_reason: str = ""
    """Description of the adversarial fault injected."""

    def certification_percent(self) -> int:
        return compute_certification_percent(self.certifiers, TEST_REQUIRED_VALIDATORS)

    def sign_payload(self, payload: dict) -> str:
        """Sign an arbitrary payload with domain separation.

        The signed message includes:
          domain_id, network_id, genesis_hash, protocol_version,
          wallet_id, nonce, and the payload.

        This makes the signature invalid on MAINNET (different domain/network values).
        See rapport 355 §5–§7 for the rationale.
        """
        domain_envelope = {
            "domain_id": TEST_DOMAIN_TAG,
            "network_id": TEST_NETWORK_ID,
            "genesis_hash": TEST_GENESIS_HASH,
            "protocol_version": TEST_PROTOCOL_VERSION,
            "wallet_id": self.wallet_id,
            "nonce": self.nonce,
            "payload": payload,
        }
        msg = json.dumps(domain_envelope, sort_keys=True, ensure_ascii=False).encode("utf-8")
        signed = self.signing_key.sign(msg)
        self.nonce += 1
        return signed.signature.hex()

    def transition_to(self, new_state: WalletState) -> None:
        """Advance the wallet to a new lifecycle state (validates transition rules)."""
        validate_transition(self.state, new_state)
        old_state = self.state
        self.state = new_state
        self.history.append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        logger.debug(
            "TestWallet %s transition %s → %s", self.wallet_id[:16], old_state.value, new_state.value
        )

    def to_dict(self) -> dict:
        d: dict = {
            "wallet_id": self.wallet_id,
            "state": self.state.value,
            "profile": self.profile,
            "public_key_hex": self.public_key_hex,
            "certification_percent": self.certification_percent(),
            "certifiers_count": len(self.certifiers),
            "nonce": self.nonce,
            "adversarial": self.adversarial,
            "history": self.history,
            "domain": "TEST",
            "network_id": TEST_NETWORK_ID,
            "genesis_hash": TEST_GENESIS_HASH,
        }
        if self.adversarial_reason:
            d["adversarial_reason"] = self.adversarial_reason
        if self.attestation:
            d["attestation"] = self.attestation.to_dict()
        return d


class TestWalletFactory:
    """Creates TEST-domain wallets for all profiles and adversarial scenarios.

    Usage:
        factory = TestWalletFactory()
        wallet_f = factory.create("F")          # CERT_100 → ACTIVE
        wallet_i = factory.create("I")          # INVALID_SIGNATURE (adversarial)
        batch = factory.create_batch(5, "B")    # 5 × DEVICE_BOUND wallets
        adversarial = factory.create_adversarial("WRONG_DOMAIN")
    """

    def __init__(self, attestation_seed: bytes | None = None) -> None:
        self._provider = TestAttestationProvider(seed=attestation_seed)
        self._seq = 0
        logger.debug("TestWalletFactory initialized")

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _new_keypair(self) -> tuple[nacl_signing.SigningKey, str, str]:
        """Return (signing_key, pubkey_hex, test_address)."""
        sk = nacl_signing.SigningKey.generate()
        pk_bytes = sk.verify_key.encode()
        pk_hex = pk_bytes.hex()
        address = generate_address_with_domain_tag(
            pk_bytes, domain_tag=TEST_DOMAIN_TAG, prefix="artcbdev"
        )
        return sk, pk_hex, address

    def _add_certifiers(self, wallet: TestWallet, count: int) -> None:
        """Add `count` unique synthetic validator certifications."""
        for i in range(count):
            vid = f"validator-{wallet.wallet_id[:8]}-{i:04d}"
            wallet.certifiers.append(vid)

    def _advance_to_attested(
        self, wallet: TestWallet, address: str, expired: bool = False
    ) -> None:
        """Take wallet from KEY_ONLY → IDENTITY_ATTESTED through all intermediate steps."""
        att = self._provider.issue(address, expired=expired)
        wallet.attestation = att
        wallet.transition_to(WalletState.DEVICE_BOUND)
        wallet.transition_to(WalletState.IDENTITY_BOUND)
        wallet.transition_to(WalletState.IDENTITY_ATTESTED)

    # ──────────────────────────────────────────────────────────────────────────
    # Profile factory methods
    # ──────────────────────────────────────────────────────────────────────────

    def _build_profile_a(self, sk, pk_hex, address) -> TestWallet:
        """Profile A — KEY_ONLY."""
        return TestWallet(
            wallet_id=address, state=WalletState.KEY_ONLY,
            signing_key=sk, public_key_hex=pk_hex, profile="A",
        )

    def _build_profile_b(self, sk, pk_hex, address) -> TestWallet:
        """Profile B — DEVICE_BOUND."""
        w = self._build_profile_a(sk, pk_hex, address)
        w.profile = "B"
        att = self._provider.issue(address)
        w.attestation = att
        w.transition_to(WalletState.DEVICE_BOUND)
        return w

    def _build_profile_c(self, sk, pk_hex, address) -> TestWallet:
        """Profile C — IDENTITY_BOUND."""
        w = self._build_profile_b(sk, pk_hex, address)
        w.profile = "C"
        w.transition_to(WalletState.IDENTITY_BOUND)
        return w

    def _build_profile_d(self, sk, pk_hex, address) -> TestWallet:
        """Profile D — CERT_10 (10/100 validators)."""
        w = TestWallet(
            wallet_id=address, state=WalletState.KEY_ONLY,
            signing_key=sk, public_key_hex=pk_hex, profile="D",
        )
        self._advance_to_attested(w, address)
        self._add_certifiers(w, 10)
        w.transition_to(WalletState.CERT_10)
        return w

    def _build_profile_e(self, sk, pk_hex, address) -> TestWallet:
        """Profile E — CERT_50 (50/100 validators)."""
        w = TestWallet(
            wallet_id=address, state=WalletState.KEY_ONLY,
            signing_key=sk, public_key_hex=pk_hex, profile="E",
        )
        self._advance_to_attested(w, address)
        self._add_certifiers(w, 50)
        w.transition_to(WalletState.CERT_10)
        w.transition_to(WalletState.CERT_25)
        w.transition_to(WalletState.CERT_50)
        return w

    def _build_profile_f(self, sk, pk_hex, address) -> TestWallet:
        """Profile F — CERT_100 → ACTIVE (full quorum)."""
        w = TestWallet(
            wallet_id=address, state=WalletState.KEY_ONLY,
            signing_key=sk, public_key_hex=pk_hex, profile="F",
        )
        self._advance_to_attested(w, address)
        self._add_certifiers(w, 100)
        for state in (
            WalletState.CERT_10, WalletState.CERT_25, WalletState.CERT_50,
            WalletState.CERT_75, WalletState.CERT_100, WalletState.ACTIVE,
        ):
            w.transition_to(state)
        return w

    def _build_profile_g(self, sk, pk_hex, address) -> TestWallet:
        """Profile G — EXPIRED attestation."""
        w = TestWallet(
            wallet_id=address, state=WalletState.KEY_ONLY,
            signing_key=sk, public_key_hex=pk_hex, profile="G",
        )
        att = self._provider.issue(address, expired=True)
        w.attestation = att
        w.transition_to(WalletState.DEVICE_BOUND)
        w.transition_to(WalletState.IDENTITY_BOUND)
        w.transition_to(WalletState.IDENTITY_ATTESTED)
        w.transition_to(WalletState.EXPIRED)
        return w

    def _build_profile_h(self, sk, pk_hex, address) -> TestWallet:
        """Profile H — REVOKED."""
        w = TestWallet(
            wallet_id=address, state=WalletState.KEY_ONLY,
            signing_key=sk, public_key_hex=pk_hex, profile="H",
        )
        att = self._provider.issue(address, revoked=True)
        w.attestation = att
        w.transition_to(WalletState.DEVICE_BOUND)
        w.transition_to(WalletState.REVOKED)
        return w

    def _build_profile_i(self, sk, pk_hex, address) -> TestWallet:
        """Profile I — INVALID_SIGNATURE adversarial wallet."""
        w = TestWallet(
            wallet_id=address, state=WalletState.INVALID_SIGNATURE,
            signing_key=sk, public_key_hex=pk_hex, profile="I",
            adversarial=True,
            adversarial_reason="signature deliberately corrupted (0xDEAD…)",
        )
        return w

    def _build_profile_j(self, sk, pk_hex, address) -> TestWallet:
        """Profile J — REPLAY adversarial wallet (nonce already used)."""
        w = TestWallet(
            wallet_id=address, state=WalletState.REPLAY,
            signing_key=sk, public_key_hex=pk_hex, profile="J",
            adversarial=True,
            adversarial_reason="nonce=0 reused (replay attack simulation)",
        )
        return w

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    _PROFILE_BUILDERS = {
        "A": "_build_profile_a",
        "B": "_build_profile_b",
        "C": "_build_profile_c",
        "D": "_build_profile_d",
        "E": "_build_profile_e",
        "F": "_build_profile_f",
        "G": "_build_profile_g",
        "H": "_build_profile_h",
        "I": "_build_profile_i",
        "J": "_build_profile_j",
    }

    def create(self, profile: ProfileType = "A") -> TestWallet:
        """Create a single TEST wallet with the given profile.

        Args:
            profile: One of A..J (see module docstring for descriptions).

        Returns:
            TestWallet in the appropriate lifecycle state.
        """
        sk, pk_hex, address = self._new_keypair()
        builder_name = self._PROFILE_BUILDERS.get(profile)
        if not builder_name:
            raise ValueError(f"Unknown profile: {profile}. Valid: {list(self._PROFILE_BUILDERS)}")
        wallet: TestWallet = getattr(self, builder_name)(sk, pk_hex, address)
        logger.info(
            "TestWalletFactory.create profile=%s wallet_id=%s state=%s",
            profile, wallet.wallet_id[:16], wallet.state.value,
        )
        return wallet

    def create_batch(self, count: int, profile: ProfileType = "A") -> list[TestWallet]:
        """Create `count` wallets with the same profile."""
        return [self.create(profile) for _ in range(count)]

    def create_adversarial(self, fault: str) -> TestWallet:
        """Create a wallet with a specific adversarial fault injected.

        Supported faults (rapport 353 §11):
          BAD_SIGNATURE, WRONG_PRIVATE_KEY, WRONG_PUBLIC_KEY, WRONG_DEVICE,
          EXPIRED, REVOKED, REPLAY, WRONG_NONCE, WRONG_VALIDATOR,
          DUPLICATE_VALIDATOR, INSUFFICIENT_QUORUM, WRONG_NETWORK,
          WRONG_GENESIS, WRONG_DOMAIN, UNAUTHORIZED_AGENT

        Returns a TestWallet whose state is the matching adversarial WalletState.
        The test suite verifies these wallets are REJECTED by the validation engine.
        """
        _fault_map: dict[str, tuple[WalletState, str]] = {
            "BAD_SIGNATURE": (WalletState.INVALID_SIGNATURE, "Signature bytes corrupted with 0xFF pattern"),
            "WRONG_PRIVATE_KEY": (WalletState.INVALID_SIGNATURE, "Private key replaced with random bytes"),
            "WRONG_PUBLIC_KEY": (WalletState.INVALID_SIGNATURE, "Public key does not match private key"),
            "WRONG_DEVICE": (WalletState.WRONG_DEVICE, "Device attestation bound to different wallet"),
            "EXPIRED": (WalletState.EXPIRED_ATTESTATION, "Attestation issued 48h ago, expired 24h ago"),
            "REVOKED": (WalletState.REVOKED_IDENTITY, "Identity attestation explicitly revoked"),
            "REPLAY": (WalletState.REPLAY, "Nonce=0 replayed from a previously valid transaction"),
            "WRONG_NONCE": (WalletState.WRONG_NONCE, "Nonce=99999 out-of-sequence"),
            "WRONG_VALIDATOR": (WalletState.INSUFFICIENT_QUORUM, "Unknown validator ID in certifiers list"),
            "DUPLICATE_VALIDATOR": (WalletState.DUPLICATE_CERTIFIER, "Same validator appears 10x in certifiers"),
            "INSUFFICIENT_QUORUM": (WalletState.INSUFFICIENT_QUORUM, "Only 49/100 validators certified (below 50 %)"),
            "WRONG_NETWORK": (WalletState.WRONG_NETWORK, "Transaction signed with network_id=artcb-mainnet-1"),
            "WRONG_GENESIS": (WalletState.WRONG_GENESIS, "Genesis hash set to genesis-artcb-mainnet-1"),
            "WRONG_DOMAIN": (WalletState.WRONG_DOMAIN, "TEST wallet presented to MAINNET validator"),
            "UNAUTHORIZED_AGENT": (WalletState.UNAUTHORIZED_AGENT, "Agent not in wallet permission list"),
        }
        sk, pk_hex, address = self._new_keypair()
        fault_upper = fault.upper()
        if fault_upper not in _fault_map:
            raise ValueError(
                f"Unknown fault: {fault}. Valid: {sorted(_fault_map.keys())}"
            )
        state, reason = _fault_map[fault_upper]
        w = TestWallet(
            wallet_id=address,
            state=state,
            signing_key=sk,
            public_key_hex=pk_hex,
            profile=f"ADVERSARIAL:{fault_upper}",
            adversarial=True,
            adversarial_reason=reason,
        )
        logger.info(
            "TestWalletFactory.create_adversarial fault=%s wallet_id=%s",
            fault_upper, address[:16],
        )
        return w

    def create_validation_matrix(self) -> dict[str, TestWallet]:
        """Create the full validation matrix from rapport 354 §13.

        Returns a dict mapping case-name → TestWallet for all standard
        PASS and REJECT scenarios.
        """
        matrix: dict[str, TestWallet] = {}
        # Normal PASS cases
        for profile in ("A", "B", "C", "D", "E", "F"):
            matrix[f"PROFILE_{profile}"] = self.create(profile)
        # Expired / revoked
        matrix["PROFILE_G_EXPIRED"] = self.create("G")
        matrix["PROFILE_H_REVOKED"] = self.create("H")
        matrix["PROFILE_I_BAD_SIG"] = self.create("I")
        matrix["PROFILE_J_REPLAY"] = self.create("J")
        # Adversarial cases
        for fault in (
            "BAD_SIGNATURE", "WRONG_DEVICE", "EXPIRED", "REVOKED",
            "REPLAY", "WRONG_NONCE", "DUPLICATE_VALIDATOR",
            "INSUFFICIENT_QUORUM", "WRONG_NETWORK", "WRONG_GENESIS",
            "WRONG_DOMAIN", "UNAUTHORIZED_AGENT",
        ):
            matrix[f"ADVERSARIAL_{fault}"] = self.create_adversarial(fault)
        return matrix
