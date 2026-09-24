"""Liaison cryptographique TPM EK → NodeID — R460.

Protocole ARTCB-NODE-TPM-BINDING-v1 :

    La chaîne de preuve complète vise :

        HUMAIN → WebAuthn → Wallet → Device → TPM EK/AK → NodeID → P2P → Blockchain

    Ce module implémente le chaînon MANQUANT (niveaux C+D identifiés R460) :

        TPM device_fingerprint  →  payload JSON signé  →  NodeTpmBinding
                                                              ↓
                                             verify_node_tpm_binding(peer_node_id)

    Niveaux de garantie (D-045 — jamais inventer une puce) :

        A  physical_tpm  → tpm_proven=True  (TPM EK cert hash présent, bare-metal)
        B  virtual_tpm   → tpm_proven=True  (vTPM / NitroTPM — EK cert hash présent)
        C  tee           → tpm_proven=False, tee_proven=True
        D  hsm           → tpm_proven=False, hsm_proven=True
        E  software      → tpm_proven=False (machine-id seulement)

    Signature :
        Ed25519 (D-032 — toujours actif)
        ML-DSA-65 (D-032 — si liboqs disponible)
        Hybride AND : les deux si possible (D-034)

    INVARIANTS :
        tpm_proven = True ssi hardware_assurance_level in {A, B} ET tpm_ek_cert_hash présent
        certified = False — absolu
        unique_human_proven = False — ce module ne prouve pas l'unicité humaine
        node_id ≠ wallet_address — le node a sa propre clé
        On n'invente jamais un TPM absent (D-045)

Référence : rapport R460 — 2026-09-25
"""

from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R460 — liaison TPM EK → NodeID

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("artcb.security.node_tpm_binding")

# ── Imports optionnels (fail-open) ───────────────────────────────────────────

try:
    from nacl import signing as _nacl_signing  # type: ignore[import]
    _HAS_NACL = True
except ImportError:  # pragma: no cover
    _HAS_NACL = False

try:
    from src.artcb.crypto.pqc import sign_message as _pqc_sign, verify_message as _pqc_verify
    _HAS_LIBOQS = True
except Exception:  # pragma: no cover
    _HAS_LIBOQS = False


# ── Constantes ───────────────────────────────────────────────────────────────

BINDING_PROTOCOL = "ARTCB-NODE-TPM-BINDING-v1"
TPM_PROVEN_LEVELS = {"A", "B"}           # niveaux qui autorisent tpm_proven=True
DEBUG_MODE = True                         # R460 — mode DEBUG toujours actif


# ── Payload (partie signée) ───────────────────────────────────────────────────

def _make_payload(
    *,
    node_id: str,
    device_fingerprint: str,
    hardware_assurance_level: str,
    hardware_kind: str,
    tpm_ek_cert_hash: str | None,
    tpm_kind: str,
    platform_system: str,
    env_type: str,
    nonce: str,
    timestamp: str,
) -> dict[str, Any]:
    """Construit le payload JSON canonique qui sera signé.

    Tous les champs sont inclus dans la signature — toute altération invalide la vérif.
    """
    return {
        "protocol": BINDING_PROTOCOL,
        "node_id": node_id,
        "device_fingerprint": device_fingerprint,
        "hardware_assurance_level": hardware_assurance_level,
        "hardware_kind": hardware_kind,
        # tpm_ek_cert_hash est le hash SHA-256 du certificat EK TPM (jamais la clé brute)
        "tpm_ek_cert_hash": tpm_ek_cert_hash,
        "tpm_kind": tpm_kind,
        "platform_system": platform_system,
        "env_type": env_type,
        "nonce": nonce,
        "timestamp": timestamp,
    }


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Sérialisation déterministe pour la signature (clés triées, compact)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class NodeTpmBinding:
    """Liaison signée entre un NodeID et son empreinte matérielle (TPM ou software).

    Invariants :
        certified = False (absolu)
        unique_human_proven = False (ce module ne touche pas à l'unicité humaine)
        tpm_proven = True ssi hardware_assurance_level in {A, B} ET tpm_ek_cert_hash présent
    """

    node_id: str
    device_fingerprint: str
    hardware_assurance_level: str            # A | B | C | D | E
    hardware_kind: str                       # physical_tpm | virtual_tpm | tee | hsm | software
    tpm_ek_cert_hash: str | None             # SHA-256 du cert EK — None si absent
    tpm_kind: str                            # physical | virtual | absent
    tpm_proven: bool                         # True ssi level A/B + EK cert hash présent
    platform_system: str
    env_type: str
    nonce: str                               # 32 octets hex — anti-rejeu
    timestamp: str                           # ISO 8601 UTC
    ed25519_public_key_hex: str              # clé publique Ed25519 du node
    ed25519_signature_hex: str              # signature Ed25519 du payload
    mldsa65_public_key_hex: str | None       # clé publique ML-DSA-65 (si liboqs)
    mldsa65_signature_hex: str | None        # signature ML-DSA-65 (si liboqs)
    hybrid_and: bool                         # True si les deux signatures présentes
    certified: bool = False                  # invariant absolu
    unique_human_proven: bool = False        # invariant absolu
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": BINDING_PROTOCOL,
            "node_id": self.node_id,
            "device_fingerprint": self.device_fingerprint,
            "hardware_assurance_level": self.hardware_assurance_level,
            "hardware_kind": self.hardware_kind,
            "tpm_ek_cert_hash": self.tpm_ek_cert_hash,
            "tpm_kind": self.tpm_kind,
            "tpm_proven": self.tpm_proven,
            "platform_system": self.platform_system,
            "env_type": self.env_type,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "ed25519_public_key_hex": self.ed25519_public_key_hex,
            "ed25519_signature_hex": self.ed25519_signature_hex,
            "mldsa65_public_key_hex": self.mldsa65_public_key_hex,
            "mldsa65_signature_hex": self.mldsa65_signature_hex,
            "hybrid_and": self.hybrid_and,
            "certified": self.certified,
            "unique_human_proven": self.unique_human_proven,
            "note": self.note,
        }


