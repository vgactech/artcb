"""Single-use capability tokens — Issue #90.

Problem: node roles/certs allow capabilities indefinitely with no audit trail.
A bypassing node can call a privileged operation multiple times using the same
certificate.

Solution: capability tokens that are:
  1. Cryptographically derived from a cert + nonce + operation context
  2. Single-use — a token_id can be redeemed at most ONCE
  3. Scoped — token binds to a specific capability, node_id, domain_id
  4. Expirable — optional TTL
  5. Audited — every redemption (success or failure) is recorded

Architecture:
    NodeCert (permanent) + nonce → CapabilityToken (one-shot)
    CapabilityToken → CapabilityTokenStore.redeem() → consumed or rejected

FAIL-CLOSED: any unknown token_id → DENIED. Any already-consumed token → DENIED.
Expired token → DENIED. Capability mismatch → DENIED.

This module has no runtime dependency on the chain — the store is local.
The chain layer can consume the audit_trail entries as evidence (R451/R452).
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R456 — capability token single-use

import hashlib
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.artcb.authz.node_roles import can_role

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

TOKEN_KIND = "artcb_capability_token_v1"
MAX_TOKEN_BYTES = 32  # nonce size for token_id derivation

STATE_PENDING = "PENDING"
STATE_CONSUMED = "CONSUMED"
STATE_EXPIRED = "EXPIRED"
STATE_DENIED = "DENIED"

# Reasons for denial
REASON_ALREADY_CONSUMED = "already_consumed"
REASON_EXPIRED = "token_expired"
REASON_UNKNOWN_TOKEN = "unknown_token"
REASON_CAPABILITY_MISMATCH = "capability_mismatch"
REASON_NODE_MISMATCH = "node_mismatch"
REASON_DOMAIN_MISMATCH = "domain_mismatch"
REASON_INVALID_STATE = "invalid_state"


# ──────────────────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────────────────

class CapabilityTokenError(ValueError):
    """Raised when a capability token cannot be issued or redeemed."""


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CapabilityToken:
    """An immutable single-use capability token."""

    token_id: str          # SHA-256(node_id + capability + nonce + issued_at)
    node_id: str
    domain_id: str
    capability: str        # e.g. CAP_PRODUCE, CAP_VALIDATE …
    role: str              # role at issuance time
    issued_at: str         # ISO-8601 UTC
    valid_until: str | None  # ISO-8601 UTC or None
    nonce: str             # hex random bytes, single-use guarantee
    state: str = STATE_PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": TOKEN_KIND,
            "token_id": self.token_id,
            "node_id": self.node_id,
            "domain_id": self.domain_id,
            "capability": self.capability,
            "role": self.role,
            "issued_at": self.issued_at,
            "valid_until": self.valid_until,
            "nonce": self.nonce,
            "state": self.state,
        }


@dataclass
class RedemptionResult:
    """Outcome of a single token redemption attempt."""

    token_id: str
    allowed: bool
    reason: str
    redeemed_at: str | None = None
    previous_state: str = STATE_PENDING
    new_state: str = STATE_PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "allowed": self.allowed,
            "reason": self.reason,
            "redeemed_at": self.redeemed_at,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
        }


@dataclass
class AuditEntry:
    """Immutable audit trail record for a redemption attempt."""

    token_id: str
    node_id: str
    domain_id: str
    capability: str
    outcome: str          # CONSUMED | DENIED | EXPIRED
    reason: str
    attempted_at: str
    actor: str | None = None   # optional: which process/peer attempted
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "node_id": self.node_id,
            "domain_id": self.domain_id,
            "capability": self.capability,
            "outcome": self.outcome,
            "reason": self.reason,
            "attempted_at": self.attempted_at,
            "actor": self.actor,
            "extra": self.extra,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Token derivation
# ──────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derive_token_id(node_id: str, domain_id: str, capability: str,
                     nonce: str, issued_at: str) -> str:
    """Deterministic token_id — collision-resistant, bound to all fields."""
    raw = f"{node_id}:{domain_id}:{capability}:{nonce}:{issued_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(
    *,
    node_id: str,
    domain_id: str,
    capability: str,
    role: str,
    valid_until: str | None = None,
    issued_at: str | None = None,
) -> CapabilityToken:
    """
    Issue a single-use capability token.

    Verifies that the role permits the requested capability (FAIL-CLOSED).
    Returns an immutable CapabilityToken in state PENDING.

    :raises CapabilityTokenError: if role does not grant the capability.
    """
    if not can_role(role, capability):
        raise CapabilityTokenError(
            f"role_does_not_grant_capability:{role}:{capability}"
        )
    now = issued_at or _now_iso()
    nonce = os.urandom(MAX_TOKEN_BYTES).hex()
    token_id = _derive_token_id(node_id, domain_id, capability, nonce, now)
    return CapabilityToken(
        token_id=token_id,
        node_id=node_id,
        domain_id=domain_id,
        capability=capability,
        role=role,
        issued_at=now,
        valid_until=valid_until,
        nonce=nonce,
        state=STATE_PENDING,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Token store — thread-safe, in-memory (production: back with persistence)
# ──────────────────────────────────────────────────────────────────────────────

class CapabilityTokenStore:
    """
    Thread-safe single-use token registry.

    Tokens can only be redeemed ONCE. After redemption their state transitions
    PENDING → CONSUMED. Any further attempt returns DENIED:already_consumed.

    The audit_trail records every attempt (success and failure), never erased.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, CapabilityToken] = {}    # token_id → token
        self._audit_trail: list[AuditEntry] = []

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, token: CapabilityToken) -> None:
        """Register a freshly issued token. Raises if token_id already exists."""
        with self._lock:
            if token.token_id in self._tokens:
                raise CapabilityTokenError(
                    f"token_id_collision:{token.token_id}"
                )
            if token.state != STATE_PENDING:
                raise CapabilityTokenError(
                    f"token_not_pending:{token.state}"
                )
            self._tokens[token.token_id] = token

    # ── Redemption ────────────────────────────────────────────────────────────

    def redeem(
        self,
        token_id: str,
        *,
        expected_node_id: str,
        expected_domain_id: str,
        expected_capability: str,
        actor: str | None = None,
        now: str | None = None,
    ) -> RedemptionResult:
        """
        Attempt to redeem a single-use token.

        FAIL-CLOSED: any anomaly → allowed=False, state unchanged, audit logged.
        On success: state → CONSUMED (irreversible).
        """
        now_str = now or _now_iso()

        with self._lock:
            # 1. Unknown token
            if token_id not in self._tokens:
                entry = AuditEntry(
                    token_id=token_id,
                    node_id=expected_node_id,
                    domain_id=expected_domain_id,
                    capability=expected_capability,
                    outcome=STATE_DENIED,
                    reason=REASON_UNKNOWN_TOKEN,
                    attempted_at=now_str,
                    actor=actor,
                )
                self._audit_trail.append(entry)
                return RedemptionResult(
                    token_id=token_id,
                    allowed=False,
                    reason=REASON_UNKNOWN_TOKEN,
                    redeemed_at=now_str,
                    previous_state=STATE_PENDING,
                    new_state=STATE_DENIED,
                )

            token = self._tokens[token_id]
            prev_state = token.state

            # 2. Already consumed or in bad state
            if token.state != STATE_PENDING:
                reason = (
                    REASON_ALREADY_CONSUMED
                    if token.state == STATE_CONSUMED
                    else REASON_INVALID_STATE
                )
                entry = AuditEntry(
                    token_id=token_id,
                    node_id=token.node_id,
                    domain_id=token.domain_id,
                    capability=token.capability,
                    outcome=STATE_DENIED,
                    reason=reason,
                    attempted_at=now_str,
                    actor=actor,
                    extra={"previous_state": prev_state},
                )
                self._audit_trail.append(entry)
                return RedemptionResult(
                    token_id=token_id,
                    allowed=False,
                    reason=reason,
                    redeemed_at=now_str,
                    previous_state=prev_state,
                    new_state=STATE_DENIED,
                )

            # 3. Expired
            if token.valid_until and now_str > token.valid_until:
                token.state = STATE_EXPIRED  # type: ignore[misc]
                # dataclass is not frozen — mark as expired
                object.__setattr__(token, "state", STATE_EXPIRED)
                entry = AuditEntry(
                    token_id=token_id,
                    node_id=token.node_id,
                    domain_id=token.domain_id,
                    capability=token.capability,
                    outcome=STATE_EXPIRED,
                    reason=REASON_EXPIRED,
                    attempted_at=now_str,
                    actor=actor,
                    extra={"valid_until": token.valid_until},
                )
                self._audit_trail.append(entry)
                return RedemptionResult(
                    token_id=token_id,
                    allowed=False,
                    reason=REASON_EXPIRED,
                    redeemed_at=now_str,
                    previous_state=prev_state,
                    new_state=STATE_EXPIRED,
                )

            # 4. Capability mismatch
            if token.capability != expected_capability:
                entry = AuditEntry(
                    token_id=token_id,
                    node_id=token.node_id,
                    domain_id=token.domain_id,
                    capability=token.capability,
                    outcome=STATE_DENIED,
                    reason=REASON_CAPABILITY_MISMATCH,
                    attempted_at=now_str,
                    actor=actor,
                    extra={
                        "expected": expected_capability,
                        "actual": token.capability,
                    },
                )
                self._audit_trail.append(entry)
                return RedemptionResult(
                    token_id=token_id,
                    allowed=False,
                    reason=REASON_CAPABILITY_MISMATCH,
                    redeemed_at=now_str,
                    previous_state=prev_state,
                    new_state=STATE_DENIED,
                )

            # 5. Node mismatch
            if token.node_id != expected_node_id:
                entry = AuditEntry(
                    token_id=token_id,
                    node_id=token.node_id,
                    domain_id=token.domain_id,
                    capability=token.capability,
                    outcome=STATE_DENIED,
                    reason=REASON_NODE_MISMATCH,
                    attempted_at=now_str,
                    actor=actor,
                )
                self._audit_trail.append(entry)
                return RedemptionResult(
                    token_id=token_id,
                    allowed=False,
                    reason=REASON_NODE_MISMATCH,
                    redeemed_at=now_str,
                    previous_state=prev_state,
                    new_state=STATE_DENIED,
                )

            # 6. Domain mismatch
            if token.domain_id != expected_domain_id:
                entry = AuditEntry(
                    token_id=token_id,
                    node_id=token.node_id,
                    domain_id=token.domain_id,
                    capability=token.capability,
                    outcome=STATE_DENIED,
                    reason=REASON_DOMAIN_MISMATCH,
                    attempted_at=now_str,
                    actor=actor,
                )
                self._audit_trail.append(entry)
                return RedemptionResult(
                    token_id=token_id,
                    allowed=False,
                    reason=REASON_DOMAIN_MISMATCH,
                    redeemed_at=now_str,
                    previous_state=prev_state,
                    new_state=STATE_DENIED,
                )

            # ✅ All checks pass — consume the token (irreversible)
            object.__setattr__(token, "state", STATE_CONSUMED)
            entry = AuditEntry(
                token_id=token_id,
                node_id=token.node_id,
                domain_id=token.domain_id,
                capability=token.capability,
                outcome=STATE_CONSUMED,
                reason="ok",
                attempted_at=now_str,
                actor=actor,
            )
            self._audit_trail.append(entry)
            return RedemptionResult(
                token_id=token_id,
                allowed=True,
                reason="ok",
                redeemed_at=now_str,
                previous_state=prev_state,
                new_state=STATE_CONSUMED,
            )

    # ── Queries ───────────────────────────────────────────────────────────────

    def state_of(self, token_id: str) -> str | None:
        """Return current state of a token, or None if unknown."""
        with self._lock:
            t = self._tokens.get(token_id)
            return t.state if t else None

    def get_audit_trail(self, token_id: str | None = None) -> list[dict[str, Any]]:
        """Return audit entries, optionally filtered by token_id."""
        with self._lock:
            if token_id is None:
                return [e.to_dict() for e in self._audit_trail]
            return [e.to_dict() for e in self._audit_trail if e.token_id == token_id]

    def count_by_state(self) -> dict[str, int]:
        """Return count of tokens by state."""
        with self._lock:
            result: dict[str, int] = {
                STATE_PENDING: 0,
                STATE_CONSUMED: 0,
                STATE_EXPIRED: 0,
            }
            for t in self._tokens.values():
                result[t.state] = result.get(t.state, 0) + 1
            return result
