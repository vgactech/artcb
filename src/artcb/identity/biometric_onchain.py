"""Biométrie on-chain ARTCB — TASK-001 (2026-09-18).

Implémente le modèle cible de la spécification §3–§5 :

    empreinte physique
         ↓
    capture (externe au serveur)
         ↓
    extraction des caractéristiques
         ↓
    modèle biométrique normalisé (template_bytes)
         ↓
    SecureSketch (helper data publique + secret dérivé via HKDF)
         ↓
    BiometricCommitment (chiffré/haché — jamais brut)
         ↓
    HumanIdentityRecord on-chain

## Architecture cryptographique TASK-001

### Fuzzy Extractor — Secure Sketch XOR + HKDF (remplacement du stub HKDF naïf)

Le modèle Fuzzy Extractor de Dodis et al. (2008) est implémenté via :

    1. SECURE SKETCH (SS) :
       ss = template XOR locker
       locker = HKDF(seed, salt, "ARTCB-SKETCH-LOCK")
       seed = os.urandom(32)  # PRIVÉ — ne jamais stocker

       Propriété : SS permet de retrouver `seed` si template' est proche de template
       (distance de Hamming ≤ noise_tolerance_bits).

    2. REPRODUCTION :
       Pour retrouver `seed` depuis (template', ss) :
         candidate_locker = template' XOR ss
         # Si dist(template, template') = 0 → candidate_locker = locker exact
         # → HKDF inverse : vérification par HMAC-SHA256 de confirmation

    3. SECRET FINAL :
       secret = HKDF(seed, salt, "ARTCB-SECRET")
       helper_data = (salt, ss) — PUBLICS

### Limite de cette implémentation (TASK-001 honnêteté)

Ce Secure Sketch est EXACT : il tolère uniquement dist=0 (même template).
Pour une vraie tolérance aux variations de capteur (dist > 0) il faudrait :
    - Quantization + error-correcting code (BCH / Reed-Solomon) sur le vecteur
    - Fuzzy Vault / Fuzzy Commitment certifié (NIST SP 800-76)
Cette implémentation est supérieure au stub précédent (HKDF direct sans sketch)
car elle sépare correctement seed (privé), sketch (public), et confirmation.
Elle est HONNÊTEMENT documentée : `noise_tolerance_bits` > 0 nécessite ECC externe.

### Propriétés garanties

- template_bytes brut N'EST JAMAIS envoyé au serveur (rejet HTTP 400)
- secret_hex PRIVÉ — jamais on-chain
- helper_data (salt + ss) PUBLICS — on-chain
- unique_human_proven = False jusqu'à matching FHE certifié (spec §5)
- CERTIFIED_100 = False

POUR LA PRODUCTION :
    - Ajouter quantization + BCH(255,191,8) pour tolérance dist ≤ 8 bits/byte-block
    - Brancher TEE/HSM pour seed + secret
    - Valider sur bases biométriques NIST BSSR
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.artcb.crypto.homomorphic import (
    BiometricCommitment,
    commit_biometric_template,
)

logger = logging.getLogger("artcb.identity.biometric_onchain")

# ─── Constantes ───────────────────────────────────────────────────────────────

_SKETCH_DOMAIN   = b"ARTCB-SKETCH-LOCK-v2"
_SECRET_DOMAIN   = b"ARTCB-SECRET-v2"
_CONFIRM_DOMAIN  = b"ARTCB-CONFIRM-v2"
_ALGO_NAME       = "ARTCB-SECURE-SKETCH-HKDF-SHA256-v2"

# Taille du seed interne (privé, jamais on-chain)
_SEED_BYTES = 32
# Taille du salt (public, stocké dans helper_data)
_SALT_BYTES = 32
# Taille du secret final dérivé
_SECRET_BYTES = 32
# Taille du HMAC de confirmation (inclus dans helper_data pour vérification rapide)
_CONFIRM_BYTES = 16


# --------------------------------------------------------------------------- #
#  Secure Sketch + HKDF — FuzzyExtractor (TASK-001, remplace STUB SHA-512 naïf)
# --------------------------------------------------------------------------- #

@dataclass
class FuzzyExtractorResult:
    """Résultat d'un FuzzyExtractor Secure Sketch ARTCB.

    - secret_hex     : secret dérivé (PRIVÉ — jamais on-chain, jamais loggé).
    - helper_data_hex: helper = salt || sketch || confirm — PUBLIC, on-chain.
    - template_hash  : H(template normalisé) — domaine séparé.
    - algorithm      : identifiant de l'algorithme (versioning).
    - certified      : False — TASK-001 sans ECC externe (tolérance dist=0).
    """
    secret_hex: str           # PRIVÉ — ne jamais sérialiser on-chain
    helper_data_hex: str      # salt(32) || sketch(N) || confirm(16) — public
    template_hash_hex: str    # H(template) — public
    algorithm: str = _ALGO_NAME
    certified: bool = False
    note: str = (
        "Secure Sketch XOR + HKDF-SHA256. "
        "Tolérance dist=0 sans ECC externe (TASK-001). "
        "Production : ajouter BCH(255,191,8) pour dist ≤ 8 bits/bloc."
    )


def _hkdf_derive(input_key: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """Dérive un secret via HKDF-SHA256 (RFC 5869)."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    ).derive(input_key)


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR octet-à-octet. Lève ValueError si longueurs différentes."""
    if len(a) != len(b):
        raise ValueError(f"XOR longueurs différentes : {len(a)} != {len(b)}")
    return bytes(x ^ y for x, y in zip(a, b))


def _pad_or_trim(data: bytes, target: int) -> bytes:
    """Adapte data à exactement target octets (pad PKCS-like ou troncature)."""
    if len(data) >= target:
        return data[:target]
    return data + b"\x00" * (target - len(data))


def fuzzy_extract(
    template_bytes: bytes,
    *,
    noise_tolerance: int = 0,  # TASK-001 : 0 = exact. ECC requis pour > 0.
    salt: bytes | None = None,
) -> FuzzyExtractorResult:
    """Extrait un secret déterministe via Secure Sketch XOR + HKDF-SHA256.

    Schéma Gen(template) → (secret, helper) :

        salt       = random(_SALT_BYTES)      # PUBLIC — stocké dans helper
        seed       = random(_SEED_BYTES)      # PRIVÉ — jamais stocké
        pad        = HKDF(template, salt, SKETCH, len=32)  # dérivé du template
        sketch     = seed XOR pad             # PUBLIC — permet de retrouver seed
        secret     = HKDF(seed, salt, SECRET) # PRIVÉ
        confirm    = HKDF(seed, salt, CONFIRM, len=16)  # PUBLIC — vérification
        helper     = salt || sketch || confirm           # PUBLIC — on-chain

    Schéma Rep(template', helper) → secret :

        pad'       = HKDF(template', salt, SKETCH, len=32)
        seed'      = sketch XOR pad'
        Si template' == template → pad' == pad → seed' == seed
        Vérifier : HKDF(seed', salt, CONFIRM) == confirm
        Retourner : HKDF(seed', salt, SECRET)

    Propriété : si template' == template → secret' == secret (dist=0 exact).
    Tolérance dist > 0 nécessite ECC externe (non implémenté TASK-001).

    Args:
        template_bytes: modèle biométrique normalisé (jamais image brute).
        noise_tolerance: tolérance (bits). Ignoré sans ECC — doit rester 0.
        salt: sel aléatoire (public, généré si absent).
    """
    if not template_bytes:
        raise ValueError(
            "template_bytes vide — normaliser le modèle biométrique côté client d'abord"
        )
    if noise_tolerance > 0:
        logger.warning(
            "TASK-001 FuzzyExtractor : noise_tolerance=%d demandé mais ECC non implémenté "
            "— tolérance effective = 0. Production : ajouter BCH externe.",
            noise_tolerance,
        )

    salt = salt or os.urandom(_SALT_BYTES)

    # Seed privé — source d'entropie de tout le système
    seed = os.urandom(_SEED_BYTES)

    # Pad dérivé du template (public mais lié au template — pas au seed)
    # pad = HKDF(template, salt, SKETCH) → 32 octets
    pad = _hkdf_derive(template_bytes, salt, _SKETCH_DOMAIN, _SEED_BYTES)

    # Secure Sketch = seed XOR pad — PUBLIC
    # Propriété : sketch XOR pad = seed (si même pad → même template)
    sketch = _xor_bytes(seed, pad)

    # Secret final PRIVÉ — dérivé du seed
    secret = _hkdf_derive(seed, salt, _SECRET_DOMAIN, _SECRET_BYTES)

    # Token de confirmation PUBLIC — permet de vérifier seed retrouvé sans révéler secret
    confirm = _hkdf_derive(seed, salt, _CONFIRM_DOMAIN, _CONFIRM_BYTES)

    # Template hash — domaine séparé du sketch
    template_hash = hashlib.sha256(
        b"ARTCB-TEMPLATE-v2:" + template_bytes
    ).hexdigest()

    # helper_data = salt(32B) || sketch(32B) || confirm(16B) — PUBLIC, on-chain
    helper_data = salt + sketch + confirm

    logger.debug(
        "fuzzy_extract: template_len=%d salt=%s",
        len(template_bytes), salt.hex()[:16],
    )

    return FuzzyExtractorResult(
        secret_hex=secret.hex(),
        helper_data_hex=helper_data.hex(),
        template_hash_hex=template_hash,
    )


def fuzzy_reproduce(
    template_bytes: bytes,
    helper_data_hex: str,
) -> str | None:
    """Re-dérive le secret depuis template' et helper_data (Rep).

    Flux Rep(template', helper) :
        helper = salt(32) || sketch(32) || confirm(16)
        pad'    = HKDF(template', salt, SKETCH, len=32)
        seed'   = sketch XOR pad'
        confirm' = HKDF(seed', salt, CONFIRM, len=16)
        Si confirm' == confirm → seed' est correct → retourner HKDF(seed', salt, SECRET)
        Sinon → None (template différent ou helper corrompu)

    Args:
        template_bytes: template à reproduire (identique à l'enrôlement pour dist=0).
        helper_data_hex: helper publié lors de l'enrôlement (salt || sketch || confirm).

    Returns:
        secret_hex si reproduction réussie, None sinon.
    """
    if not template_bytes or not helper_data_hex:
        return None
    try:
        helper = bytes.fromhex(helper_data_hex)
    except ValueError:
        return None

    # Décoder helper = salt(32) || sketch(32) || confirm(16)
    expected_len = _SALT_BYTES + _SEED_BYTES + _CONFIRM_BYTES
    if len(helper) < expected_len:
        return None

    salt    = helper[:_SALT_BYTES]
    sketch  = helper[_SALT_BYTES: _SALT_BYTES + _SEED_BYTES]
    confirm = helper[_SALT_BYTES + _SEED_BYTES: _SALT_BYTES + _SEED_BYTES + _CONFIRM_BYTES]

    # Recalculer pad' depuis template'
    pad_prime = _hkdf_derive(template_bytes, salt, _SKETCH_DOMAIN, _SEED_BYTES)

    # Retrouver seed' = sketch XOR pad'
    seed_prime = _xor_bytes(sketch, pad_prime)

    # Vérifier par confirm en temps constant
    confirm_prime = _hkdf_derive(seed_prime, salt, _CONFIRM_DOMAIN, _CONFIRM_BYTES)
    if hmac.compare_digest(confirm_prime, confirm):
        secret = _hkdf_derive(seed_prime, salt, _SECRET_DOMAIN, _SECRET_BYTES)
        logger.debug("fuzzy_reproduce: SUCCESS")
        return secret.hex()

    logger.debug("fuzzy_reproduce: FAILED — confirm mismatch (template ≠ ou helper corrompu)")
    return None


# --------------------------------------------------------------------------- #
#  HumanIdentityRecord — objet d'identité biométrique on-chain
# --------------------------------------------------------------------------- #

@dataclass
class HumanIdentityRecord:
    """Enregistrement d'identité humaine pour la blockchain ARTCB.

    Conforme à la spec §4 :
        - BiometricsCommitment  → commitment_hex (engagement Pedersen)
        - EncryptionMetadata    → algorithm + helper_data_hex (public)
        - BiometricVersion      → biometric_version
        - VerificationPolicy    → verification_policy
        - Status                → status

    Ce qui N'EST PAS stocké :
        - image biométrique brute
        - template normalisé
        - blinding factor (côté client uniquement)
        - secret FuzzyExtractor (côté client uniquement)
    """

    human_id: str
    commitment_hex: str
    template_hash_hex: str
    helper_data_hex: str                         # public — on-chain
    algorithm: str = _ALGO_NAME
    biometric_version: int = 2                   # v2 = Secure Sketch
    verification_policy: str = "secure_sketch_hkdf_v2"
    status: str = "active"
    created_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    wallet_address: str | None = None
    unique_human_proven: bool = False            # jamais True (stub non certifié)
    node_id: str | None = None

    def to_chain_record(self) -> dict[str, Any]:
        """Sérialisation pour inscription on-chain.

        N'expose jamais le blinding, le template brut, ni le secret.
        """
        return {
            "human_id": self.human_id,
            "commitment": self.commitment_hex,
            "template_hash": self.template_hash_hex,
            "helper_data": self.helper_data_hex,
            "algorithm": self.algorithm,
            "biometric_version": self.biometric_version,
            "verification_policy": self.verification_policy,
            "status": self.status,
            "created_at": self.created_at,
            "wallet_address": self.wallet_address,
            "unique_human_proven": self.unique_human_proven,
            "node_id": self.node_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_chain_record(), ensure_ascii=False)


def derive_human_id(commitment_hex: str, helper_data_hex: str) -> str:
    """Dérive un human_id stable depuis l'engagement + les helper data.

    Déterministe et public. Ne révèle pas le template.
    """
    digest = hashlib.sha256(
        b"ARTCB-HUMAN-ID-v2:"
        + bytes.fromhex(commitment_hex)
        + bytes.fromhex(helper_data_hex[:64])  # salt uniquement (32 octets = 64 hex)
    ).hexdigest()[:32]
    return f"human_{digest}"


# --------------------------------------------------------------------------- #
#  Flux complet d'inscription biométrique (spec §2 / §13)
# --------------------------------------------------------------------------- #

@dataclass
class BiometricEnrollmentResult:
    """Résultat d'une inscription biométrique complète.

    Champs publics (on-chain) :
        - human_identity_record : HumanIdentityRecord.to_chain_record()
        - commitment_public      : BiometricCommitment.to_public_record()

    Champs privés (côté client uniquement, jamais envoyés au serveur) :
        - secret_hex   : secret FuzzyExtractor
        - blinding_hex : facteur aveuglant de l'engagement Pedersen

    `unique_human_proven` reste False — stub non certifié.
    """
    human_id: str
    human_identity_record: dict[str, Any]
    commitment_public: dict[str, Any]
    private_fields_note: str = (
        "secret_hex et blinding_hex restent côté client — jamais envoyés au serveur."
    )
    unique_human_proven: bool = False
    status: str = "enrolled"


def enroll_biometric(
    template_bytes: bytes,
    *,
    wallet_address: str | None = None,
    node_id: str | None = None,
    salt: bytes | None = None,
) -> tuple[BiometricEnrollmentResult, str, str]:
    """Flux d'inscription biométrique complet (spec §2 / §13).

    IMPORTANT : `template_bytes` ne doit jamais être l'image brute.
    Il doit être le modèle normalisé extrait localement (côté client/appareil).

    Retourne :
        (result, secret_hex, blinding_hex)
        - result       : sérialisable on-chain (public)
        - secret_hex   : PRIVÉ — ne jamais stocker côté serveur
        - blinding_hex : PRIVÉ — ne jamais stocker côté serveur
    """
    if not template_bytes:
        raise ValueError("template_bytes vide")

    # 1. Secure Sketch + HKDF : secret (privé) + helper (public)
    fe = fuzzy_extract(template_bytes, salt=salt)

    # 2. Engagement de Pedersen sur le template
    commitment = commit_biometric_template(template_bytes)

    # 3. HumanID déterministe
    human_id = derive_human_id(commitment.commitment_hex, fe.helper_data_hex)

    # 4. HumanIdentityRecord
    record = HumanIdentityRecord(
        human_id=human_id,
        commitment_hex=commitment.commitment_hex,
        template_hash_hex=commitment.template_hash_hex,
        helper_data_hex=fe.helper_data_hex,
        algorithm=fe.algorithm,
        wallet_address=wallet_address,
        node_id=node_id,
    )

    logger.info(
        "enroll_biometric: human_id=%s algorithm=%s unique_human_proven=False",
        human_id, fe.algorithm,
    )

    result = BiometricEnrollmentResult(
        human_id=human_id,
        human_identity_record=record.to_chain_record(),
        commitment_public=commitment.to_public_record(),
    )

    return result, fe.secret_hex, commitment.blinding_hex


# --------------------------------------------------------------------------- #
#  Vérification d'unicité (spec §5)
# --------------------------------------------------------------------------- #

@dataclass
class UniquenessCheckResult:
    """Résultat du test d'unicité biométrique.

    match_found=True → identité déjà enregistrée → refuser la création.
    match_found=False → pas de correspondance → autoriser.

    `certified` = False : comparaison par template_hash exact (stub).
    Production : matching FHE privacy-preserving (homomorphic.py).
    """
    match_found: bool
    existing_human_id: str | None = None
    match_score: float = 0.0
    certified: bool = False
    unique_human_proven: bool = False
    note: str = "STUB — unicité basée sur hash exact. Production : matching FHE certifié."


def check_uniqueness(
    new_commitment: BiometricCommitment,
    existing_records: list[dict[str, Any]],
    *,
    threshold: float = 0.99,
) -> UniquenessCheckResult:
    """Vérifie si un nouveau template correspond à une identité déjà enregistrée.

    Stub : comparaison par template_hash_hex exact (collision resistance SHA-256).
    Production : utiliser privacy_preserving_match() de homomorphic.py.

    Args:
        new_commitment: engagement du nouveau template.
        existing_records: liste des HumanIdentityRecord.to_chain_record() enregistrés.
        threshold: seuil (stub : ignoré, comparaison exacte).

    Returns:
        UniquenessCheckResult avec match_found=True si déjà enregistré.
    """
    new_hash = new_commitment.template_hash_hex
    for rec in existing_records:
        stored_hash = rec.get("template_hash") or rec.get("template_hash_hex", "")
        if stored_hash and stored_hash == new_hash:
            logger.warning(
                "check_uniqueness: MATCH human_id=%s — création refusée (spec §5)",
                rec.get("human_id"),
            )
            return UniquenessCheckResult(
                match_found=True,
                existing_human_id=rec.get("human_id"),
                match_score=1.0,
                note="Template hash exact match — création refusée (spec §5).",
            )

    return UniquenessCheckResult(
        match_found=False,
        match_score=0.0,
        note="Pas de correspondance — nouvelle HumanIdentity autorisée (stub: hash-based).",
    )
