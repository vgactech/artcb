"""Official artcb-devnet-1 cryptographic policy (D-032).

User lock 2026-08-31: Option B primary (ML-DSA-65 preferred, Ed25519
temporarily allowed). Option C hybrid signatures are used whenever ML-DSA-65
is available on the signer. Economic V-01…V-07 are unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

NETWORK_ID: Final[str] = "artcb-devnet-1"
PROTOCOL_VERSION: Final[str] = "174-devnet-1"
# Declared network genesis identifier (creator_rights.json), not a live block hash.
GENESIS_HASH: Final[str] = "genesis-artcb-v2"
PREFERRED_SIG: Final[str] = "ML-DSA-65"
TEMPORARY_SIG: Final[str] = "Ed25519"
HYBRID_SIG: Final[str] = "hybrid:ed25519+ML-DSA-65"
POLICY_ID: Final[str] = "B-preferred-pqc"
POLICY_VERSION: Final[str] = "174-devnet-crypto-b"
# Temporary Ed25519-only compatibility window (UTC). After this instant, B
# becomes A (ML-DSA-65 required) unless a later decision extends it.
ED25519_ONLY_UNTIL: Final[str] = "2026-12-31T00:00:00Z"

# Messages that MUST use hybrid (C) when the local node has ML-DSA-65.
HIGH_VALUE_MESSAGES: Final[tuple[str, ...]] = (
    "block_append",
    "node_identity",
    "settlement",
    "peer_handshake",
)

# Messages that may remain Ed25519-only during the window.
LOW_VALUE_MESSAGES: Final[tuple[str, ...]] = (
    "health",
    "peer_register_unsigned",
)

# D-034 A: both hybrid legs must verify. OR is forbidden.
HYBRID_VERIFY_MODE: Final[str] = "AND"
# Capability history is keyed by KEM fingerprint, not a spoofable peer_id label.
IDENTITY_BIND: Final[str] = "kem_public_sha256"


class CryptoPolicyError(ValueError):
    """Peer rejected by the official crypto policy."""


def fallback_still_open(now: datetime | None = None) -> bool:
    n = now or datetime.now(UTC)
    if n.tzinfo is None:
        n = n.replace(tzinfo=UTC)
    limit = datetime.fromisoformat(ED25519_ONLY_UNTIL.replace("Z", "+00:00"))
    return n < limit


def local_suite(pqc_available: bool) -> str:
    if pqc_available:
        return HYBRID_SIG
    return TEMPORARY_SIG


def capabilities(pqc_available: bool) -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "network_id": NETWORK_ID,
        "protocol_version": PROTOCOL_VERSION,
        "genesis_hash": GENESIS_HASH,
        "preferred": PREFERRED_SIG,
        "temporary_allowed": TEMPORARY_SIG if fallback_still_open() else None,
        "ed25519_only_until": ED25519_ONLY_UNTIL,
        "fallback_open": fallback_still_open(),
        "local_suite": local_suite(pqc_available),
        "hybrid_when_pqc": True,
        "hybrid_verify_mode": HYBRID_VERIFY_MODE,
        "identity_bind": IDENTITY_BIND,
        "high_value_messages": list(HIGH_VALUE_MESSAGES),
        "anti_downgrade": True,
        "silent_downgrade_forbidden": True,
        "unsigned_pqc_not_trusted": True,
    }


def accept_peer_protocol(
    *,
    advertised_network_id: str | None,
    advertised_protocol_version: str | None,
    advertised_genesis_hash: str | None,
) -> tuple[bool, str]:
    """DV-03 B: match network_id + protocol_version + genesis_hash.

    Missing fields (legacy node) are not a silent match: the peer is
    *reachable* but not protocol-compatible.
    """
    nid = (advertised_network_id or "").strip()
    pv = (advertised_protocol_version or "").strip()
    gh = (advertised_genesis_hash or "").strip()
    if not nid or not pv or not gh:
        return False, "legacy_missing_protocol_fields"
    if nid != NETWORK_ID:
        return False, f"network_id_mismatch:{nid}"
    if pv != PROTOCOL_VERSION:
        return False, f"protocol_version_mismatch:{pv}"
    if gh != GENESIS_HASH:
        return False, f"genesis_hash_mismatch:{gh}"
    return True, "protocol_compatible"


def accept_peer_suite(
    *,
    advertised: str | None,
    previously_seen: str | None,
    pqc_available_here: bool,
    signed: bool = False,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return (ok, reason). Anti-downgrade uses *signed* capability history
    keyed by KEM fingerprint (D-034). Unsigned PQC claims are not trusted.
    """
    suite = (advertised or "").strip() or TEMPORARY_SIG
    prev = (previously_seen or "").strip() or None
    has_pqc = PREFERRED_SIG in suite or "mldsa" in suite.lower() or suite.startswith("hybrid:")
    has_only_ed = suite in {TEMPORARY_SIG, "Ed25519 (fallback)", "ed25519"} and not has_pqc

    if prev and PREFERRED_SIG in prev and has_only_ed:
        return False, "anti_downgrade: peer previously advertised ML-DSA-65"

    if has_pqc:
        if not signed:
            return True, "unsigned_untrusted_pqc"
        return True, "pqc_preferred_accepted"

    if has_only_ed:
        if not fallback_still_open(now):
            return False, "ed25519_window_closed"
        return True, "ed25519_temporary_allowed"

    return False, f"unknown_suite:{suite}"


def public_health_block(pqc_available: bool) -> dict[str, Any]:
    return {
        "available": pqc_available,
        "algorithm": PREFERRED_SIG if pqc_available else f"{TEMPORARY_SIG} (fallback)",
        "policy": capabilities(pqc_available),
        "availability_is_not_enforcement": True,
        "high_value_hybrid_enforced": False,
        "ed25519_only_still_accepted": fallback_still_open(),
        "action_required": (
            None
            if pqc_available
            else (
                "liboqs absent — Ed25519 temporary under D-032 B until "
                f"{ED25519_ONLY_UNTIL}. Install cmake+gcc then pip install liboqs-python."
            )
        ),
    }
