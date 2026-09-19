"""TEST DOMAIN wallet state machine — rapport 353 §5, rapport 355 §14+§27.

Formalises the WalletState enum and the valid transitions.

State machine:
  KEY_ONLY → DEVICE_BOUND → IDENTITY_BOUND → IDENTITY_ATTESTED
  → CERT_10 → CERT_25 → CERT_50 → CERT_75 → CERT_100 → ACTIVE

  From ACTIVE:
    ACTIVE → SUSPENDED (recoverable)
    ACTIVE → EXPIRED   (re-attestation required)
    ACTIVE → REVOKED   (irrecoverable without explicit RECOVERY procedure)
    ACTIVE → ROTATION_PENDING → ROTATED → ACTIVE (key rotation)
    REVOKED → RECOVERY  (only via explicit procedure)

Adversarial states (read-only — for testing rejection paths):
  INVALID_SIGNATURE, WRONG_DEVICE, EXPIRED_ATTESTATION,
  REPLAY, WRONG_NONCE, WRONG_NETWORK, REVOKED_IDENTITY,
  DUPLICATE_CERTIFIER, INSUFFICIENT_QUORUM, WRONG_GENESIS,
  UNAUTHORIZED_AGENT, WRONG_DOMAIN

Rules:
  - KEY_ONLY → CERT_100 is REJECTED (intermediate steps required)
  - CERT_50 → ACTIVE is REJECTED if protocol requires CERT_100
  - REVOKED → ACTIVE is REJECTED without RECOVERY
  - Any adversarial state → anything is REJECTED
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

from enum import Enum, auto
from typing import FrozenSet


class WalletState(Enum):
    """Wallet lifecycle states (rapport 353 §5 table, rapport 355 §27 table)."""

    # ── Normal lifecycle ─────────────────────────────────────────────────────
    KEY_ONLY = "KEY_ONLY"
    """Keypair exists; no device binding, no identity."""

    DEVICE_BOUND = "DEVICE_BOUND"
    """Wallet is bound to a (synthetic) device attestation."""

    IDENTITY_BOUND = "IDENTITY_BOUND"
    """A TEST identity is associated (not yet attested)."""

    IDENTITY_ATTESTED = "IDENTITY_ATTESTED"
    """TEST identity attestation is cryptographically valid."""

    CERT_10 = "CERT_10"
    """10 % of required validators have certified."""

    CERT_25 = "CERT_25"
    """25 % of required validators have certified."""

    CERT_50 = "CERT_50"
    """50 % of required validators have certified."""

    CERT_75 = "CERT_75"
    """75 % of required validators have certified."""

    CERT_100 = "CERT_100"
    """100 % of required validators have certified — quorum complete."""

    ACTIVE = "ACTIVE"
    """Wallet is fully authorised for normal operations."""

    MATURE = "MATURE"
    """Wallet meets stability/age criteria for advanced economic functions."""

    # ── Suspended / terminal states ──────────────────────────────────────────
    SUSPENDED = "SUSPENDED"
    """Temporarily suspended — recoverable."""

    EXPIRED = "EXPIRED"
    """Attestation or certification has expired."""

    REVOKED = "REVOKED"
    """Identity or key revoked — cannot become ACTIVE without RECOVERY."""

    RECOVERY = "RECOVERY"
    """Formal recovery procedure in progress."""

    ROTATION_PENDING = "ROTATION_PENDING"
    """Key rotation initiated — old key still valid during grace period."""

    ROTATED = "ROTATED"
    """New key active, old key retired."""

    # ── Adversarial / error states (test-only) ───────────────────────────────
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    """Signature does not verify against the registered public key."""

    WRONG_DEVICE = "WRONG_DEVICE"
    """Device attestation does not match the wallet binding."""

    EXPIRED_ATTESTATION = "EXPIRED_ATTESTATION"
    """Identity attestation is past its expiry timestamp."""

    REPLAY = "REPLAY"
    """Nonce or challenge has already been consumed (replay attack)."""

    WRONG_NONCE = "WRONG_NONCE"
    """Nonce value is out-of-sequence or malformed."""

    WRONG_NETWORK = "WRONG_NETWORK"
    """Transaction signed for a different NETWORK_ID."""

    REVOKED_IDENTITY = "REVOKED_IDENTITY"
    """The associated identity has been revoked."""

    DUPLICATE_CERTIFIER = "DUPLICATE_CERTIFIER"
    """Same validator certified more than once (double-counting attempt)."""

    INSUFFICIENT_QUORUM = "INSUFFICIENT_QUORUM"
    """Certification count is below the required threshold."""

    WRONG_GENESIS = "WRONG_GENESIS"
    """Genesis hash in the signed payload does not match this network."""

    UNAUTHORIZED_AGENT = "UNAUTHORIZED_AGENT"
    """Agent does not have permission to perform this action."""

    WRONG_DOMAIN = "WRONG_DOMAIN"
    """TEST transaction presented to MAINNET (or vice-versa)."""


# ──────────────────────────────────────────────────────────────────────────────
# Ordered progression for the happy path
# ──────────────────────────────────────────────────────────────────────────────

HAPPY_PATH_SEQUENCE: tuple[WalletState, ...] = (
    WalletState.KEY_ONLY,
    WalletState.DEVICE_BOUND,
    WalletState.IDENTITY_BOUND,
    WalletState.IDENTITY_ATTESTED,
    WalletState.CERT_10,
    WalletState.CERT_25,
    WalletState.CERT_50,
    WalletState.CERT_75,
    WalletState.CERT_100,
    WalletState.ACTIVE,
)

# States that represent adversarial / invalid inputs (test rejection paths)
ADVERSARIAL_STATES: FrozenSet[WalletState] = frozenset({
    WalletState.INVALID_SIGNATURE,
    WalletState.WRONG_DEVICE,
    WalletState.EXPIRED_ATTESTATION,
    WalletState.REPLAY,
    WalletState.WRONG_NONCE,
    WalletState.WRONG_NETWORK,
    WalletState.REVOKED_IDENTITY,
    WalletState.DUPLICATE_CERTIFIER,
    WalletState.INSUFFICIENT_QUORUM,
    WalletState.WRONG_GENESIS,
    WalletState.UNAUTHORIZED_AGENT,
    WalletState.WRONG_DOMAIN,
})

# Certification states in ascending order (for threshold checks)
CERT_STATES_ORDERED: tuple[WalletState, ...] = (
    WalletState.CERT_10,
    WalletState.CERT_25,
    WalletState.CERT_50,
    WalletState.CERT_75,
    WalletState.CERT_100,
)

# Certification thresholds (percent) matching each CERT state
CERT_THRESHOLDS: dict[WalletState, int] = {
    WalletState.CERT_10: 10,
    WalletState.CERT_25: 25,
    WalletState.CERT_50: 50,
    WalletState.CERT_75: 75,
    WalletState.CERT_100: 100,
}

# ──────────────────────────────────────────────────────────────────────────────
# Valid transitions (allowed_transitions[from] → set of allowed destinations)
# ──────────────────────────────────────────────────────────────────────────────

ALLOWED_TRANSITIONS: dict[WalletState, FrozenSet[WalletState]] = {
    WalletState.KEY_ONLY: frozenset({WalletState.DEVICE_BOUND}),
    WalletState.DEVICE_BOUND: frozenset({WalletState.IDENTITY_BOUND, WalletState.REVOKED}),
    WalletState.IDENTITY_BOUND: frozenset({WalletState.IDENTITY_ATTESTED, WalletState.REVOKED}),
    WalletState.IDENTITY_ATTESTED: frozenset({WalletState.CERT_10, WalletState.REVOKED, WalletState.EXPIRED}),
    WalletState.CERT_10: frozenset({WalletState.CERT_25, WalletState.REVOKED, WalletState.EXPIRED}),
    WalletState.CERT_25: frozenset({WalletState.CERT_50, WalletState.REVOKED, WalletState.EXPIRED}),
    WalletState.CERT_50: frozenset({WalletState.CERT_75, WalletState.REVOKED, WalletState.EXPIRED}),
    WalletState.CERT_75: frozenset({WalletState.CERT_100, WalletState.REVOKED, WalletState.EXPIRED}),
    WalletState.CERT_100: frozenset({WalletState.ACTIVE, WalletState.REVOKED, WalletState.EXPIRED}),
    WalletState.ACTIVE: frozenset({
        WalletState.SUSPENDED,
        WalletState.EXPIRED,
        WalletState.REVOKED,
        WalletState.ROTATION_PENDING,
        WalletState.MATURE,
    }),
    WalletState.MATURE: frozenset({
        WalletState.SUSPENDED,
        WalletState.EXPIRED,
        WalletState.REVOKED,
        WalletState.ROTATION_PENDING,
    }),
    WalletState.SUSPENDED: frozenset({WalletState.ACTIVE, WalletState.REVOKED}),
    WalletState.EXPIRED: frozenset({WalletState.IDENTITY_ATTESTED}),  # re-attestation
    WalletState.REVOKED: frozenset({WalletState.RECOVERY}),
    WalletState.RECOVERY: frozenset({WalletState.KEY_ONLY}),  # full restart after recovery
    WalletState.ROTATION_PENDING: frozenset({WalletState.ROTATED, WalletState.ACTIVE}),
    WalletState.ROTATED: frozenset({WalletState.ACTIVE}),
}


class WalletStateError(ValueError):
    """Raised when an invalid state transition is attempted."""


def validate_transition(current: WalletState, target: WalletState) -> None:
    """Assert that the transition current → target is allowed.

    Raises WalletStateError with a descriptive message on invalid transitions.
    Examples of forbidden transitions (rapport 353 §6):
      KEY_ONLY → CERT_100       (skips mandatory intermediate steps)
      CERT_50  → ACTIVE         (below 100 % quorum requirement)
      REVOKED  → ACTIVE         (must go through RECOVERY first)
      <adversarial> → anything  (adversarial states are terminal for tests)
    """
    if current in ADVERSARIAL_STATES:
        raise WalletStateError(
            f"Adversarial state {current.value} is terminal — no valid transition."
        )
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        allowed_names = ", ".join(s.value for s in sorted(allowed, key=lambda s: s.value))
        raise WalletStateError(
            f"Invalid transition {current.value} → {target.value}. "
            f"Allowed from {current.value}: [{allowed_names}]"
        )


def certification_percent_to_state(percent: int) -> WalletState:
    """Map a certification percentage to the corresponding WalletState.

    Uses the floor threshold: 12 % → CERT_10, 50 % → CERT_50, 100 % → CERT_100.
    Below 10 % → remains IDENTITY_ATTESTED.
    """
    if percent >= 100:
        return WalletState.CERT_100
    if percent >= 75:
        return WalletState.CERT_75
    if percent >= 50:
        return WalletState.CERT_50
    if percent >= 25:
        return WalletState.CERT_25
    if percent >= 10:
        return WalletState.CERT_10
    return WalletState.IDENTITY_ATTESTED


def compute_certification_percent(
    certifiers: list[str],
    required: int,
) -> int:
    """Compute certification percentage from a list of unique valid certifiers.

    Follows rapport 353 §7: count unique certifiers, divide by required.
    Duplicate certifiers are deduplicated before counting.
    """
    if required <= 0:
        return 0
    unique = len(set(certifiers))
    return min(100, int(unique / required * 100))
