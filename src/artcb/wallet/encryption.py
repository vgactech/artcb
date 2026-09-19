"""Wallet private key encryption at rest — AES-256-GCM."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import os
import secrets
from pathlib import Path
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

logger = logging.getLogger("artcb.wallet.encryption")

MAGIC: Final[bytes] = b"ARTCBENC1"
NONCE_LEN: Final[int] = 12
SCRYPT_N: Final[int] = 2**14
SCRYPT_R: Final[int] = 8
SCRYPT_P: Final[int] = 1
SCRYPT_LEN: Final[int] = 32

ENV_PASSPHRASE = "ARTCB_WALLET_PASSPHRASE"


class WalletEncryptionError(Exception):
    """Raised when wallet encryption/decryption fails."""


def get_wallet_passphrase() -> str:
    """
    Load passphrase from environment.
    Required for creating/loading encrypted wallets.
    """
    phrase = os.getenv(ENV_PASSPHRASE, "").strip()
    if not phrase:
        raise WalletEncryptionError(
            f"{ENV_PASSPHRASE} is not set — cannot encrypt or decrypt wallet private keys. "
            "Set a strong passphrase in .env (never commit it)."
        )
    if len(phrase) < 12:
        raise WalletEncryptionError(
            f"{ENV_PASSPHRASE} must be at least 12 characters for AES-256-GCM key derivation."
        )
    return phrase


def is_encrypted_key_blob(data: bytes) -> bool:
    return data.startswith(MAGIC) and len(data) > len(MAGIC) + 16 + NONCE_LEN + 16


def is_plain_ed25519_seed(data: bytes) -> bool:
    """Legacy unencrypted 32-byte Ed25519 seed."""
    return len(data) == 32 and not data.startswith(MAGIC)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=SCRYPT_LEN, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_secret_blob(data: bytes, passphrase: str | None = None) -> bytes:
    """Encrypt arbitrary secret bytes → ARTCBENC1 | salt(16) | nonce(12) | ciphertext+tag."""
    if not data:
        raise WalletEncryptionError("Cannot encrypt empty secret blob")
    phrase = passphrase or get_wallet_passphrase()
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(NONCE_LEN)
    key = _derive_key(phrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, data, MAGIC)
    blob = MAGIC + salt + nonce + ciphertext
    logger.debug("Encrypted secret blob (%d bytes → %d bytes)", len(data), len(blob))
    return blob


def decrypt_secret_blob(blob: bytes, passphrase: str | None = None) -> bytes:
    """Decrypt ARTCBENC1 blob."""
    if not is_encrypted_key_blob(blob):
        raise WalletEncryptionError("Invalid encrypted secret blob format")
    phrase = passphrase or get_wallet_passphrase()
    salt = blob[len(MAGIC) : len(MAGIC) + 16]
    nonce = blob[len(MAGIC) + 16 : len(MAGIC) + 16 + NONCE_LEN]
    ciphertext = blob[len(MAGIC) + 16 + NONCE_LEN :]
    key = _derive_key(phrase, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, MAGIC)
    except Exception as exc:
        raise WalletEncryptionError("Decryption failed — wrong passphrase or corrupted file") from exc


def encrypt_private_key(seed: bytes, passphrase: str | None = None) -> bytes:
    """Encrypt 32-byte Ed25519 seed → ARTCBENC1 | salt(16) | nonce(12) | ciphertext+tag."""
    if len(seed) != 32:
        raise WalletEncryptionError(f"Expected 32-byte seed, got {len(seed)}")
    return encrypt_secret_blob(seed, passphrase)


def decrypt_private_key(blob: bytes, passphrase: str | None = None) -> bytes:
    """Decrypt wallet blob or pass through legacy 32-byte seed."""
    if is_plain_ed25519_seed(blob):
        logger.warning(
            "Loading LEGACY unencrypted wallet key (32 bytes). "
            "Re-save wallet to encrypt with AES-256-GCM."
        )
        return blob
    seed = decrypt_secret_blob(blob, passphrase)
    if len(seed) != 32:
        raise WalletEncryptionError("Decrypted seed has invalid length")
    return seed


def encrypt_legacy_key_file(key_path: Path, passphrase: str | None = None) -> bool:
    """Migrate plain .key file to encrypted format. Returns True if migrated."""
    raw = key_path.read_bytes()
    if is_encrypted_key_blob(raw):
        return False
    if not is_plain_ed25519_seed(raw):
        raise WalletEncryptionError(f"Cannot migrate unknown key format: {key_path}")
    encrypted = encrypt_private_key(raw, passphrase)
    key_path.write_bytes(encrypted)
    key_path.chmod(0o600)
    logger.info("Migrated wallet key to AES-256-GCM: %s", key_path)
    return True
