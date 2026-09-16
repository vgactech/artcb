"""ARTCB address generation — Bech32-like format with Ed25519 pubkey hash.

Domain separation (rapports 354/355):
  generate_address_with_domain_tag() injects a domain string into the hash
  so that the same public key produces DIFFERENT addresses on MAINNET vs TEST.

  MAINNET: H("ARTCB/WALLET/MAINNET/V1" || pubkey)  → artcb1…
  TEST:    H("ARTCB/WALLET/TEST/V1"    || pubkey)  → artcbdev1…

  This prevents cross-domain replay: a TEST wallet_id cannot be used as a
  MAINNET wallet_id even if the private key is identical.
"""

from __future__ import annotations

import hashlib
import logging

from nacl import signing

logger = logging.getLogger("artcb.wallet.address")

# Domain separation tags (mirrors testdomain.policy constants — kept here to
# avoid circular imports; both must stay in sync).
DOMAIN_TAG_MAINNET: str = "ARTCB/WALLET/MAINNET/V1"
DOMAIN_TAG_TEST: str = "ARTCB/WALLET/TEST/V1"

# Bech32 charset (lowercase only)
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values: list[int]) -> int:
    """Bech32 checksum polymod."""
    GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    """Expand HRP for checksum."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_create_checksum(hrp: str, data: list[int]) -> list[int]:
    """Create Bech32 checksum."""
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _bech32_encode(hrp: str, data: list[int]) -> str:
    """Encode Bech32 string."""
    combined = data + _bech32_create_checksum(hrp, data)
    return hrp + "1" + "".join([BECH32_CHARSET[d] for d in combined])


def _convertbits(data: bytes, frombits: int, tobits: int, pad: bool = True) -> list[int]:
    """Convert between bit groups."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        raise ValueError("Invalid padding")
    return ret


def generate_address(public_key_bytes: bytes, *, prefix: str = "artcb") -> str:
    """
    Generate ARTCB address from Ed25519 public key (no domain tag — legacy/mainnet path).

    Format: artcb1<bech32_encoded_hash>

    Args:
        public_key_bytes: 32-byte Ed25519 public key
        prefix: Address prefix (default: "artcb")

    Returns:
        Bech32-encoded address (e.g., "artcb1q...")
    """
    if len(public_key_bytes) != 32:
        raise ValueError(f"Public key must be 32 bytes, got {len(public_key_bytes)}")

    # Hash pubkey (SHA-256 then RIPEMD-160 like Bitcoin)
    sha256_hash = hashlib.sha256(public_key_bytes).digest()
    ripemd160_hash = hashlib.new("ripemd160", sha256_hash).digest()

    # Convert to 5-bit groups for Bech32
    data = _convertbits(ripemd160_hash, 8, 5)

    # Encode with checksum
    address = _bech32_encode(prefix, data)

    logger.debug("Generated address=%s from pubkey_hash=%s", address, ripemd160_hash.hex()[:16])
    return address


def generate_address_with_domain_tag(
    public_key_bytes: bytes,
    *,
    domain_tag: str,
    prefix: str = "artcb",
) -> str:
    """Generate ARTCB address with cryptographic domain separation.

    The domain_tag is included in the hash input, so:
      H(MAINNET_TAG || pubkey) ≠ H(TEST_TAG || pubkey)

    Same public key → different wallet_id depending on the domain.
    This prevents cross-domain replay (rapport 354 §14, rapport 355 §4–§7).

    Args:
        public_key_bytes: 32-byte Ed25519 public key
        domain_tag: Domain separation string (DOMAIN_TAG_MAINNET or DOMAIN_TAG_TEST)
        prefix: Bech32 HRP prefix (e.g. "artcb" or "artcbdev")

    Returns:
        Bech32-encoded domain-separated address
    """
    if len(public_key_bytes) != 32:
        raise ValueError(f"Public key must be 32 bytes, got {len(public_key_bytes)}")
    if not domain_tag:
        raise ValueError("domain_tag must not be empty")

    # Domain separation: hash(domain_tag_bytes || pubkey_bytes)
    domain_bytes = domain_tag.encode("utf-8")
    sha256_hash = hashlib.sha256(domain_bytes + public_key_bytes).digest()
    ripemd160_hash = hashlib.new("ripemd160", sha256_hash).digest()

    data = _convertbits(ripemd160_hash, 8, 5)
    address = _bech32_encode(prefix, data)

    logger.debug(
        "Generated domain-separated address=%s domain=%s pubkey_hash=%s",
        address, domain_tag, ripemd160_hash.hex()[:16],
    )
    return address


def generate_test_address(public_key_bytes: bytes) -> str:
    """Convenience wrapper — generate TEST domain address (artcbdev1…).

    Uses DOMAIN_TAG_TEST + prefix "artcbdev".
    """
    return generate_address_with_domain_tag(
        public_key_bytes,
        domain_tag=DOMAIN_TAG_TEST,
        prefix="artcbdev",
    )


def generate_mainnet_address_domain_separated(public_key_bytes: bytes) -> str:
    """Convenience wrapper — generate MAINNET domain-separated address (artcb1…).

    Uses DOMAIN_TAG_MAINNET + prefix "artcb".
    NOTE: this produces a DIFFERENT hash than the legacy generate_address()
    which has no domain tag. Use this for new wallets post-testdomain roll-out.
    """
    return generate_address_with_domain_tag(
        public_key_bytes,
        domain_tag=DOMAIN_TAG_MAINNET,
        prefix="artcb",
    )