@dataclass
class BindingVerificationResult:
    """Résultat de la vérification d'un NodeTpmBinding.

    valid = True ssi :
        - ed25519_ok = True
        - node_id_match = True
        - hybrid_and respecté si requis

    certified = False — absolu.
    tpm_proven reflète le champ du binding vérifié (pas recalculé).
    """

    valid: bool
    node_id_match: bool
    ed25519_ok: bool
    mldsa65_ok: bool | None          # None si ML-DSA absent
    hybrid_and_satisfied: bool
    tpm_proven: bool
    hardware_assurance_level: str
    failure_reason: str | None = None
    certified: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "node_id_match": self.node_id_match,
            "ed25519_ok": self.ed25519_ok,
            "mldsa65_ok": self.mldsa65_ok,
            "hybrid_and_satisfied": self.hybrid_and_satisfied,
            "tpm_proven": self.tpm_proven,
            "hardware_assurance_level": self.hardware_assurance_level,
            "failure_reason": self.failure_reason,
            "certified": self.certified,
            "note": self.note,
        }


# ── Création du binding ───────────────────────────────────────────────────────

def create_node_tpm_binding(
    *,
    node_id: str,
    ed25519_signing_key_bytes: bytes,
    device_fingerprint: str,
    hardware_assurance_level: str,
    hardware_kind: str,
    tpm_ek_cert_hash: str | None,
    tpm_kind: str = "absent",
    platform_system: str = "",
    env_type: str = "unknown",
    mldsa65_secret_key_bytes: bytes | None = None,
    mldsa65_public_key_bytes: bytes | None = None,
) -> NodeTpmBinding:
    """Crée un binding NodeID ↔ empreinte matérielle signé par la clé Ed25519 du node.

    Ne fabrique jamais un TPM absent.
    tpm_proven = True ssi hardware_assurance_level in {A, B} ET tpm_ek_cert_hash présent.

    Args:
        node_id: identifiant unique du nœud P2P.
        ed25519_signing_key_bytes: 32 octets — clé privée Ed25519 du nœud.
        device_fingerprint: empreinte SHA-256 calculée par hardware_identity.py.
        hardware_assurance_level: A–E (jamais inventé).
        hardware_kind: "physical_tpm" | "virtual_tpm" | "tee" | "hsm" | "software".
        tpm_ek_cert_hash: hash SHA-256 du cert EK TPM, ou None.
        tpm_kind: "physical" | "virtual" | "absent".
        mldsa65_secret_key_bytes: clé secrète ML-DSA-65 (si liboqs disponible).
        mldsa65_public_key_bytes: clé publique ML-DSA-65 correspondante.

    Returns:
        NodeTpmBinding signé.

    Raises:
        ValueError: node_id ou device_fingerprint vide.
        RuntimeError: nacl absent (Ed25519 requis).
    """
    if not node_id:
        raise ValueError("node_id ne peut pas être vide")
    if not device_fingerprint:
        raise ValueError("device_fingerprint ne peut pas être vide")
    if not _HAS_NACL:
        raise RuntimeError(  # pragma: no cover
            "PyNaCl est requis pour créer un binding (pip install pynacl)"
        )

    # ── Invariant : tpm_proven uniquement si EK cert ET niveau A/B ────────────
    tpm_proven = (
        hardware_assurance_level in TPM_PROVEN_LEVELS
        and bool(tpm_ek_cert_hash)
    )

    # ── Nonce anti-rejeu ──────────────────────────────────────────────────────
    nonce = secrets.token_hex(32)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Payload canonique ─────────────────────────────────────────────────────
    payload = _make_payload(
        node_id=node_id,
        device_fingerprint=device_fingerprint,
        hardware_assurance_level=hardware_assurance_level,
        hardware_kind=hardware_kind,
        tpm_ek_cert_hash=tpm_ek_cert_hash,
        tpm_kind=tpm_kind,
        platform_system=platform_system,
        env_type=env_type,
        nonce=nonce,
        timestamp=timestamp,
    )
    message = _canonical_bytes(payload)

    # ── Signature Ed25519 ─────────────────────────────────────────────────────
    sk = _nacl_signing.SigningKey(ed25519_signing_key_bytes)
    ed_sig_bytes = sk.sign(message).signature
    ed_pub_hex = sk.verify_key.encode().hex()
    ed_sig_hex = ed_sig_bytes.hex()

    # ── Signature ML-DSA-65 (optionnelle) ────────────────────────────────────
    mldsa_pub_hex: str | None = None
    mldsa_sig_hex: str | None = None
    if _HAS_LIBOQS and mldsa65_secret_key_bytes and mldsa65_public_key_bytes:
        try:
            raw_sig = _pqc_sign(message, mldsa65_secret_key_bytes)
            mldsa_pub_hex = mldsa65_public_key_bytes.hex()
            mldsa_sig_hex = raw_sig.hex()
        except Exception as exc:
            logger.warning("[R460] ML-DSA-65 signature failed (non-bloquant): %s", exc)

    hybrid_and = bool(ed_sig_hex and mldsa_sig_hex)

    note_parts = [
        f"protocol={BINDING_PROTOCOL}",
        f"hardware_assurance_level={hardware_assurance_level}",
        f"tpm_proven={tpm_proven}",
        f"hybrid_and={hybrid_and}",
        "certified=False — invariant absolu",
        "unique_human_proven=False — ce module ne prouve pas l'unicité humaine",
    ]
    if not tpm_proven:
        note_parts.append(
            "tpm_proven=False : EK cert absent ou niveau C/D/E — "
            "fingerprint basé sur machine-id/instance-id"
        )

    if DEBUG_MODE:
        logger.debug(
            "[R460][DEBUG] create_node_tpm_binding node_id=%s level=%s tpm_proven=%s hybrid=%s",
            node_id,
            hardware_assurance_level,
            tpm_proven,
            hybrid_and,
        )

    return NodeTpmBinding(
        node_id=node_id,
        device_fingerprint=device_fingerprint,
        hardware_assurance_level=hardware_assurance_level,
        hardware_kind=hardware_kind,
        tpm_ek_cert_hash=tpm_ek_cert_hash,
        tpm_kind=tpm_kind,
        tpm_proven=tpm_proven,
        platform_system=platform_system,
        env_type=env_type,
        nonce=nonce,
        timestamp=timestamp,
        ed25519_public_key_hex=ed_pub_hex,
        ed25519_signature_hex=ed_sig_hex,
        mldsa65_public_key_hex=mldsa_pub_hex,
        mldsa65_signature_hex=mldsa_sig_hex,
        hybrid_and=hybrid_and,
        certified=False,
        unique_human_proven=False,
        note=". ".join(note_parts),
    )


