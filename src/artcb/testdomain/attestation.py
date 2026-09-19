"""TEST DOMAIN attestation provider — rapport 353 §7, rapport 354 §7.

Produces deterministic synthetic attestations for TEST wallets.
The validation engine is IDENTICAL to production; only the source of proofs differs:
  - Production: real biometric / hardware proofs
  - TEST: synthetic TestAttestation objects with explicit identity markers

Key invariants (rapport 354 §5):
  - A TestAttestation is NEVER accepted as a production HUMAN_UNIQUE proof.
  - The attestation type field is always "TEST" — impossible to confuse with "REAL".
  - Attestations are cryptographically signed (Ed25519) with the TEST node's key
    → they are verifiable, not mocked.
  - Expiry timestamps are configurable for testing EXPIRED scenarios.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

logger = logging.getLogger("artcb.testdomain.attestation")

# Test identity subject prefix (rapport 354 §7)
_TEST_HUMAN_PREFIX = "TEST-HUMAN"
_TEST_DEVICE_PREFIX = "TEST-DEVICE"

# Default TTL for a fresh TEST attestation
_DEFAULT_TTL_SECONDS = 86_400  # 24 h


@dataclass
class TestAttestation:
    """Synthetic identity attestation for TEST domain wallets.

    Equivalent of a real biometric/hardware proof, but explicitly marked TEST.
    Used as input to the same validation engine as production.
    """

    subject_id: str
    """e.g. TEST-HUMAN-000001 — deterministic, not a real human."""

    attestation_type: Literal["TEST"] = "TEST"
    """Always 'TEST' — never 'REAL', 'HUMAN_UNIQUE', or 'BIOMETRIC'."""

    device_id: str = ""
    """Synthetic device identifier, e.g. TEST-DEVICE-000001."""

    wallet_address: str = ""
    """The TEST wallet address this attestation is bound to."""

    issued_at: str = ""
    """ISO-8601 UTC timestamp."""

    expires_at: str = ""
    """ISO-8601 UTC timestamp — set in the past to test EXPIRED scenarios."""

    policy_version: str = "testdomain-v1"
    """Attestation policy version."""

    signature: str = ""
    """Hex Ed25519 signature over the canonical attestation payload."""

    revoked: bool = False
    """True → simulates a REVOKED identity (for adversarial tests)."""

    extra: dict = field(default_factory=dict)
    """Additional fields for adversarial scenarios (e.g. bad_nonce, wrong_domain)."""

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True if this attestation is past its expiry."""
        if not self.expires_at:
            return False
        t = now or datetime.now(UTC)
        try:
            exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return t > exp
        except ValueError:
            return True  # malformed = treat as expired

    def is_valid_for_test(self, now: datetime | None = None) -> tuple[bool, str]:
        """Validate this attestation for TEST domain use.

        Returns (valid, reason). Mirrors the production validation pipeline
        (rapport 353 §4) but accepts synthetic proofs.
        """
        if self.attestation_type != "TEST":
            return False, f"wrong_attestation_type:{self.attestation_type}"
        if self.revoked:
            return False, "revoked_identity"
        if not self.subject_id.startswith(_TEST_HUMAN_PREFIX):
            return False, f"invalid_subject_id:{self.subject_id}"
        if not self.signature:
            return False, "missing_signature"
        if self.is_expired(now):
            return False, "expired_attestation"
        if not self.wallet_address.startswith("artcbdev"):
            return False, f"wrong_domain_prefix:{self.wallet_address}"
        return True, "valid_test_attestation"

    def canonical_payload(self) -> bytes:
        """Deterministic bytes to sign/verify."""
        d = {
            "subject_id": self.subject_id,
            "attestation_type": self.attestation_type,
            "device_id": self.device_id,
            "wallet_address": self.wallet_address,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "policy_version": self.policy_version,
            "revoked": self.revoked,
        }
        return json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")

    def fingerprint(self) -> str:
        """SHA-256 hex of the canonical payload (for logging / dedup)."""
        return hashlib.sha256(self.canonical_payload()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "subject_id": self.subject_id,
            "attestation_type": self.attestation_type,
            "device_id": self.device_id,
            "wallet_address": self.wallet_address,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "policy_version": self.policy_version,
            "signature": self.signature,
            "revoked": self.revoked,
            "fingerprint": self.fingerprint(),
        }


