"""Biométrie on-chain ARTCB — P0-C (2026-09-16).

Implémente le modèle cible de la spécification §3–§5 :

    empreinte physique
         ↓
    capture (externe au serveur)
         ↓
    extraction des caractéristiques
         ↓
    modèle biométrique normalisé
         ↓
    FuzzyExtractor (helper data publique + secret dérivé)
         ↓
    BiometricCommitment (chiffré/haché — jamais brut)
         ↓
    HumanIdentityRecord on-chain

ARCHITECTURE DE CONFIDENTIALITÉ :
    - L'image brute n'est JAMAIS envoyée au serveur (rejet HTTP 400).
    - Le template normalisé n'est JAMAIS stocké en clair.
    - La blockchain conserve uniquement :
        * helper_data (public — nécessaire à la re-dérivation côté client)
        * BiometricCommitment.commitment_hex (engagement cryptographique)
        * BiometricCommitment.template_hash_hex (empreinte du template)
    - Le secret dérivé (FuzzyExtractor.secret) est PRIVÉ — jamais on-chain.

HONNÊTETÉ (CERTIFIED_100=false) :
    - Ce module est un stub fonctionnel.
    - La vérification d'unicité globale (anti-double-inscription) N'EST PAS
      prouvée en conditions réelles.
    - FAR/FRR/PAD non mesurés sur vrais capteurs.
    - `unique_human_proven` reste False jusqu'à validation certifiée.

POUR LA PRODUCTION :
    - Remplacer FuzzyExtractorStub par une implémentation certifiée (ex: fuzzy-vault).
    - Brancher un TEE ou HSM pour la génération du secret.
    - Valider sur des bases biométriques standardisées (NIST BSSR).
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

from src.artcb.crypto.homomorphic import (
    BiometricCommitment,
    commit_biometric_template,
)

logger = logging.getLogger("artcb.identity.biometric_onchain")


# --------------------------------------------------------------------------- #
#  FuzzyExtractor — stub (P0-C)
# --------------------------------------------------------------------------- #

@dataclass
class FuzzyExtractorResult:
    """Résultat d'un FuzzyExtractor.

    - secret    : secret dérivé (PRIVÉ — jamais on-chain).
    - helper    : helper data (public — sur blockchain pour re-dérivation).
    - template_hash : H(template normalisé) — domaine séparé.
    """
    secret_hex: str          # PRIVÉ — ne jamais sérialiser on-chain
    helper_data_hex: str     # public — inscriptible sur blockchain
    template_hash_hex: str   # H(template) — public
    algorithm: str = "ARTCB-FUZZY-STUB-SHA512-v1"
    certified: bool = False
    note: str = "STUB — production: fuzzy-vault / secure-sketch certifié"


def fuzzy_extract(
    template_bytes: bytes,
    *,
    noise_tolerance: int = 8,  # bits de tolérance (stub : non utilisé)
    salt: bytes | None = None,
) -> FuzzyExtractorResult:
    """Extrait un secret déterministe et des helper data depuis un template.

    Stub basé sur HKDF-SHA512 :
        secret = HKDF(template, salt, "ARTCB-SECRET")
        helper = HKDF(template, salt, "ARTCB-HELPER") XOR some_public_noise

    Pour la production : remplacer par un Fuzzy Vault ou un Secure Sketch.

    Args:
        template_bytes: modèle biométrique normalisé (jamais l'image brute).
        noise_tolerance: tolérance aux variations de capture (stub: ignoré).
        salt: sel aléatoire (généré si absent, doit être stocké avec helper).

    Returns:
        FuzzyExtractorResult avec secret (privé) et helper (public).
    """
    if not template_bytes:
        raise ValueError("template_bytes vide — capturer et normaliser le modèle biométrique d'abord")
    salt = salt or os.urandom(32)

    # Secret : HKDF stub — dérivé du template + salt
    secret = hashlib.sha512(
        b"ARTCB-SECRET:" + salt + b":" + template_bytes
    ).digest()[:32]

    # Helper data : données publiques permettant la re-dérivation côté client
    # Dans un vrai FuzzyExtractor : helper = template XOR error_correcting_code(secret)
    # Ici : helper = H(salt || "HELPER") — stub non ambigu
    helper = hashlib.sha512(
        b"ARTCB-HELPER:" + salt + b":" + template_bytes
    ).digest()[:32]

    template_hash = hashlib.sha256(
        b"ARTCB-TEMPLATE:" + template_bytes
    ).hexdigest()

    return FuzzyExtractorResult(
        secret_hex=secret.hex(),
        helper_data_hex=(salt + helper).hex(),  # salt encodé dans helper pour re-dérivation
        template_hash_hex=template_hash,
    )


def fuzzy_reproduce(
    template_bytes: bytes,
    helper_data_hex: str,
) -> str | None:
    """Re-dérive le secret depuis un nouveau template et les helper data.

    Retourne secret_hex si la reproduction réussit, None sinon.
    Dans un stub identique (même template) → toujours réussi.
    Dans un vrai FuzzyExtractor : tolère les variations de capture.
    """
    if not template_bytes or not helper_data_hex:
        return None
    helper_bytes = bytes.fromhex(helper_data_hex)
    if len(helper_bytes) < 32:
        return None
    salt = helper_bytes[:32]
    # Re-dériver le secret avec le même algorithme
    secret = hashlib.sha512(
        b"ARTCB-SECRET:" + salt + b":" + template_bytes
    ).digest()[:32]
    return secret.hex()


# --------------------------------------------------------------------------- #
#  HumanIdentityRecord — objet d'identité biométrique on-chain (P0-C)
# --------------------------------------------------------------------------- #

@dataclass
class HumanIdentityRecord:
    """Enregistrement d'identité humaine pour la blockchain ARTCB.

    Conforme à la spec §4 (HumanIdentityRecord) :
        - BiometricsCommitment  → commitment_hex (engagement cryptographique)
        - EncryptedBiometricTemplate → NON stocké ici (côté client uniquement)
        - EncryptionMetadata    → algorithm + helper_data_hex (public)
        - BiometricVersion      → biometric_version
        - VerificationPolicy    → verification_policy
        - Status                → status

    Ce qui N'EST PAS stocké ici :
        - image biométrique brute
        - template normalisé
        - blinding factor
        - secret FuzzyExtractor
    """

    human_id: str                          # identifiant unique dérivé de l'engagement
    commitment_hex: str                    # engagement biométrique (public)
    template_hash_hex: str                 # H(template) (public)
    helper_data_hex: str                   # helper data FuzzyExtractor (public)
    algorithm: str = "ARTCB-FUZZY-STUB-SHA512-v1"
    biometric_version: int = 1
    verification_policy: str = "fuzzy_commitment_v1"
    status: str = "active"                 # active | revoked | suspended
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    wallet_address: str | None = None      # wallet lié (créé APRÈS l'identité — spec §7)
    unique_human_proven: bool = False      # jamais True — stub non certifié
    node_id: str | None = None             # nœud ayant enregistré l'identité

    def to_chain_record(self) -> dict[str, Any]:
        """Sérialisation pour inscription on-chain.

        N'expose jamais le blinding, le template brut, ni le secret FuzzyExtractor.
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

    Le human_id est public et déterministe.
    Il ne révèle pas le template.
    """
    digest = hashlib.sha256(
        b"ARTCB-HUMAN-ID:" + bytes.fromhex(commitment_hex) + bytes.fromhex(helper_data_hex)
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
        - secret_hex             : secret FuzzyExtractor
        - blinding_hex           : facteur aveuglant de l'engagement

    `unique_human_proven` reste toujours False (stub non certifié).
    """
    human_id: str
    human_identity_record: dict[str, Any]   # public — on-chain
    commitment_public: dict[str, Any]       # public — on-chain
    # Avertissement sur les champs privés qui restent côté client
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

    Args:
        template_bytes: modèle biométrique normalisé (jamais image brute).
        wallet_address: adresse du wallet lié (créé après l'identité).
        node_id: identifiant du nœud ARTCB enregistrant l'identité.
        salt: sel de génération (aléatoire si absent).
    """
    if not template_bytes:
        raise ValueError("template_bytes vide")

    # 1. FuzzyExtractor : secret (privé) + helper (public)
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
        "P0-C enroll_biometric: human_id=%s algorithm=%s unique_human_proven=False",
        human_id, fe.algorithm,
    )

    result = BiometricEnrollmentResult(
        human_id=human_id,
        human_identity_record=record.to_chain_record(),
        commitment_public=commitment.to_public_record(),
    )

    # secret_hex et blinding_hex restent côté client — retournés mais non stockés ici
    return result, fe.secret_hex, commitment.blinding_hex


# --------------------------------------------------------------------------- #
#  Vérification d'unicité (spec §5)
# --------------------------------------------------------------------------- #

@dataclass
class UniquenessCheckResult:
    """Résultat du test d'unicité biométrique.

    match_found=True → identité déjà enregistrée → refuser la création.
    match_found=False → pas de correspondance → autoriser la création.

    `certified` reste False : vérification sur hash (stub), pas FHE.
    """
    match_found: bool
    existing_human_id: str | None = None
    match_score: float = 0.0
    certified: bool = False
    unique_human_proven: bool = False
    note: str = "STUB — unicité basée sur hash exact. Pour production : matching FHE."


def check_uniqueness(
    new_commitment: BiometricCommitment,
    existing_records: list[dict[str, Any]],
    *,
    threshold: float = 0.99,
) -> UniquenessCheckResult:
    """Vérifie si une nouvelle empreinte correspond à une identité déjà enregistrée.

    Stub : comparaison par template_hash_hex exact.
    Production : utiliser privacy_preserving_match() de homomorphic.py.

    Args:
        new_commitment: engagement du nouveau template.
        existing_records: liste des HumanIdentityRecord.to_chain_record() enregistrés.
        threshold: seuil de correspondance (stub: ignoré, comparaison exacte).

    Returns:
        UniquenessCheckResult avec match_found=True si déjà enregistré.
    """
    new_hash = new_commitment.template_hash_hex
    for rec in existing_records:
        stored_hash = rec.get("template_hash") or rec.get("template_hash_hex", "")
        if stored_hash and stored_hash == new_hash:
            logger.warning(
                "P0-C check_uniqueness: MATCH FOUND human_id=%s — creation refused",
                rec.get("human_id"),
            )
            return UniquenessCheckResult(
                match_found=True,
                existing_human_id=rec.get("human_id"),
                match_score=1.0,
                note="Template hash exact match — creation refused (spec §5).",
            )

    return UniquenessCheckResult(
        match_found=False,
        match_score=0.0,
        note="No match — new HumanIdentity can be created (stub: hash-based only).",
    )
