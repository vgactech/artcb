"""TEST DOMAIN cryptographic policy — mirror of crypto_policy.py for the test network.

Architecture (rapport 355 §8, §13):
  - NETWORK_ID / PROTOCOL_VERSION / GENESIS_HASH are DIFFERENT from mainnet.
  - P2P accept_peer_protocol() will reject cross-domain peers.
  - TEST domain tag is included in EVERY address derivation and signature payload
    → a signature produced on TEST is mathematically invalid on MAINNET
      (cross-domain replay protection).

Constants follow the same naming discipline as crypto_policy.py (D-004: English code).
"""

from __future__ import annotations

from typing import Any, Final

# ──────────────────────────────────────────────────────────────────────────────
# Domain separation tags — injected into address hash and signature payloads
# ──────────────────────────────────────────────────────────────────────────────

#: Mainnet domain tag (same as crypto_policy constants — kept here for symmetry)
MAINNET_DOMAIN_TAG: Final[str] = "ARTCB/WALLET/MAINNET/V1"

#: TEST domain tag — changes the wallet address hash, preventing MAINNET collisions
TEST_DOMAIN_TAG: Final[str] = "ARTCB/WALLET/TEST/V1"

# ──────────────────────────────────────────────────────────────────────────────
# TEST network protocol identifiers
# ──────────────────────────────────────────────────────────────────────────────

TEST_NETWORK_ID: Final[str] = "artcb-testnet-1"
TEST_PROTOCOL_VERSION: Final[str] = "189-testnet-1"

# Declared test genesis identifier (not a live block hash — same convention as mainnet).
TEST_GENESIS_HASH: Final[str] = "genesis-artcb-testnet-1"

# Address prefix for TEST wallets (visual indicator + Bech32 HRP segregation)
TEST_ADDRESS_PREFIX: Final[str] = "artcbdev"

# Mainnet address prefix (from address.py — copied here for cross-check)
MAINNET_ADDRESS_PREFIX: Final[str] = "artcb"

# TEST asset unit name (isolated from ARTCB production economics)
TEST_ASSET_NAME: Final[str] = "tARTCB"

# ──────────────────────────────────────────────────────────────────────────────
# Cross-domain invariants (rapport 355 §19 + rapport 356 §14)
# ──────────────────────────────────────────────────────────────────────────────

#: Transfers from TEST → MAINNET are ALWAYS rejected (no bridge defined yet)
TEST_TO_MAINNET_ALLOWED: Final[bool] = False
MAINNET_TO_TEST_ALLOWED: Final[bool] = False


def is_test_address(address: str) -> bool:
    """Return True if the address belongs to the TEST domain."""
    return address.startswith(TEST_ADDRESS_PREFIX + "1")


def is_mainnet_address(address: str) -> bool:
    """Return True if the address belongs to the MAINNET domain."""
    return address.startswith(MAINNET_ADDRESS_PREFIX + "1") or address.startswith("artcb2")


def domain_of_address(address: str) -> str:
    """Return 'TEST', 'MAINNET', or 'UNKNOWN' based on address prefix."""
    if is_test_address(address):
        return "TEST"
    if is_mainnet_address(address):
        return "MAINNET"
    return "UNKNOWN"


def accept_test_peer_protocol(
    *,
    advertised_network_id: str | None,
    advertised_protocol_version: str | None,
    advertised_genesis_hash: str | None,
) -> tuple[bool, str]:
    """Same logic as crypto_policy.accept_peer_protocol() but for the test network.

    A TEST peer MUST match the TEST identifiers exactly.
    A MAINNET peer connecting to a TESTNET node is rejected (cross-domain).
    """
    nid = (advertised_network_id or "").strip()
    pv = (advertised_protocol_version or "").strip()
    gh = (advertised_genesis_hash or "").strip()
    if not nid or not pv or not gh:
        return False, "legacy_missing_protocol_fields"
    if nid != TEST_NETWORK_ID:
        return False, f"network_id_mismatch:{nid}"
    if pv != TEST_PROTOCOL_VERSION:
        return False, f"protocol_version_mismatch:{pv}"
    if gh != TEST_GENESIS_HASH:
        return False, f"genesis_hash_mismatch:{gh}"
    return True, "test_protocol_compatible"


def reject_cross_domain_transfer(
    sender_address: str,
    recipient_address: str,
) -> tuple[bool, str]:
    """Enforce domain segregation on transfers.

    Returns (rejected, reason). Callers MUST check rejected=True and abort.
    """
    sender_domain = domain_of_address(sender_address)
    recipient_domain = domain_of_address(recipient_address)
    if sender_domain == "TEST" and recipient_domain == "MAINNET":
        return True, "cross_domain_reject: TEST→MAINNET forbidden"
    if sender_domain == "MAINNET" and recipient_domain == "TEST":
        return True, "cross_domain_reject: MAINNET→TEST forbidden"
    return False, "same_domain_allowed"


def test_capabilities() -> dict[str, Any]:
    """Public test-domain capability block (analogous to crypto_policy.capabilities())."""
    return {
        "domain": "TEST",
        "network_id": TEST_NETWORK_ID,
        "protocol_version": TEST_PROTOCOL_VERSION,
        "genesis_hash": TEST_GENESIS_HASH,
        "address_prefix": TEST_ADDRESS_PREFIX,
        "domain_tag": TEST_DOMAIN_TAG,
        "asset_name": TEST_ASSET_NAME,
        "test_to_mainnet_allowed": TEST_TO_MAINNET_ALLOWED,
        "mainnet_to_test_allowed": MAINNET_TO_TEST_ALLOWED,
        "validation_engine": "SAME_AS_MAINNET",
        "attestation_type": "SYNTHETIC",
        "note": "Full validation active on synthetic proofs. No bypasses.",
    }