class TestAttestationProvider:
    """Factory for synthetic TestAttestation objects (rapport 354 §7).

    Produces deterministic, sequenced identities:
        TEST-HUMAN-000001, TEST-HUMAN-000002, …
        TEST-DEVICE-000001, TEST-DEVICE-000002, …

    Signing key is a throwaway Ed25519 key generated at instantiation.
    For reproducible tests, pass a fixed seed.
    """

    def __init__(self, seed: bytes | None = None) -> None:
        from nacl import signing as nacl_signing
        if seed is not None:
            if len(seed) != 32:
                raise ValueError("seed must be exactly 32 bytes")
            self._signing_key = nacl_signing.SigningKey(seed)
        else:
            self._signing_key = nacl_signing.SigningKey.generate()
        self._counter = 0
        logger.debug(
            "TestAttestationProvider initialized pubkey=%s",
            self._signing_key.verify_key.encode().hex()[:16],
        )

    @property
    def verify_key_hex(self) -> str:
        return self._signing_key.verify_key.encode().hex()

    def _next_seq(self) -> str:
        self._counter += 1
        return f"{self._counter:06d}"

    def issue(
        self,
        wallet_address: str,
        *,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        revoked: bool = False,
        expired: bool = False,
        extra: dict | None = None,
    ) -> TestAttestation:
        """Issue a new synthetic attestation for a TEST wallet.

        Args:
            wallet_address: The artcbdev1… address of the TEST wallet.
            ttl_seconds: How long the attestation is valid (default 24h).
                         Set to 0 to create an already-expired attestation.
            revoked: If True, the attestation is pre-revoked (adversarial).
            expired: If True, the issued_at/expires_at timestamps are set in
                     the past (adversarial EXPIRED scenario).
            extra: Optional extra fields for adversarial scenarios.

        Returns:
            Signed TestAttestation.
        """
        seq = self._next_seq()
        subject_id = f"{_TEST_HUMAN_PREFIX}-{seq}"
        device_id = f"{_TEST_DEVICE_PREFIX}-{seq}"

        now = datetime.now(UTC)
        if expired:
            issued_at = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            expires_at = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            issued_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            expires_at = (now + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

        att = TestAttestation(
            subject_id=subject_id,
            device_id=device_id,
            wallet_address=wallet_address,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked=revoked,
            extra=extra or {},
        )

        # Sign the canonical payload
        signed = self._signing_key.sign(att.canonical_payload())
        att.signature = signed.signature.hex()

        logger.debug(
            "Issued TestAttestation subject=%s wallet=%s revoked=%s expired=%s",
            subject_id, wallet_address[:16], revoked, expired,
        )
        return att

    def issue_batch(self, addresses: list[str], **kwargs) -> list[TestAttestation]:
        """Issue attestations for a list of TEST wallet addresses."""
        return [self.issue(addr, **kwargs) for addr in addresses]

    def verify(self, att: TestAttestation) -> tuple[bool, str]:
        """Verify the Ed25519 signature on a TestAttestation.

        Returns (ok, reason). Used by the validation engine to confirm
        the attestation is genuinely from this provider.
        """
        if not att.signature:
            return False, "missing_signature"
        try:
            sig_bytes = bytes.fromhex(att.signature)
            self._signing_key.verify_key.verify(att.canonical_payload(), sig_bytes)
            return True, "signature_valid"
        except Exception as exc:
            return False, f"signature_invalid:{exc}"
