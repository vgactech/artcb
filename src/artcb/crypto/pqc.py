"""Post-quantum cryptography — ML-DSA-65 (NIST) via liboqs."""

from __future__ import annotations

import logging
import os
from typing import Final

from src.artcb.crypto.liboqs_runtime import native_liboqs_available

logger = logging.getLogger("artcb.crypto.pqc")

PQC_SIG_ALGORITHM: Final[str] = "ML-DSA-65"
ENV_PQC_ENABLED = "ARTCB_PQC_ENABLED"

# ML-DSA-65 fixed key sizes (liboqs FIPS204)
PQC_SECRET_KEY_LEN: Final[int] = 4032
PQC_PUBLIC_KEY_LEN: Final[int] = 1952

# Cache de disponibilité liboqs — testé une seule fois au démarrage (comme kem.py)
_PQC_AVAILABLE: bool | None = None


class PQCError(Exception):
    """Post-quantum crypto operation failed."""


def pqc_enabled() -> bool:
    return os.getenv(ENV_PQC_ENABLED, "true").lower() in ("1", "true", "yes", "on")


def pqc_available() -> bool:
    """Vérifie si liboqs-python est disponible pour ML-DSA-65 — résultat mis en cache.

    Retourne True si oqs est importable ET que le .so natif est chargé.
    Utilisé par /health pour exposer le statut PQC en temps réel.
    """
    global _PQC_AVAILABLE
    if _PQC_AVAILABLE is None:
        if not native_liboqs_available():
            _PQC_AVAILABLE = False
            logger.warning(
                "liboqs native library absent — fallback Ed25519 actif. "
                "PQC installation is deferred so API startup is not blocked."
            )
            return _PQC_AVAILABLE
        try:
            import oqs as _oqs_test  # noqa: F401
            _oqs_test.get_enabled_sig_mechanisms()
            _PQC_AVAILABLE = True
        except (ImportError, RuntimeError, OSError, AttributeError, SystemExit, BaseException):
            _PQC_AVAILABLE = False
            logger.warning(
                "liboqs backend unusable (Python binding may be installed). "
                "Typical Replit case: liboqs-python 0.16 + native liboqs 0.13 "
                "→ ML-DSA-65 missing → fallback Ed25519. "
                "Compile native liboqs 0.16.0 into $OQS_INSTALL_PATH (see "
                "scripts/install_native_liboqs_replit.sh). Not 'package absent'."
            )
    return _PQC_AVAILABLE


def _import_oqs():
    if not native_liboqs_available():
        raise PQCError(
            "liboqs native library not found — fallback Ed25519 actif. "
            "Compiler liboqs (cmake) pour ML-DSA-65 complet."
        )
    try:
        import oqs  # liboqs-python
        # Vérifie que le .so natif est chargé — API stable liboqs-python
        oqs.get_enabled_sig_mechanisms()
    except ImportError as exc:
        raise PQCError(
            "liboqs-python not installed — run: pip install liboqs-python\n"
            "  Linux  : sudo apt install cmake gcc libssl-dev && pip install liboqs-python\n"
            "  macOS  : brew install cmake openssl && pip install liboqs-python\n"
            "  Replit : cmake est dans replit.nix — repit_start.sh installe liboqs en arrière-plan"
        ) from exc
    except (AttributeError, RuntimeError, OSError, SystemExit, BaseException) as exc:
        raise PQCError(
            "liboqs native library not found — fallback Ed25519 actif. "
            "Compiler liboqs (cmake) pour ML-DSA-65 complet."
        ) from exc
    return oqs


def generate_keypair() -> tuple[bytes, bytes]:
    """Return (secret_key, public_key) bytes for ML-DSA-65."""
    oqs = _import_oqs()
    with oqs.Signature(PQC_SIG_ALGORITHM) as signer:
        public_key = signer.generate_keypair()
        secret_key = signer.export_secret_key()
    logger.debug("Generated %s keypair (pub=%d bytes)", PQC_SIG_ALGORITHM, len(public_key))
    return secret_key, public_key


def pack_keypair(secret_key: bytes, public_key: bytes) -> bytes:
    if len(secret_key) != PQC_SECRET_KEY_LEN or len(public_key) != PQC_PUBLIC_KEY_LEN:
        raise PQCError(f"Invalid ML-DSA-65 key sizes: sk={len(secret_key)} pk={len(public_key)}")
    return secret_key + public_key


def unpack_keypair(blob: bytes) -> tuple[bytes, bytes]:
    if len(blob) < PQC_SECRET_KEY_LEN + PQC_PUBLIC_KEY_LEN:
        raise PQCError(f"Invalid packed keypair length: {len(blob)}")
    secret = blob[:PQC_SECRET_KEY_LEN]
    public = blob[PQC_SECRET_KEY_LEN : PQC_SECRET_KEY_LEN + PQC_PUBLIC_KEY_LEN]
    return secret, public


def sign_message(message: bytes, secret_key: bytes) -> bytes:
    oqs = _import_oqs()
    with oqs.Signature(PQC_SIG_ALGORITHM, secret_key=secret_key) as signer:
        return signer.sign(message)


def verify_message(message: bytes, signature: bytes, public_key: bytes) -> bool:
    oqs = _import_oqs()
    try:
        with oqs.Signature(PQC_SIG_ALGORITHM) as verifier:
            return verifier.verify(message, signature, public_key)
    except Exception as exc:
        logger.debug("PQC verify failed: %s", exc)
        return False
