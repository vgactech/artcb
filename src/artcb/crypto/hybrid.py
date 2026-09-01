"""Hybrid classical + post-quantum signatures.

D-034 A — hybride AND : les DEUX jambes (Ed25519 ET ML-DSA-65) doivent
passer. Une jambe seule (Ed25519 ou ML-DSA) est refusée par
``verify_hybrid_and``.

``verify_hybrid`` garde encore un repli Ed25519-only (fenêtre D-032 B).
Ce n'est PAS l'enforcement AND. ``high_value_hybrid_enforced`` reste
false tant que chain / groups / governance n'appellent pas
``verify_hybrid_and``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from nacl import signing

from src.artcb.crypto.pqc import PQC_SIG_ALGORITHM, sign_message, verify_message

logger = logging.getLogger("artcb.crypto.hybrid")

HYBRID_PREFIX = "hybrid:"
ED25519_PREFIX = "ed25519:"
MLDSA65_PREFIX = "mldsa65:"


@dataclass(frozen=True)
class HybridSignature:
    ed25519_hex: str
    mldsa_hex: str

    def serialize(self) -> str:
        return f"{HYBRID_PREFIX}{ED25519_PREFIX}{self.ed25519_hex}|mldsa65:{self.mldsa_hex}"

    @classmethod
    def parse(cls, value: str) -> HybridSignature | None:
        if not value.startswith(HYBRID_PREFIX):
            return None
        body = value[len(HYBRID_PREFIX) :]
        if "|mldsa65:" not in body:
            return None
        ed_part, mldsa_part = body.split("|mldsa65:", 1)
        if not ed_part.startswith(ED25519_PREFIX):
            return None
        return cls(ed25519_hex=ed_part[len(ED25519_PREFIX) :], mldsa_hex=mldsa_part)


def sign_hybrid(
    *,
    ed25519_key: signing.SigningKey,
    pqc_secret_key: bytes,
    message: bytes,
) -> str:
    ed_sig = ed25519_key.sign(message).signature.hex()
    pqc_sig = sign_message(message, pqc_secret_key).hex()
    return HybridSignature(ed25519_hex=ed_sig, mldsa_hex=pqc_sig).serialize()


def is_hybrid_envelope(signature_value: str) -> bool:
    return HybridSignature.parse(signature_value) is not None


def is_ed25519_only_envelope(signature_value: str) -> bool:
    """Ed25519 seule : préfixe ed25519: ou hex brut, sans enveloppe hybride."""
    if is_hybrid_envelope(signature_value) or signature_value.startswith(MLDSA65_PREFIX):
        return False
    return bool(signature_value)


def is_mldsa_only_envelope(signature_value: str) -> bool:
    """ML-DSA seule : préfixe mldsa65: sans enveloppe hybrid:ed25519:…|mldsa65:…"""
    if is_hybrid_envelope(signature_value):
        return False
    return signature_value.startswith(MLDSA65_PREFIX)


def verify_hybrid_and(
    *,
    message: bytes,
    signature_value: str,
    ed25519_public_key: bytes,
    pqc_public_key: bytes,
) -> bool:
    """D-034 A: les deux jambes doivent passer. Une jambe seule → refus.

    N'accepte pas Ed25519-only, ni ML-DSA-only, ni une enveloppe hybride
    dont une jambe est cassée ou absente.
    """
    parsed = HybridSignature.parse(signature_value)
    if parsed is None:
        logger.debug("hybrid AND reject: not a hybrid envelope")
        return False
    if not parsed.ed25519_hex or not parsed.mldsa_hex:
        logger.debug("hybrid AND reject: empty leg")
        return False
    try:
        verify_key = signing.VerifyKey(ed25519_public_key)
        verify_key.verify(message, bytes.fromhex(parsed.ed25519_hex))
    except Exception as exc:
        logger.debug("hybrid AND Ed25519 leg failed: %s", exc)
        return False
    try:
        mldsa_ok = verify_message(
            message, bytes.fromhex(parsed.mldsa_hex), pqc_public_key
        )
    except Exception as exc:
        logger.debug("hybrid AND ML-DSA leg failed: %s", exc)
        return False
    if not mldsa_ok:
        logger.debug("hybrid AND ML-DSA leg invalid")
        return False
    return True


def verify_hybrid(
    *,
    message: bytes,
    signature_value: str,
    ed25519_public_key: bytes,
    pqc_public_key: bytes,
    require_and: bool = False,
) -> bool:
    """Vérifie une signature.

    ``require_and=True`` → D-034 (``verify_hybrid_and``).
    Défaut ``False`` : enveloppe hybride = AND des deux jambes ; sinon
    repli Ed25519-only (encore utilisé par chain / groups / governance).
    """
    if require_and:
        return verify_hybrid_and(
            message=message,
            signature_value=signature_value,
            ed25519_public_key=ed25519_public_key,
            pqc_public_key=pqc_public_key,
        )
    parsed = HybridSignature.parse(signature_value)
    if parsed:
        return verify_hybrid_and(
            message=message,
            signature_value=signature_value,
            ed25519_public_key=ed25519_public_key,
            pqc_public_key=pqc_public_key,
        )

    # Legacy ed25519-only: "ed25519:hex" or raw hex with VerifyKey
    sig_hex = signature_value[len(ED25519_PREFIX):] if signature_value.startswith(ED25519_PREFIX) else signature_value
    try:
        verify_key = signing.VerifyKey(ed25519_public_key)
        verify_key.verify(message, bytes.fromhex(sig_hex))
        return True
    except Exception:
        return False


def algorithm_label() -> str:
    return f"Ed25519+{PQC_SIG_ALGORITHM}"