# ── Vérification ──────────────────────────────────────────────────────────────

def verify_node_tpm_binding(
    binding: NodeTpmBinding,
    *,
    expected_node_id: str,
    require_hybrid_and: bool = False,
    require_tpm_proven: bool = False,
) -> BindingVerificationResult:
    """Vérifie un NodeTpmBinding.

    Fail-closed : tout échec de vérification → valid=False.

    Args:
        binding: le binding à vérifier.
        expected_node_id: node_id attendu — doit correspondre exactement.
        require_hybrid_and: si True, rejette les bindings sans ML-DSA-65.
        require_tpm_proven: si True, rejette les bindings avec tpm_proven=False.

    Returns:
        BindingVerificationResult avec valid=True ssi toutes les vérifications passent.
    """
    if not _HAS_NACL:
        return BindingVerificationResult(  # pragma: no cover
            valid=False,
            node_id_match=False,
            ed25519_ok=False,
            mldsa65_ok=None,
            hybrid_and_satisfied=False,
            tpm_proven=False,
            hardware_assurance_level="E",
            failure_reason="nacl_absent",
            certified=False,
        )

    # ── 1. NodeID match ───────────────────────────────────────────────────────
    node_id_match = (binding.node_id == expected_node_id)
    if not node_id_match:
        if DEBUG_MODE:
            logger.debug(
                "[R460][DEBUG] verify: node_id mismatch got=%s expected=%s",
                binding.node_id,
                expected_node_id,
            )
        return BindingVerificationResult(
            valid=False,
            node_id_match=False,
            ed25519_ok=False,
            mldsa65_ok=None,
            hybrid_and_satisfied=False,
            tpm_proven=binding.tpm_proven,
            hardware_assurance_level=binding.hardware_assurance_level,
            failure_reason="node_id_mismatch",
            certified=False,
        )

    # ── 2. Reconstruire le payload canonique ──────────────────────────────────
    payload = _make_payload(
        node_id=binding.node_id,
        device_fingerprint=binding.device_fingerprint,
        hardware_assurance_level=binding.hardware_assurance_level,
        hardware_kind=binding.hardware_kind,
        tpm_ek_cert_hash=binding.tpm_ek_cert_hash,
        tpm_kind=binding.tpm_kind,
        platform_system=binding.platform_system,
        env_type=binding.env_type,
        nonce=binding.nonce,
        timestamp=binding.timestamp,
    )
    message = _canonical_bytes(payload)

    # ── 3. Vérification Ed25519 ───────────────────────────────────────────────
    ed25519_ok = False
    try:
        vk = _nacl_signing.VerifyKey(bytes.fromhex(binding.ed25519_public_key_hex))
        vk.verify(message, bytes.fromhex(binding.ed25519_signature_hex))
        ed25519_ok = True
    except Exception as exc:
        if DEBUG_MODE:
            logger.debug("[R460][DEBUG] verify: ed25519 failed: %s", exc)

    # ── 4. Vérification ML-DSA-65 (si présente) ───────────────────────────────
    mldsa65_ok: bool | None = None
    if binding.mldsa65_signature_hex and binding.mldsa65_public_key_hex:
        if _HAS_LIBOQS:
            try:
                mldsa65_ok = _pqc_verify(
                    message,
                    bytes.fromhex(binding.mldsa65_signature_hex),
                    bytes.fromhex(binding.mldsa65_public_key_hex),
                )
            except Exception as exc:
                if DEBUG_MODE:
                    logger.debug("[R460][DEBUG] verify: mldsa65 failed: %s", exc)
                mldsa65_ok = False
        else:
            mldsa65_ok = None  # liboqs absent — on ne peut pas vérifier

    # ── 5. Contraintes hybride / TPM ──────────────────────────────────────────
    hybrid_and_satisfied = binding.hybrid_and and (mldsa65_ok is True)
    if require_hybrid_and and not hybrid_and_satisfied:
        return BindingVerificationResult(
            valid=False,
            node_id_match=True,
            ed25519_ok=ed25519_ok,
            mldsa65_ok=mldsa65_ok,
            hybrid_and_satisfied=hybrid_and_satisfied,
            tpm_proven=binding.tpm_proven,
            hardware_assurance_level=binding.hardware_assurance_level,
            failure_reason="hybrid_and_required_not_satisfied",
            certified=False,
        )

    if require_tpm_proven and not binding.tpm_proven:
        return BindingVerificationResult(
            valid=False,
            node_id_match=True,
            ed25519_ok=ed25519_ok,
            mldsa65_ok=mldsa65_ok,
            hybrid_and_satisfied=hybrid_and_satisfied,
            tpm_proven=False,
            hardware_assurance_level=binding.hardware_assurance_level,
            failure_reason="tpm_proven_required_not_satisfied",
            certified=False,
        )

    valid = ed25519_ok and node_id_match
    failure = None if valid else "ed25519_verification_failed"

    if DEBUG_MODE:
        logger.debug(
            "[R460][DEBUG] verify: valid=%s ed25519_ok=%s mldsa65_ok=%s tpm_proven=%s",
            valid,
            ed25519_ok,
            mldsa65_ok,
            binding.tpm_proven,
        )

    return BindingVerificationResult(
        valid=valid,
        node_id_match=node_id_match,
        ed25519_ok=ed25519_ok,
        mldsa65_ok=mldsa65_ok,
        hybrid_and_satisfied=hybrid_and_satisfied,
        tpm_proven=binding.tpm_proven,
        hardware_assurance_level=binding.hardware_assurance_level,
        failure_reason=failure,
        certified=False,
        note=(
            f"protocol={BINDING_PROTOCOL} node_id={binding.node_id} "
            f"level={binding.hardware_assurance_level} tpm_proven={binding.tpm_proven} "
            f"certified=False"
        ),
    )
