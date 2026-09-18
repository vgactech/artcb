"""Biométrie on-chain ARTCB — TASK-001 / R374 (2026-09-18).

Implémente le modèle cible de la spécification §3–§5 :

    empreinte physique
         ↓
    capture (externe au serveur)
         ↓
    extraction des caractéristiques
         ↓
    modèle biométrique normalisé (template_bytes)
         ↓
    BCH(255,191,8) : correction d'erreurs sur le template avant le Sketch
         ↓
    SecureSketch (helper data publique + secret dérivé via HKDF)
         ↓
    BiometricCommitment (chiffré/haché — jamais brut)
         ↓
    HumanIdentityRecord on-chain

## Architecture cryptographique TASK-001 / R374

### Couche BCH — tolérance dist ≤ 8 bits par bloc de 23 octets (R374)

BCH(255, t=8, m=8, prim_poly=0x11d) — paramètres standard ARTCB :
  - n = 255 bits de code total
  - t = 8 erreurs de bits corrigibles par bloc
  - ecc_bytes = 8 octets d'ECC par bloc
  - Taille du bloc de données : 23 octets (184 bits < 255)

ENRÔLEMENT (_bch_encode_template) :
  template_padded → découpé en blocs de BCH_DATA_BYTES octets
  → pour chaque bloc : ecc_i = BCH.encode(bloc_i)
  → helper_data stocke la concaténation des ecc (public)
  → template_corrigé = template_padded (inchangé à l'enrôlement)

REPRODUCTION (_bch_decode_template) :
  template'_padded → découpé en blocs
  → pour chaque bloc_i : BCH.decode(bloc_i, ecc_i) → BCH.correct(bloc_i, ecc_i)
  → si nerr < 0 → bloc incorrigible → retourner None (trop de bruit)
  → template corrigé reconstruit → passé au Secure Sketch

Propriété : si dist_bits(template, template') ≤ 8 × nb_blocs → reproduction réussie.
Pour une empreinte digitale de 32 octets (= 1 bloc + padding) : tolérance ≤ 8 bits.
Pour 64 octets (3 blocs) : tolérance ≤ 8 bits par bloc = 24 bits globaux.

### Fuzzy Extractor — Secure Sketch XOR + HKDF (ARTCB-SECURE-SKETCH-HKDF-BCH-v3)

Schéma Gen(template) → (secret, helper) :

    salt       = random(_SALT_BYTES)      # PUBLIC — stocké dans helper
    seed       = random(_SEED_BYTES)      # PRIVÉ — jamais stocké
    tmpl_norm  = _bch_encode_template(template)  # template normalisé BCH
    pad        = HKDF(tmpl_norm, salt, SKETCH, len=32)
    sketch     = seed XOR pad             # PUBLIC
    secret     = HKDF(seed, salt, SECRET) # PRIVÉ
    confirm    = HKDF(seed, salt, CONFIRM, len=16)  # PUBLIC
    bch_ecc    = ECC blocs (public)       # PUBLIC — stocké dans helper
    helper     = salt || sketch || confirm || bch_ecc  # PUBLIC — on-chain

Schéma Rep(template', helper) → secret :

    tmpl_corr  = _bch_decode_template(template', bch_ecc)  # correction BCH
    si tmpl_corr is None → échec (trop de bruit)
    pad'       = HKDF(tmpl_corr, salt, SKETCH, len=32)
    seed'      = sketch XOR pad'
    Vérifier : HKDF(seed', salt, CONFIRM) == confirm
    Retourner : HKDF(seed', salt, SECRET)

### Propriétés garanties

- template_bytes brut N'EST JAMAIS envoyé au serveur (rejet HTTP 400)
- secret_hex PRIVÉ — jamais on-chain
- helper_data (salt + sketch + confirm + bch_ecc) PUBLICS — on-chain
- unique_human_proven = False jusqu'à matching FHE certifié (spec §5)
- CERTIFIED_100 = False
- BCH.decode() < 0 → None (fail-closed — pas de secret incorrect)

PRODUCTION :
    - Brancher TEE/HSM pour seed + secret
    - Valider FAR/FRR sur bases NIST BSSR
    - Quantification du vecteur biométrique côté client recommandée
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

import bchlib
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.artcb.crypto.homomorphic import (
    BiometricCommitment,
    commit_biometric_template,
)

logger = logging.getLogger("artcb.identity.biometric_onchain")

# ─── Constantes Secure Sketch ─────────────────────────────────────────────────

_SKETCH_DOMAIN   = b"ARTCB-SKETCH-LOCK-v3"   # v3 avec BCH
_SECRET_DOMAIN   = b"ARTCB-SECRET-v3"
_CONFIRM_DOMAIN  = b"ARTCB-CONFIRM-v3"
_ALGO_NAME       = "ARTCB-SECURE-SKETCH-HKDF-BCH-v3"

# Taille du seed interne (privé, jamais on-chain)
_SEED_BYTES = 32
# Taille du salt (public, stocké dans helper_data)
_SALT_BYTES = 32
# Taille du secret final dérivé
_SECRET_BYTES = 32
# Taille du HMAC de confirmation (public, stocké dans helper_data)
_CONFIRM_BYTES = 16

# ─── Constantes BCH ───────────────────────────────────────────────────────────

# BCH(255, t=8, m=8) — standard ARTCB R374
# prim_poly=0x11d = x^8 + x^4 + x^3 + x^2 + 1 (polynôme primitif standard GF(2^8))
_BCH_T          = 8          # erreurs de bits corrigibles par bloc
_BCH_PRIM_POLY  = 0x11d      # polynôme primitif GF(2^8)
_BCH_DATA_BYTES = 23         # octets de données par bloc (184 bits < n=255)
# ecc_bytes déduit de l'instance BCH (= 8 pour t=8, m=8)

def _make_bch() -> bchlib.BCH:
    """Crée une instance BCH(255, t=8) — instanciation légère, réutilisable."""
    return bchlib.BCH(_BCH_T, prim_poly=_BCH_PRIM_POLY)


# ─── Couche BCH — encode/decode template ──────────────────────────────────────

def _bch_encode_template(template_bytes: bytes) -> tuple[bytes, bytes]:
    """Encode le template en blocs BCH.

    Découpe template_bytes en blocs de _BCH_DATA_BYTES octets (padding nul si nécessaire),
    génère l'ECC BCH pour chaque bloc.

    Returns:
        (template_padded, bch_ecc_blob)
        - template_padded : template normalisé à un multiple de _BCH_DATA_BYTES (PUBLIC, helper)
        - bch_ecc_blob    : concaténation des ecc de chaque bloc (PUBLIC, helper)
    """
    bch = _make_bch()
    ecc_bytes = bch.ecc_bytes  # = 8 pour BCH(t=8, m=8)

    # Pad template à multiple de BCH_DATA_BYTES
    n_blocks = max(1, (len(template_bytes) + _BCH_DATA_BYTES - 1) // _BCH_DATA_BYTES)
    padded_len = n_blocks * _BCH_DATA_BYTES
    template_padded = template_bytes.ljust(padded_len, b"\x00")

    ecc_parts: list[bytes] = []
    for i in range(n_blocks):
        block = template_padded[i * _BCH_DATA_BYTES: (i + 1) * _BCH_DATA_BYTES]
        ecc = bch.encode(block)
        ecc_parts.append(ecc)

    bch_ecc_blob = b"".join(ecc_parts)
    # Préfixe : 1 octet = nombre de blocs (max 255) + 1 octet = ecc_bytes par bloc
    header = bytes([n_blocks, ecc_bytes])
    return template_padded, header + bch_ecc_blob


def _bch_decode_template(
    template_bytes: bytes,
    bch_ecc_blob: bytes,
) -> bytes | None:
    """Corrige template_bytes avec les ECC BCH stockés.

    Returns:
        template corrigé (bytes) si tous les blocs sont corrigibles,
        None si au moins un bloc est incorrigible (trop d'erreurs ou blob corrompu).
    """
    if len(bch_ecc_blob) < 2:
        return None
    n_blocks   = bch_ecc_blob[0]
    ecc_size   = bch_ecc_blob[1]
    ecc_data   = bch_ecc_blob[2:]

    expected_ecc_len = n_blocks * ecc_size
    if len(ecc_data) < expected_ecc_len:
        return None

    bch = _make_bch()
    if bch.ecc_bytes != ecc_size:
        # Incompatibilité paramètres — fail-closed
        return None

    # Pad template' au même nombre de blocs que lors de l'enrôlement
    padded_len = n_blocks * _BCH_DATA_BYTES
    template_padded = template_bytes.ljust(padded_len, b"\x00")[:padded_len]

    corrected_parts: list[bytes] = []
    for i in range(n_blocks):
        block = bytearray(template_padded[i * _BCH_DATA_BYTES: (i + 1) * _BCH_DATA_BYTES])
        ecc   = bytearray(ecc_data[i * ecc_size: (i + 1) * ecc_size])

        nerr = bch.decode(block, ecc)
        if nerr < 0:
            # Bloc incorrigible (trop d'erreurs) — fail-closed
            logger.debug(
                "_bch_decode_template: bloc %d incorrigible (nerr=%d)", i, nerr
            )
            return None
        if nerr > 0:
            bch.correct(block, ecc)
            logger.debug(
                "_bch_decode_template: bloc %d — %d erreurs corrigées", i, nerr
            )
        corrected_parts.append(bytes(block))

    return b"".join(corrected_parts)


# --------------------------------------------------------------------------- #
#  Secure Sketch + HKDF — FuzzyExtractor (TASK-001, remplace STUB SHA-512 naïf)
# --------------------------------------------------------------------------- #

@dataclass
class FuzzyExtractorResult:
    """Résultat d'un FuzzyExtractor Secure Sketch + BCH ARTCB (R374).

    - secret_hex          : secret dérivé (PRIVÉ — jamais on-chain, jamais loggé).
    - helper_data_hex     : helper = salt || sketch || confirm || bch_ecc — PUBLIC, on-chain.
    - template_hash_hex   : H(template padded BCH) — domaine séparé.
    - algorithm           : identifiant de l'algorithme (versioning).
    - certified           : False — FHE uniqueness non implémenté (TASK-001).
    - noise_tolerance_bits: tolérance effective en bits (8 × nb_blocs).
    """
    secret_hex: str           # PRIVÉ — ne jamais sérialiser on-chain
    helper_data_hex: str      # salt(32) || sketch(32) || confirm(16) || bch_ecc — public
    template_hash_hex: str    # H(template padded BCH) — public
    algorithm: str = _ALGO_NAME
    certified: bool = False
    noise_tolerance_bits: int = 0   # rempli par fuzzy_extract()
    note: str = (
        "Secure Sketch XOR + HKDF-SHA256 + BCH(255,191,8). "
        "Tolérance : 8 erreurs de bits par bloc de 23 octets (R374). "
        "unique_human_proven=False — FHE matching non implémenté (TASK-001)."
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
    noise_tolerance: int = 8,  # R374 : 8 bits par bloc (BCH t=8) — effectif
    salt: bytes | None = None,
) -> FuzzyExtractorResult:
    """Extrait un secret déterministe via BCH + Secure Sketch XOR + HKDF-SHA256 (R374).

    Schéma Gen(template) → (secret, helper) :

        salt          = random(_SALT_BYTES)                   # PUBLIC
        seed          = random(_SEED_BYTES)                   # PRIVÉ
        tmpl_padded, bch_ecc = _bch_encode_template(template) # PUBLIC (ecc)
        pad           = HKDF(tmpl_padded, salt, SKETCH, 32)
        sketch        = seed XOR pad                          # PUBLIC
        secret        = HKDF(seed, salt, SECRET)              # PRIVÉ
        confirm       = HKDF(seed, salt, CONFIRM, 16)         # PUBLIC
        helper        = salt || sketch || confirm || bch_ecc  # PUBLIC, on-chain

    Schéma Rep(template', helper) → secret :

        bch_ecc       = helper[80:]  (après salt+sketch+confirm)
        tmpl_corr     = _bch_decode_template(template', bch_ecc)
        si tmpl_corr is None → return None (trop d'erreurs, fail-closed)
        pad'          = HKDF(tmpl_corr, salt, SKETCH, 32)
        seed'         = sketch XOR pad'
        confirm'      = HKDF(seed', salt, CONFIRM, 16)
        si confirm' != confirm → return None
        return HKDF(seed', salt, SECRET)

    Tolérance effective : 8 bits d'erreurs par bloc de 23 octets.

    Args:
        template_bytes: modèle biométrique normalisé (jamais image brute).
        noise_tolerance: ignoré — paramétré par BCH_T=8. Conservé pour compatibilité.
        salt: sel aléatoire (public, généré si absent).
    """
    if not template_bytes:
        raise ValueError(
            "template_bytes vide — normaliser le modèle biométrique côté client d'abord"
        )

    salt = salt or os.urandom(_SALT_BYTES)

    # Seed privé — source d'entropie de tout le système
    seed = os.urandom(_SEED_BYTES)

    # 1. BCH encode : normalize template + générer ECC
    template_padded, bch_ecc = _bch_encode_template(template_bytes)

    # 2. Pad dérivé du template paddé (lié au template normalisé BCH)
    pad = _hkdf_derive(template_padded, salt, _SKETCH_DOMAIN, _SEED_BYTES)

    # 3. Secure Sketch = seed XOR pad — PUBLIC
    sketch = _xor_bytes(seed, pad)

    # 4. Secret final PRIVÉ
    secret = _hkdf_derive(seed, salt, _SECRET_DOMAIN, _SECRET_BYTES)

    # 5. Confirmation PUBLIQUE
    confirm = _hkdf_derive(seed, salt, _CONFIRM_DOMAIN, _CONFIRM_BYTES)

    # 6. Template hash — sur le template paddé (stable)
    template_hash = hashlib.sha256(
        b"ARTCB-TEMPLATE-v3:" + template_padded
    ).hexdigest()

    # helper_data = salt(32B) || sketch(32B) || confirm(16B) || bch_ecc(var) — PUBLIC
    helper_data = salt + sketch + confirm + bch_ecc

    # Nombre de blocs BCH = taille sans header / ecc_bytes
    bch = _make_bch()
    n_blocks = max(1, (len(template_bytes) + _BCH_DATA_BYTES - 1) // _BCH_DATA_BYTES)
    tolerance = _BCH_T * n_blocks  # bits corrigibles totaux

    logger.debug(
        "fuzzy_extract: template_len=%d n_blocks=%d tolerance=%d bits salt=%s",
        len(template_bytes), n_blocks, tolerance, salt.hex()[:16],
    )

    return FuzzyExtractorResult(
        secret_hex=secret.hex(),
        helper_data_hex=helper_data.hex(),
        template_hash_hex=template_hash,
        noise_tolerance_bits=tolerance,
    )


def fuzzy_reproduce(
    template_bytes: bytes,
    helper_data_hex: str,
) -> str | None:
    """Re-dérive le secret depuis template' et helper_data (Rep) — R374 avec BCH.

    Flux Rep(template', helper) :
        helper    = salt(32) || sketch(32) || confirm(16) || bch_ecc(var)
        bch_ecc   = helper[80:]   (80 = 32+32+16)
        tmpl_corr = _bch_decode_template(template', bch_ecc)
        si tmpl_corr is None → None (trop d'erreurs bits — fail-closed)
        pad'      = HKDF(tmpl_corr, salt, SKETCH, len=32)
        seed'     = sketch XOR pad'
        confirm'  = HKDF(seed', salt, CONFIRM, len=16)
        Si confirm' == confirm → retourner HKDF(seed', salt, SECRET)
        Sinon → None (helper corrompu ou dist > tolérance BCH)

    Tolérance effective : 8 bits d'erreurs par bloc BCH de 23 octets.

    Args:
        template_bytes: template à reproduire (peut différer de l'enrôlement de ≤ 8 bits/bloc).
        helper_data_hex: helper publié lors de l'enrôlement.

    Returns:
        secret_hex si reproduction réussie, None sinon (fail-closed).
    """
    if not template_bytes or not helper_data_hex:
        return None
    try:
        helper = bytes.fromhex(helper_data_hex)
    except ValueError:
        return None

    # Décoder helper = salt(32) || sketch(32) || confirm(16) || bch_ecc(>=2)
    _FIXED = _SALT_BYTES + _SEED_BYTES + _CONFIRM_BYTES  # 80 octets fixes
    if len(helper) < _FIXED + 2:  # +2 pour le header BCH minimum
        return None

    salt        = helper[:_SALT_BYTES]
    sketch      = helper[_SALT_BYTES: _SALT_BYTES + _SEED_BYTES]
    confirm     = helper[_SALT_BYTES + _SEED_BYTES: _FIXED]
    bch_ecc     = helper[_FIXED:]

    # 1. Corriger template' via BCH
    template_corr = _bch_decode_template(template_bytes, bch_ecc)
    if template_corr is None:
        logger.debug("fuzzy_reproduce: FAILED — BCH decode échoué (template trop bruité)")
        return None

    # 2. Recalculer pad' depuis template corrigé
    pad_prime = _hkdf_derive(template_corr, salt, _SKETCH_DOMAIN, _SEED_BYTES)

    # 3. Retrouver seed' = sketch XOR pad'
    seed_prime = _xor_bytes(sketch, pad_prime)

    # 4. Vérifier confirm en temps constant
    confirm_prime = _hkdf_derive(seed_prime, salt, _CONFIRM_DOMAIN, _CONFIRM_BYTES)
    if hmac.compare_digest(confirm_prime, confirm):
        secret = _hkdf_derive(seed_prime, salt, _SECRET_DOMAIN, _SECRET_BYTES)
        logger.debug("fuzzy_reproduce: SUCCESS")
        return secret.hex()

    logger.debug("fuzzy_reproduce: FAILED — confirm mismatch (dist > tolérance BCH ou helper corrompu)")
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
    verification_policy: str = "secure_sketch_hkdf_bch_v3"
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
            "bch_tolerance_bits_per_block": _BCH_T,
            "bch_data_bytes_per_block": _BCH_DATA_BYTES,
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