def verify_address(address: str, *, prefix: str = "artcb") -> bool:
    """
    Verify ARTCB address format and checksum.

    Args:
        address: Address to verify
        prefix: Expected prefix

    Returns:
        True if valid, False otherwise
    """
    if not address.startswith(prefix + "1"):
        return False

    try:
        hrp, data_part = address.split("1", 1)
        if hrp != prefix:
            return False

        # Decode data
        data = [BECH32_CHARSET.index(c) for c in data_part]

        # Verify checksum
        hrp_expand = _bech32_hrp_expand(hrp)
        if _bech32_polymod(hrp_expand + data) != 1:
            return False

        # Verify length (20 bytes RIPEMD-160 → ~32 chars + 6 checksum)
        return not len(data) < 6
    except (ValueError, IndexError):
        return False


def address_from_signing_key(signing_key: signing.SigningKey, *, prefix: str = "artcb") -> str:
    """Generate address from SigningKey."""
    pubkey_bytes = signing_key.verify_key.encode()
    return generate_address(pubkey_bytes, prefix=prefix)


def address_from_public_key_bytes(pubkey_bytes: bytes, *, prefix: str = "artcb") -> str:
    """Derive ARTCB address from raw Ed25519 public key bytes."""
    return generate_address(pubkey_bytes, prefix=prefix)


def address_from_public_key_hex(public_key_hex: str, *, prefix: str = "artcb") -> str:
    return address_from_public_key_bytes(bytes.fromhex(public_key_hex), prefix=prefix)


def hybrid_address_v2(ed25519_public_key: bytes, pqc_public_key: bytes) -> str:
    """
    Hybrid post-quantum address (artcb2) — hash of Ed25519 + ML-DSA public keys.

    Legacy/MAINNET path — no domain tag injected.
    Use hybrid_address_v2_domain_separated() for V-PQC-2 domain separation.
    """
    if len(ed25519_public_key) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    if not pqc_public_key:
        raise ValueError("PQC public key required for artcb2 address")
    combined = hashlib.sha256(ed25519_public_key + pqc_public_key).digest()
    ripemd160_hash = hashlib.new("ripemd160", combined).digest()
    data = _convertbits(ripemd160_hash, 8, 5)
    return _bech32_encode("artcb2", data)


def hybrid_address_v2_domain_separated(
    ed25519_public_key: bytes,
    pqc_public_key: bytes,
    *,
    domain_tag: str,
    prefix: str = "artcb2",
) -> str:
    """V-PQC-2 — Hybrid PQC address with cryptographic domain separation.

    Injects domain_tag into the hash input so that:
      H(MAINNET_TAG || ed25519_pk || pqc_pk) ≠ H(TEST_TAG || ed25519_pk || pqc_pk)

    Same key pair → different artcb2 address depending on the domain.
    This closes the cross-domain replay vector for hybrid (PQC) wallets
    (rapport 357 §5 backlog V-PQC-2).

    Args:
        ed25519_public_key: 32-byte Ed25519 public key
        pqc_public_key:     ML-DSA-65 public key bytes
        domain_tag:         DOMAIN_TAG_MAINNET or DOMAIN_TAG_TEST
        prefix:             Bech32 HRP — "artcb2" for MAINNET, "artcb2t" for TEST

    Returns:
        Bech32-encoded domain-separated hybrid address
    """
    if len(ed25519_public_key) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    if not pqc_public_key:
        raise ValueError("PQC public key required for hybrid address")
    if not domain_tag:
        raise ValueError("domain_tag must not be empty")

    # Domain separation: SHA256(domain_tag_bytes || ed25519_pk || pqc_pk)
    domain_bytes = domain_tag.encode("utf-8")
    combined = hashlib.sha256(domain_bytes + ed25519_public_key + pqc_public_key).digest()
    ripemd160_hash = hashlib.new("ripemd160", combined).digest()
    data = _convertbits(ripemd160_hash, 8, 5)
    address = _bech32_encode(prefix, data)

    logger.debug(
        "Generated domain-separated hybrid address=%s domain=%s",
        address, domain_tag,
    )
    return address


def generate_test_hybrid_address_v2(
    ed25519_public_key: bytes,
    pqc_public_key: bytes,
) -> str:
    """Convenience wrapper — TEST domain hybrid address (artcb2t…).

    Uses DOMAIN_TAG_TEST + prefix "artcb2t".
    """
    return hybrid_address_v2_domain_separated(
        ed25519_public_key,
        pqc_public_key,
        domain_tag=DOMAIN_TAG_TEST,
        prefix="artcb2t",
    )


def generate_mainnet_hybrid_address_v2(
    ed25519_public_key: bytes,
    pqc_public_key: bytes,
) -> str:
    """Convenience wrapper — MAINNET domain-separated hybrid address (artcb2…).

    NOTE: produces a DIFFERENT hash than legacy hybrid_address_v2() (no domain tag).
    Use for new wallets post-V-PQC-2 roll-out.
    """
    return hybrid_address_v2_domain_separated(
        ed25519_public_key,
        pqc_public_key,
        domain_tag=DOMAIN_TAG_MAINNET,
        prefix="artcb2",
    )


def verify_address_v2(address: str) -> bool:
    """Verify artcb2 / artcb2t hybrid address format and checksum."""
    return verify_address(address, prefix="artcb2") or verify_address(address, prefix="artcb2t")

