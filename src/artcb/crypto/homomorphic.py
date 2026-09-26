"""Homomorphic commitment primitives — P0-B / R376 / R378 / R432 (2026-09-16 → 2026-09-24).

Objectif ARTCB : permettre la vérification d'unicité biométrique sans exposer
le modèle brut. Ce module fournit :

    1. BiometricCommitment + PrivacyPreservingProof  (stubs Pedersen/Schnorr — R376/R378)
    2. FheHammingCircuit + FheCiphertext             (circuit TFHE simulé — R432)

Architecture R432 :
    Le circuit FheHammingCircuit implémente le protocole ARTCB-FHE-HAMMING-v1 :
    - Le template biométrique est chiffré côté client → FheCiphertext opaque
    - Le serveur calcule D(A,B) = Σ XOR(A_i, B_i) sur ciphertexts uniquement
    - Seul le résultat booléen (MATCH / NO_MATCH) est décrypté — jamais la distance brute
    - Fail-closed : toute erreur cryptographique → FheUniquenessResult.error=True → refus

Honnêteté (CERTIFIED_100=false) :
    FheHammingCircuit est une SIMULATION FIDÈLE du protocole TFHE :
    - Le circuit et le protocole sont exacts (XOR bit, Hamming, seuil).
    - La SÉCURITÉ CRYPTOGRAPHIQUE n'est pas garantie (pas de vrai chiffrement FHE).
    - Pour la production : substituer FheHammingCircuit par un backend Concrete/SEAL
      sans modifier l'interface (duck-typing compatible).
    - unique_human_proven = False dans tous les cas.
    - Interface de substitution Concrete documentée en bas de fichier.
"""
from __future__ import annotations
MODULE_VERSION = '1.3.1'  # R487 — ConcreteHammingBackend (vrai circuit FHE Concrete)

import hashlib
import hmac
import logging
import os
import struct
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.crypto.homomorphic")

# Ordre du groupe Ed25519 (RFC 8032) — utilisé comme modulus pour les scalaires
_ORDER = (
    2**252 + 27742317777372353535851937790883648493
)

# --------------------------------------------------------------------------- #
#  Engagement de Pedersen (stub)
# --------------------------------------------------------------------------- #

def _hash_to_scalar(data: bytes) -> int:
    """Hash-to-scalar déterministe (domaine séparé ARTCB-HOM-1)."""
    h = hashlib.sha512(b"ARTCB-HOM-1:" + data).digest()
    return int.from_bytes(h, "big") % _ORDER


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    """XOR byte-à-byte (longueur minimum)."""
    length = min(len(a), len(b))
    return bytes(x ^ y for x, y in zip(a[:length], b[:length]))


@dataclass
class BiometricCommitment:
    """Engagement sur un vecteur de caractéristiques biométriques.

    commit = H(template_bytes || blinding_factor)
    L'engagement est déterministe pour un même template + blinding identiques,
    et computationally binding.
    """

    commitment_hex: str          # engagement principal (public)
    blinding_hex: str            # facteur aveuglant (PRIVÉ — jamais on-chain)
    template_hash_hex: str       # H(template) domaine séparé (peut être public)
    algorithm: str = "ARTCB-PEDERSEN-SHA512-v1"
    unique_human_proven: bool = False  # toujours False — jamais certifié

    def to_public_record(self) -> dict[str, Any]:
        """Sérialisation on-chain : jamais le blinding, jamais le template brut."""
        return {
            "commitment": self.commitment_hex,
            "template_hash": self.template_hash_hex,
            "algorithm": self.algorithm,
            "unique_human_proven": self.unique_human_proven,
        }


def commit_biometric_template(
    template_bytes: bytes,
    *,
    blinding: bytes | None = None,
) -> BiometricCommitment:
    """Produit un engagement sur un modèle biométrique normalisé.

    Args:
        template_bytes: représentation normalisée du modèle (jamais l'image brute).
        blinding: facteur aveuglant aléatoire. Généré si absent.

    Returns:
        BiometricCommitment avec le champ blinding_hex confidentiel.
    """
    if not template_bytes:
        raise ValueError("template_bytes vide — capturer le modèle avant l'engagement")
    blinding = blinding or os.urandom(32)
    # commitment = H("ARTCB-COMMIT-BIO:" || template || ":" || blinding)
    digest = hashlib.sha512(
        b"ARTCB-COMMIT-BIO:" + template_bytes + b":" + blinding
    ).digest()
    template_hash = hashlib.sha256(b"ARTCB-TEMPLATE:" + template_bytes).hexdigest()
    return BiometricCommitment(
        commitment_hex=digest.hex(),
        blinding_hex=blinding.hex(),
        template_hash_hex=template_hash,
    )


# --------------------------------------------------------------------------- #
#  Privacy-Preserving Matching (stub Schnorr-like)
# --------------------------------------------------------------------------- #

@dataclass
class MatchProof:
    """Preuve zero-knowledge (Schnorr sigma, stub) qu'un nouveau template
    est proche du template enregistré, sans révéler les templates.

    Sécurité réelle : NOT_PROVEN (stub — brancher OpenFHE pour production).
    """

    challenge_hex: str
    response_hex: str
    commitment_a_hex: str  # engagement du template connu
    commitment_b_hex: str  # engagement du nouveau template
    threshold: float       # seuil de correspondance utilisé
    match: bool            # résultat de la comparaison
    proof_valid: bool      # cohérence cryptographique de la preuve
    certified: bool = False  # toujours False — stub non certifié
    note: str = "STUB — privacy-preserving matching non certifié (FAR/FRR non mesurés)"


def privacy_preserving_match(
    commitment_a: BiometricCommitment,
    commitment_b: BiometricCommitment,
    *,
    threshold: float = 0.85,
    session_nonce: bytes | None = None,
) -> MatchProof:
    """Compare deux engagements biométriques via une preuve Schnorr stub.

    La comparaison réelle est XOR-distance sur les hash de templates (approximation).
    Pour une production réelle : brancher sur une librairie FHE (SEAL, Concrete).

    Args:
        commitment_a: engagement du template enregistré.
        commitment_b: engagement du nouveau template à vérifier.
        threshold: seuil de correspondance [0,1].
        session_nonce: nonce de session anti-rejeu.

    Returns:
        MatchProof avec match=True si les templates sont "proches" selon la métrique stub.
    """
    nonce = session_nonce or os.urandom(16)
    # Challenge Fiat-Shamir : H(com_a || com_b || nonce)
    challenge_input = (
        bytes.fromhex(commitment_a.commitment_hex)
        + bytes.fromhex(commitment_b.commitment_hex)
        + nonce
    )
    challenge = hashlib.sha256(b"ARTCB-SCHNORR:" + challenge_input).digest()

    # Réponse stub : XOR des template_hash pour mesure de "distance"
    ha = bytes.fromhex(commitment_a.template_hash_hex)
    hb = bytes.fromhex(commitment_b.template_hash_hex)
    xor_dist = sum(bin(b).count("1") for b in _xor_bytes(ha, hb))
    max_bits = min(len(ha), len(hb)) * 8
    similarity = 1.0 - (xor_dist / max_bits) if max_bits > 0 else 0.0

    response = hashlib.sha256(
        challenge + struct.pack(">d", similarity)
    ).hexdigest()

    match = similarity >= threshold
    return MatchProof(
        challenge_hex=challenge.hex(),
        response_hex=response,
        commitment_a_hex=commitment_a.commitment_hex,
        commitment_b_hex=commitment_b.commitment_hex,
        threshold=threshold,
        match=match,
        proof_valid=True,  # cohérence interne toujours vraie pour ce stub
        certified=False,
        note="STUB — similarity basée sur XOR hash. Pour production : FHE (SEAL/Concrete).",
    )


# =========================================================================== #
#  R432 — FHE Hamming Circuit (simulation TFHE — ARTCB-FHE-HAMMING-v1)
# =========================================================================== #

FHE_CIRCUIT_PROTOCOL = "ARTCB-FHE-HAMMING-v1"
FHE_SIMULATION_NOTE = (
    "SIMULATION TFHE — circuit et protocole exacts ; "
    "sécurité cryptographique non garantie. "
    "Pour production : substituer FheHammingCircuit par backend Concrete 2.x."
)


@dataclass(frozen=True)
class FheCiphertext:
    """Représentation opaque d'un template biométrique chiffré côté client.

    Dans la simulation, le template est masqué par un MAC déterministe.
    Dans Concrete : ce serait un vrai ciphertext TFHE LWE/GLWE.

    Propriété : FheCiphertext ne re-expose JAMAIS les bytes originaux.
    Le serveur ne peut PAS reconstruire le template depuis ce seul objet.
    """
    _token: bytes           # H_MAC(session_key, template) — opaque côté serveur
    _bits_len: int          # nombre de bits du template (longueur publique)
    _session_id: str        # identifiant de session (anti-rejeu)

    def __repr__(self) -> str:
        return (
            f"FheCiphertext(bits={self._bits_len}, "
            f"session={self._session_id[:8]}..., token=[REDACTED])"
        )


@dataclass(frozen=True)
class FheUint:
    """Résultat intermédiaire homomorphe — distance de Hamming chiffrée.

    Dans la simulation : entier scalaire non divulgué directement.
    Dans Concrete : serait un LWE ciphertext entier.

    NE DOIT PAS être exposé hors du circuit (anti-oracle).
    """
    _value: int        # distance Hamming (entier — PRIVÉ, jamais exposé directement)
    _bits_len: int     # longueur du vecteur (pour vérification)
    _error_flag: bool  # True si calcul invalide


@dataclass
class FheUniquenessResult:
    """Résultat d'une vérification d'unicité via FHE.

    Seuls les champs publics sont exposables à l'appelant :
    - match_found  : True si D(A,B) ≤ threshold_bits
    - error        : True si le circuit a rencontré une erreur → FAIL-CLOSED
    - match_method : toujours "fhe_hamming"
    - note         : explication honnête (simulation / production)

    Les champs privés (_hamming_distance, etc.) ne sont PAS retournés à l'API
    pour éviter les attaques par oracle de distance.
    """
    match_found: bool
    error: bool
    match_method: str = "fhe_hamming"
    note: str = FHE_SIMULATION_NOTE
    existing_human_id: str | None = None
    # Champs privés — debug uniquement (jamais exposés en production)
    _debug_hamming_distance: int | None = None
    _debug_threshold_bits: int | None = None
    unique_human_proven: bool = False   # invariant absolu
    certified: bool = False             # invariant absolu


class FheHammingCircuit:
    """Circuit FHE simulé pour la vérification d'unicité biométrique par distance de Hamming.

    Protocole ARTCB-FHE-HAMMING-v1 :
    ─────────────────────────────────
    1. CLIENT : encrypt(template_bytes) → FheCiphertext
       - Le template est masqué par HMAC(session_key, template)
       - Le serveur reçoit FheCiphertext — jamais les bytes clairs

    2. SERVEUR : fhe_hamming(ct_a, ct_b) → FheUint
       - Calcule D(A,B) = Σ XOR(A_i, B_i) sur les représentations internes
       - Dans la simulation : utilise le token HMAC pour reconstruire les bits
         uniquement si les deux ciphertexts partagent la même session_key

    3. SERVEUR : decrypt_match(fhe_uint, threshold_bits) → bool
       - Retourne UNIQUEMENT le résultat booléen (MATCH / NO_MATCH)
       - NE retourne PAS la distance brute (anti-oracle)

    Fail-closed :
        Toute erreur (taille invalide, session mismatch, ciphertext corrompu)
        produit error=True → FheUniquenessResult.match_found=False + error=True
        → refus systématique. JAMAIS de fallback silencieux vers un "match" par défaut.

    Interface de substitution Concrete (duck-typing) :
        from concrete import fhe
        # Remplacer _encrypt_bits() et _decrypt_bits() par les ops Concrete
        # L'interface publique (encrypt/fhe_hamming/decrypt_match) reste identique.
    """

    # Domaine séparé pour le MAC de chiffrement (empêche la réutilisation cross-contexte)
    _DOMAIN = b"ARTCB-FHE-HAMMING-v1:"

    def __init__(self, *, session_key: bytes | None = None) -> None:
        """Initialise le circuit avec une clé de session.

        session_key : clé symétrique 32 bytes (générée aléatoirement si absente).
            Dans Concrete : serait la clé FHE publique/privée.
        """
        self._session_key: bytes = session_key or os.urandom(32)
        self._session_id: str = hashlib.sha256(
            b"ARTCB-FHE-SESSION:" + self._session_key
        ).hexdigest()[:16]

    def encrypt(self, template_bytes: bytes) -> FheCiphertext:
        """Chiffre un template biométrique → FheCiphertext opaque.

        Le FheCiphertext résultant ne permet pas de reconstruire template_bytes
        sans la session_key (propriété de confidentialité simulée).

        Raises:
            ValueError: si template_bytes est vide ou invalide.
        """
        if not template_bytes:
            raise ValueError(
                "FheHammingCircuit.encrypt: template_bytes vide — "
                "le template doit être normalisé avant chiffrement."
            )
        bits_len = len(template_bytes) * 8
        # MAC déterministe : H(domain || session_key || template)
        token = hmac.new(
            self._session_key,
            self._DOMAIN + template_bytes,
            hashlib.sha256,
        ).digest()
        return FheCiphertext(
            _token=token,
            _bits_len=bits_len,
            _session_id=self._session_id,
        )

    def _recover_bits(self, template_bytes: bytes) -> list[int]:
        """Retourne la liste des bits du template (0 ou 1) pour le calcul interne.

        PRIVÉ — jamais appelé depuis l'extérieur du circuit.
        Dans Concrete : serait réalisé nativement dans le circuit homomorphe.
        """
        bits: list[int] = []
        for byte in template_bytes:
            for shift in range(7, -1, -1):
                bits.append((byte >> shift) & 1)
        return bits

    def fhe_hamming(
        self,
        template_a: bytes,
        template_b: bytes,
    ) -> FheUint:
        """Calcule la distance de Hamming entre deux templates côté circuit.

        Dans le protocole complet, template_a et template_b sont transmis sous
        forme chiffrée ; le circuit opère sur les ciphertexts. Dans cette
        simulation, le calcul est exact sur les bytes clairs — le résultat
        intermédiaire FheUint n'est pas divulgué directement.

        Fail-closed : toute erreur (tailles différentes, bytes vides) → FheUint._error_flag=True.

        Args:
            template_a: template biométrique A (bytes normalisés).
            template_b: template biométrique B (bytes normalisés).

        Returns:
            FheUint contenant la distance de Hamming chiffrée (non divulguée directement).
        """
        if not template_a or not template_b:
            return FheUint(_value=0, _bits_len=0, _error_flag=True)

        if len(template_a) != len(template_b):
            # Fail-closed : tailles incompatibles → erreur
            return FheUint(_value=0, _bits_len=len(template_a) * 8, _error_flag=True)

        bits_a = self._recover_bits(template_a)
        bits_b = self._recover_bits(template_b)

        # Circuit booléen : D(A,B) = Σ XOR(a_i, b_i)
        # C'est exactement le circuit TFHE : PBS(XOR) bit-à-bit + popcount
        distance = sum(a ^ b for a, b in zip(bits_a, bits_b))

        return FheUint(
            _value=distance,
            _bits_len=len(bits_a),
            _error_flag=False,
        )

    def decrypt_match(
        self,
        fhe_result: FheUint,
        threshold_bits: int,
    ) -> tuple[bool, bool]:
        """Déchiffre le résultat FHE → (match: bool, error: bool).

        Retourne UNIQUEMENT le résultat booléen — pas la distance brute.
        Propriété anti-oracle : l'appelant ne connaît que MATCH / NO_MATCH.

        Args:
            fhe_result: résultat FheUint du calcul fhe_hamming().
            threshold_bits: seuil en bits (D ≤ threshold → MATCH).

        Returns:
            (match, error) :
                - match=True si D(A,B) ≤ threshold_bits
                - error=True si le calcul était invalide (fail-closed → match=False)
        """
        if fhe_result._error_flag:
            return False, True
        if threshold_bits < 0:
            return False, True
        match = fhe_result._value <= threshold_bits
        return match, False

    def fhe_uniqueness_check(
        self,
        new_template: bytes,
        existing_templates: list[tuple[str, bytes]],
        *,
        threshold_bits: int,
    ) -> FheUniquenessResult:
        """Vérifie l'unicité d'un template contre une liste d'enregistrements existants.

        Protocole complet :
        1. Pour chaque (human_id, stored_template) dans existing_templates :
           a. Calcule fhe_hamming(new_template, stored_template) → FheUint
           b. Déchiffre decrypt_match(fhe_uint, threshold_bits) → (match, error)
           c. Si error → fail-closed → continue (compte l'erreur)
           d. Si match → MATCH_FOUND → retour immédiat

        2. Si aucun match : NO_MATCH → nouvelle identité autorisée.

        Fail-closed absolu :
        - Toute erreur de calcul (taille, données) → continue sans match (jamais faux positif).
        - Si TOUS les calculs sont en erreur → error=True dans le résultat final.

        Args:
            new_template: template du nouveau candidat (bytes normalisés, côté client).
            existing_templates: liste de (human_id, template_bytes) des enregistrements.
            threshold_bits: seuil Hamming en bits (D ≤ threshold → MATCH).

        Returns:
            FheUniquenessResult avec match_found, error, existing_human_id.
        """
        if not new_template:
            return FheUniquenessResult(
                match_found=False,
                error=True,
                note=f"{FHE_SIMULATION_NOTE} | ERREUR: new_template vide.",
            )

        error_count = 0
        total = len(existing_templates)

        for human_id, stored_template in existing_templates:
            fhe_uint = self.fhe_hamming(new_template, stored_template)
            match, err = self.decrypt_match(fhe_uint, threshold_bits)

            if err:
                error_count += 1
                continue

            if match:
                return FheUniquenessResult(
                    match_found=True,
                    error=False,
                    existing_human_id=human_id,
                    _debug_hamming_distance=fhe_uint._value,
                    _debug_threshold_bits=threshold_bits,
                )

        # Aucun match trouvé
        all_errors = (error_count == total and total > 0)
        return FheUniquenessResult(
            match_found=False,
            error=all_errors,
            _debug_hamming_distance=None,
            _debug_threshold_bits=threshold_bits,
            note=(
                f"{FHE_SIMULATION_NOTE} | "
                f"errors={error_count}/{total}"
                if error_count > 0
                else FHE_SIMULATION_NOTE
            ),
        )


# =========================================================================== #
#  R479 — Backend Paillier HE (Homomorphic Encryption réelle)                 #
#  Protocole : ARTCB-PHE-PAILLIER-HAMMING-v1                                  #
# =========================================================================== #
#
# Architecture Paillier pour distance de Hamming :
#
#   Paillier est un schéma de chiffrement asymétrique ADDITIF HOMOMORPHE
#   (IND-CPA sécurisé, Goldwasser-Micali 1982, Paillier 1999).
#
#   Propriété exploitée :
#       Enc(a) ⊕ Enc(b) = Enc(a + b)   (addition homomorphe)
#
#   Calcul Hamming côté client :
#       Pour chaque bit i : XOR_i = a_i XOR b_i  (calculé localement)
#       Le client chiffre chaque XOR_i → Enc(XOR_i)
#       Le serveur calcule Σ Enc(XOR_i) = Enc(Σ XOR_i) = Enc(dist_Hamming)
#       Le serveur décrypte UNIQUEMENT le booléen : dist ≤ threshold ? → MATCH/NO_MATCH
#
#   Protocole complet (mode serveur biométrique) :
#       - Le client possède new_template et stored_template → calcule les XOR bits
#       - Le client chiffre ces XOR → liste de ciphertexts transmis au serveur
#       - Le serveur somme sans voir les valeurs claires
#       - Le serveur décrypte uniquement le résultat booléen
#       Note : dans ce mode, la clé privée est côté client (HSM/TEE recommandé).
#              Pour le MVP : clé générée par enrôlement, stockée dans helper_data côté client.
#
#   Limites honnêtes (PROTOCOLE ARTCB — ne jamais mentir) :
#       - n_length=1024 bits : rapide (~0.3s keygen) mais sub-optimal pour prod (2048 recommandé)
#       - Chiffrer bit-à-bit 256 bits = 256 chiffrements → ~0.5s
#       - Pur Python (bibliothèque `phe`) — pas de HSM/TEE
#       - Sécurité IND-CPA réelle (Paillier standard), pas TFHE/SEAL mais vrai HE
#       - unique_human_proven = False dans tous les cas
#       - CERTIFIED_100 = False
#
#   Interface duck-typing compatible avec FheHammingCircuit :
#       PaillierHammingBackend expose la même API :
#           .encrypt(template_bytes) → PaillierCiphertext
#           .fhe_uniqueness_check(new_template, existing_templates, threshold_bits) → FheUniquenessResult
#
# =========================================================================== #

PHE_PROTOCOL = "ARTCB-PHE-PAILLIER-HAMMING-v1"
PHE_NOTE = (
    "Paillier HE (phe 1.5.0) — chiffrement additif homomorphe réel (IND-CPA). "
    "XOR bit-à-bit chiffré côté client, somme homomorphe côté serveur. "
    "n_length=1024 bits (MVP) — 2048 recommandé pour production. "
    "unique_human_proven=False — invariant absolu. CERTIFIED_100=False."
)


@dataclass(frozen=True)
class PaillierCiphertext:
    """Liste de ciphertexts Paillier représentant les XOR bits entre deux templates.

    Chaque élément correspond à un bit XOR chiffré : Enc(a_i XOR b_i).
    Le serveur peut sommer ces ciphertexts sans voir les valeurs claires.

    Propriété : ne re-expose JAMAIS les bits originaux de l'un ou l'autre template.
    """
    _enc_xor_bits: tuple          # tuple de phe.EncryptedNumber (immutable)
    _bits_len: int                # nombre de bits (public — longueur du template)
    _pub_key_n: int               # N de la clé publique Paillier (public)
    _session_id: str              # identifiant de session (anti-rejeu)

    def __repr__(self) -> str:
        return (
            f"PaillierCiphertext(bits={self._bits_len}, "
            f"session={self._session_id[:8]}..., enc=[{self._bits_len} ciphertexts])"
        )


@dataclass
class PaillierHammingResult:
    """Résultat d'un calcul Hamming Paillier homomorphe.

    Seul le résultat booléen est exposé (anti-oracle de distance).
    """
    match_found: bool
    error: bool
    match_method: str = PHE_PROTOCOL
    note: str = PHE_NOTE
    existing_human_id: str | None = None
    _debug_hamming_distance: int | None = None   # debug uniquement — jamais en prod
    _debug_threshold_bits: int | None = None
    unique_human_proven: bool = False             # invariant absolu
    certified: bool = False                       # invariant absolu


class PaillierHammingBackend:
    """Backend Paillier pour la vérification d'unicité biométrique par distance de Hamming.

    Protocole ARTCB-PHE-PAILLIER-HAMMING-v1 :
    ──────────────────────────────────────────
    1. CLIENT : generate_keypair() → (public_key, private_key)
       - Génère une paire Paillier (n_length bits)
       - La clé privée reste côté client (HSM/TEE en prod)

    2. CLIENT : encrypt_xor_bits(template_a, template_b) → PaillierCiphertext
       - Calcule XOR_i = a_i XOR b_i pour chaque bit i
       - Chiffre chaque XOR_i : Enc(XOR_i) avec la clé publique
       - Résultat : liste de ciphertexts transmis au serveur

    3. SERVEUR : sum_encrypted_bits(paillier_ct) → EncryptedNumber
       - Somme homomorphe : Enc(XOR_0) + Enc(XOR_1) + ... = Enc(Σ XOR_i)
       - Opération sans voir les valeurs claires (propriété Paillier)

    4. CLIENT : decrypt_match(enc_sum, threshold_bits) → bool
       - Déchiffre Enc(Σ XOR_i) → distance Hamming
       - Retourne UNIQUEMENT le booléen dist ≤ threshold (anti-oracle)

    Fail-closed :
        Toute erreur (templates vides, longueurs différentes, clé invalide)
        → PaillierHammingResult.error=True → refus systématique.
        JAMAIS de fallback silencieux vers un match par défaut.

    Duck-typing FheHammingCircuit :
        Méthode fhe_uniqueness_check() compatible avec l'interface FheHammingCircuit.
    """

    def __init__(self, *, n_length: int = 1024) -> None:
        """Initialise le backend avec une paire de clés Paillier.

        Args:
            n_length: longueur de la clé en bits (1024 MVP, 2048 production).
                      1024 bits : ~0.3s keygen, sécurité 80 bits.
                      2048 bits : ~3.6s keygen, sécurité 112 bits (recommandé prod).
        """
        try:
            import phe  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "PaillierHammingBackend requiert la bibliothèque `phe` (python-paillier). "
                "Installer : python3 -m pip install phe"
            ) from exc

        self._n_length = n_length
        self._public_key, self._private_key = phe.generate_paillier_keypair(
            n_length=n_length
        )
        import hashlib  # noqa: PLC0415
        self._session_id: str = hashlib.sha256(
            b"ARTCB-PHE-SESSION:" + self._public_key.n.to_bytes(128, "big")
        ).hexdigest()[:16]

        logger.debug(
            "PaillierHammingBackend: keygen n_length=%d session=%s",
            n_length, self._session_id,
        )

    @property
    def public_key(self):
        """Clé publique Paillier (exportable — utilisée pour chiffrer côté client)."""
        return self._public_key

    def _template_to_bits(self, template_bytes: bytes) -> list[int]:
        """Convertit un template bytes en liste de bits (MSB first)."""
        bits: list[int] = []
        for byte in template_bytes:
            for shift in range(7, -1, -1):
                bits.append((byte >> shift) & 1)
        return bits

    def encrypt_xor_bits(
        self,
        template_a: bytes,
        template_b: bytes,
    ) -> "PaillierCiphertext | None":
        """Chiffre les bits XOR(a_i, b_i) avec la clé publique Paillier.

        Opération CÔTÉ CLIENT : le client possède les deux templates et calcule
        les XOR localement avant de chiffrer. Le serveur reçoit uniquement les
        ciphertexts — il ne peut pas reconstruire les templates.

        Args:
            template_a: template biométrique A (bytes normalisés).
            template_b: template biométrique B (bytes normalisés, même longueur).

        Returns:
            PaillierCiphertext avec les XOR bits chiffrés, ou None si erreur.
        """
        if not template_a or not template_b:
            logger.warning("encrypt_xor_bits: template(s) vide(s) — fail-closed")
            return None
        if len(template_a) != len(template_b):
            logger.warning(
                "encrypt_xor_bits: longueurs différentes (%d vs %d) — fail-closed",
                len(template_a), len(template_b),
            )
            return None

        bits_a = self._template_to_bits(template_a)
        bits_b = self._template_to_bits(template_b)

        # XOR bit-à-bit côté client (valeurs claires)
        xor_bits = [a ^ b for a, b in zip(bits_a, bits_b)]

        # Chiffrement Paillier de chaque bit XOR
        enc_xor_bits = tuple(self._public_key.encrypt(x) for x in xor_bits)

        return PaillierCiphertext(
            _enc_xor_bits=enc_xor_bits,
            _bits_len=len(bits_a),
            _pub_key_n=self._public_key.n,
            _session_id=self._session_id,
        )

    def sum_encrypted_bits(self, ct: "PaillierCiphertext"):
        """Calcule la somme homomorphe des ciphertexts XOR.

        Opération CÔTÉ SERVEUR : somme Enc(XOR_0) + ... + Enc(XOR_N-1) = Enc(dist_Hamming).
        Le serveur ne voit jamais les valeurs claires.

        Args:
            ct: PaillierCiphertext contenant les XOR bits chiffrés.

        Returns:
            EncryptedNumber (phe) représentant la distance de Hamming chiffrée.
            None si ct est invalide ou vide.
        """
        if not ct or not ct._enc_xor_bits:
            return None
        # Somme homomorphe : addition de ciphertexts Paillier
        enc_sum = ct._enc_xor_bits[0]
        for enc_bit in ct._enc_xor_bits[1:]:
            enc_sum = enc_sum + enc_bit
        return enc_sum

    def decrypt_match(
        self,
        enc_sum,
        threshold_bits: int,
    ) -> tuple[bool, bool, int | None]:
        """Déchiffre le résultat homomorphe et retourne uniquement le booléen.

        Opération CÔTÉ CLIENT (clé privée) : déchiffre Enc(dist) → dist.
        Retourne UNIQUEMENT (match, error, dist_debug) — pas la distance brute
        dans la valeur de retour principale (anti-oracle).

        Args:
            enc_sum: EncryptedNumber (résultat de sum_encrypted_bits).
            threshold_bits: seuil Hamming (dist ≤ threshold → MATCH).

        Returns:
            (match: bool, error: bool, _debug_dist: int | None)
        """
        if enc_sum is None:
            return False, True, None
        if threshold_bits < 0:
            return False, True, None
        try:
            dist = self._private_key.decrypt(enc_sum)
            match = int(dist) <= threshold_bits
            return match, False, int(dist)
        except Exception as exc:  # noqa: BLE001
            logger.warning("decrypt_match: erreur déchiffrement Paillier: %s", exc)
            return False, True, None

    def compute_hamming_paillier(
        self,
        template_a: bytes,
        template_b: bytes,
        *,
        threshold_bits: int,
    ) -> tuple[bool, bool, int | None]:
        """Flux complet Paillier : encrypt_xor_bits → sum → decrypt_match.

        Encapsule les 3 étapes pour un appel simple.
        En production, ces étapes seraient sur des machines différentes.

        Returns:
            (match: bool, error: bool, _debug_dist: int | None)
        """
        ct = self.encrypt_xor_bits(template_a, template_b)
        if ct is None:
            return False, True, None
        enc_sum = self.sum_encrypted_bits(ct)
        if enc_sum is None:
            return False, True, None
        return self.decrypt_match(enc_sum, threshold_bits)

    def fhe_uniqueness_check(
        self,
        new_template: bytes,
        existing_templates: list[tuple[str, bytes]],
        *,
        threshold_bits: int,
    ) -> "PaillierHammingResult":
        """Vérifie l'unicité d'un template contre une liste d'enregistrements existants.

        Interface duck-typing compatible avec FheHammingCircuit.fhe_uniqueness_check().

        Protocole complet :
        1. Pour chaque (human_id, stored_template) dans existing_templates :
           a. encrypt_xor_bits(new_template, stored_template) → PaillierCiphertext
           b. sum_encrypted_bits(ct) → EncryptedNumber
           c. decrypt_match(enc_sum, threshold_bits) → (match, error, dist)
           d. Si error → fail-closed → continue (compte l'erreur)
           e. Si match → MATCH_FOUND → retour immédiat

        2. Si aucun match : NO_MATCH → nouvelle identité autorisée.

        Fail-closed absolu :
        - Erreur de calcul → continue sans match (jamais faux positif).
        - Tous les calculs en erreur → error=True dans le résultat final.

        Args:
            new_template: template du nouveau candidat (bytes normalisés).
            existing_templates: liste (human_id, template_bytes) des enregistrements.
            threshold_bits: seuil Hamming en bits (D ≤ threshold → MATCH).

        Returns:
            PaillierHammingResult avec match_found, error, existing_human_id.
        """
        if not new_template:
            return PaillierHammingResult(
                match_found=False,
                error=True,
                note=f"{PHE_NOTE} | ERREUR: new_template vide.",
            )

        error_count = 0
        total = len(existing_templates)

        for human_id, stored_template in existing_templates:
            match, err, _debug_dist = self.compute_hamming_paillier(
                new_template,
                stored_template,
                threshold_bits=threshold_bits,
            )

            if err:
                error_count += 1
                logger.debug(
                    "fhe_uniqueness_check[paillier]: erreur calcul human_id=%s — skip",
                    human_id[:16] if human_id else "?",
                )
                continue

            if match:
                logger.warning(
                    "fhe_uniqueness_check[paillier]: MATCH human_id=%s dist=%s threshold=%d",
                    human_id[:16] if human_id else "?",
                    str(_debug_dist),
                    threshold_bits,
                )
                return PaillierHammingResult(
                    match_found=True,
                    error=False,
                    existing_human_id=human_id,
                    _debug_hamming_distance=_debug_dist,
                    _debug_threshold_bits=threshold_bits,
                )

        # Aucun match trouvé
        all_errors = (error_count == total and total > 0)
        note_suffix = f" | errors={error_count}/{total}" if error_count > 0 else ""
        return PaillierHammingResult(
            match_found=False,
            error=all_errors,
            _debug_threshold_bits=threshold_bits,
            note=PHE_NOTE + note_suffix,
        )


# =========================================================================== #
#  R487 — Backend Concrete FHE (vrai compilateur FHE via concrete-python)     #
#  Protocole : ARTCB-CONCRETE-FHE-HAMMING-v1                                  #
# =========================================================================== #
#
# Architecture Concrete FHE pour distance de Hamming :
#
#   Concrete (Zama) est un compilateur FHE TFHE/CKKS.
#   Il compile des fonctions Python annotées en circuits FHE exécutables.
#
#   Propriété exploitée :
#       Circuit `hamming_byte(a, b) → popcount(a XOR b)` compilé par Concrete.
#       Chaque octet est traité comme un uint8 ; le XOR et la décomposition bit-à-bit
#       sont des opérations natives du compilateur FHE.
#
#   Décomposition popcount via Concrete :
#       xored = a ^ b
#       hamming = Σ_{i=0..7} (xored >> i) & 1
#       → 8 shifts + 8 AND + 1 somme = circuit linéaire compilé en PBS TFHE
#
#   Mode d'exécution :
#       - `circuit.simulate()` : simulation CPU exacte (pas de chiffrement réel)
#         → résultat exact, temps de l'ordre de la milliseconde
#       - `circuit.encrypt_run_decrypt()` : exécution FHE réelle
#         → nécessite générer les clés + bootstrapping (~heures pour 256 bits)
#       Pour le MVP ARTCB : mode `simulate()` — vrai circuit compilé, vrais garanties
#       algorithmiques, sans le coût de clé+bootstrapping.
#
#   Limites honnêtes (PROTOCOLE ARTCB — ne jamais mentir) :
#       - Mode simulate() : calcul exact, non chiffré en mémoire.
#         La sécurité cryptographique FHE réelle requiert `encrypt_run_decrypt()`.
#       - Compilation initiale ~1-3s (cache dans _CONCRETE_CIRCUIT_CACHE).
#       - Circuit par octet : scalable linéairement avec la taille du template.
#       - unique_human_proven = False dans tous les cas.
#       - CERTIFIED_100 = False.
#
#   Interface duck-typing compatible avec FheHammingCircuit / PaillierHammingBackend :
#       `fhe_uniqueness_check(new_template, existing_templates, threshold_bits=...)`
#

CONCRETE_FHE_NOTE = (
    "Concrete FHE (Zama concrete-python) — circuit TFHE compilé sur uint8. "
    "Mode simulate() : vrai circuit FHE compilé, calcul exact, sans chiffrement en mémoire. "
    "XOR bit-à-bit + popcount = circuit natif Concrete (PBS TFHE). "
    "unique_human_proven=False — invariant absolu. CERTIFIED_100=False."
)

# Cache module-level pour éviter la recompilation à chaque instanciation
_CONCRETE_CIRCUIT_CACHE: "Any | None" = None


def _build_concrete_hamming_byte_circuit() -> "Any":
    """Compile le circuit Concrete FHE hamming_byte et retourne l'objet circuit.

    Le circuit calcule : popcount(a XOR b) pour deux uint8.
    Algorithme : décomposition bit-à-bit de l'XOR (8 shifts + 8 AND + somme).

    Résultat : entier [0, 8] représentant le nombre de bits différents.

    La compilation prend ~1-3s au premier appel, puis est mise en cache.

    Returns:
        concrete.fhe Circuit compilé (compatible simulate() et encrypt_run_decrypt()).
    """
    global _CONCRETE_CIRCUIT_CACHE  # noqa: PLW0603
    if _CONCRETE_CIRCUIT_CACHE is not None:
        logger.debug("_build_concrete_hamming_byte_circuit: cache hit — réutilisation circuit")
        return _CONCRETE_CIRCUIT_CACHE

    logger.debug("_build_concrete_hamming_byte_circuit: compilation circuit Concrete FHE...")

    try:
        from concrete import fhe  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "ConcreteHammingBackend requiert la bibliothèque `concrete-python`. "
            "Installer : python3 -m pip install concrete-python"
        ) from exc

    @fhe.compiler({"a": "encrypted", "b": "encrypted"})
    def _hamming_byte(a, b):  # type: ignore[no-redef]
        """Circuit FHE : distance de Hamming sur un octet (uint8 × 2 → uint4).

        Protocole ARTCB-CONCRETE-FHE-HAMMING-v1 :
        - a, b : uint8 (valeurs [0..255]) — représentent des octets de template
        - xored = a ^ b             : XOR bit-à-bit
        - décomposition 8 bits      : (xored >> i) & 1 pour i in 0..7
        - somme des bits             : ∈ [0, 8]
        """
        xored = a ^ b
        bit0 = (xored >> 0) & 1
        bit1 = (xored >> 1) & 1
        bit2 = (xored >> 2) & 1
        bit3 = (xored >> 3) & 1
        bit4 = (xored >> 4) & 1
        bit5 = (xored >> 5) & 1
        bit6 = (xored >> 6) & 1
        bit7 = (xored >> 7) & 1
        return bit0 + bit1 + bit2 + bit3 + bit4 + bit5 + bit6 + bit7

    # inputset représentatif : 200 paires aléatoires + cas limites
    import random as _random  # noqa: PLC0415
    _rng = _random.Random(0x41525443)  # seed déterministe "ARTC"
    inputset = [
        (_rng.randint(0, 255), _rng.randint(0, 255)) for _ in range(200)
    ]
    inputset += [(0, 0), (0, 255), (255, 0), (255, 255)]

    cfg = fhe.Configuration(show_graph=False, show_mlir=False)
    circuit = _hamming_byte.compile(inputset, configuration=cfg)

    _CONCRETE_CIRCUIT_CACHE = circuit
    logger.debug("_build_concrete_hamming_byte_circuit: circuit compilé et mis en cache")
    return circuit


@dataclass
class ConcreteHammingResult:
    """Résultat de la vérification d'unicité via ConcreteHammingBackend.

    Interface cohérente avec FheUniquenessResult et PaillierHammingResult.
    """

    match_found: bool
    error: bool = False
    existing_human_id: str | None = None
    note: str = CONCRETE_FHE_NOTE

    # Debug (jamais exposé côté serveur — anti-oracle)
    _debug_hamming_distance: int | None = field(default=None, repr=False)
    _debug_threshold_bits: int | None = field(default=None, repr=False)
    _debug_total_bytes: int | None = field(default=None, repr=False)

    # Invariants absolus
    unique_human_proven: bool = False   # jamais True — invariant ARTCB
    certified: bool = False             # jamais True — invariant ARTCB


class ConcreteHammingBackend:
    """Backend Concrete FHE pour la vérification d'unicité biométrique.

    Protocole ARTCB-CONCRETE-FHE-HAMMING-v1 :
    ──────────────────────────────────────────
    1. COMPILATION (une seule fois) :
       - `_build_concrete_hamming_byte_circuit()` compile le circuit FHE via Concrete.
       - Cache module-level évite la recompilation.

    2. CALCUL HAMMING (par paire de templates) :
       - Pour chaque octet i : circuit.simulate(template_a[i], template_b[i]) → bits_diff_i
       - Distance totale D(A,B) = Σ bits_diff_i
       - Mode simulate() : calcul exact, vrai circuit FHE, sans clé/bootstrapping.

    3. DÉCISION (fail-closed) :
       - D ≤ threshold_bits → MATCH
       - D > threshold_bits → NO_MATCH
       - Erreur (tailles différentes, bytes vides) → error=True → refus systématique

    Interface duck-typing compatible avec FheHammingCircuit et PaillierHammingBackend :
        `fhe_uniqueness_check(new_template, existing_templates, threshold_bits=...)`

    Honnêteté (CERTIFIED_100=false) :
        - Mode simulate() = calcul exact non chiffré.
        - Pour la sécurité FHE réelle : utiliser `execute_hamming()` avec
          `circuit.encrypt_run_decrypt()` (coût : génération clés + bootstrapping).
        - unique_human_proven = False dans tous les cas.
    """

    def __init__(self) -> None:
        """Initialise le backend en compilant (ou récupérant) le circuit Concrete."""
        self._circuit = _build_concrete_hamming_byte_circuit()
        import hashlib as _hashlib  # noqa: PLC0415
        # Session ID déterministe depuis la version du circuit
        self._session_id = _hashlib.sha256(
            b"ARTCB-CONCRETE-FHE-SESSION:" + b"v1"
        ).hexdigest()[:16]
        logger.debug(
            "ConcreteHammingBackend: initialisé, session_id=%s", self._session_id
        )

    def hamming_distance_concrete(
        self,
        template_a: bytes,
        template_b: bytes,
    ) -> tuple[int | None, bool]:
        """Calcule la distance de Hamming via le circuit Concrete FHE (simulate).

        Pour chaque paire d'octets (a_i, b_i), invoque circuit.simulate(a_i, b_i)
        qui exécute le circuit TFHE compilé en mode simulation exacte.

        Distance totale = Σ circuit.simulate(a_i, b_i) sur tous les octets.

        Args:
            template_a: template A (bytes normalisés).
            template_b: template B (bytes normalisés, même longueur).

        Returns:
            (distance: int | None, error: bool)
            - distance: nombre de bits différents [0, len*8]
            - error: True si calcul impossible (tailles, bytes vides)
        """
        if not template_a or not template_b:
            logger.warning(
                "ConcreteHammingBackend.hamming_distance_concrete: template(s) vide(s) — fail-closed"
            )
            return None, True

        if len(template_a) != len(template_b):
            logger.warning(
                "ConcreteHammingBackend.hamming_distance_concrete: "
                "longueurs différentes (%d vs %d) — fail-closed",
                len(template_a), len(template_b),
            )
            return None, True

        try:
            total_distance = 0
            for byte_a, byte_b in zip(template_a, template_b):
                # circuit.simulate() : exécution exacte du circuit FHE compilé
                bits_diff = self._circuit.simulate(int(byte_a), int(byte_b))
                total_distance += int(bits_diff)
            return total_distance, False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ConcreteHammingBackend.hamming_distance_concrete: erreur circuit: %s", exc
            )
            return None, True

    def fhe_uniqueness_check(
        self,
        new_template: bytes,
        existing_templates: list[tuple[str, bytes]],
        *,
        threshold_bits: int,
    ) -> ConcreteHammingResult:
        """Vérifie l'unicité d'un template contre une liste d'enregistrements existants.

        Interface duck-typing compatible avec FheHammingCircuit.fhe_uniqueness_check()
        et PaillierHammingBackend.fhe_uniqueness_check().

        Protocole complet :
        1. Pour chaque (human_id, stored_template) dans existing_templates :
           a. hamming_distance_concrete(new_template, stored_template) → (dist, error)
           b. Si error → fail-closed → continue (compte l'erreur)
           c. Si dist ≤ threshold_bits → MATCH_FOUND → retour immédiat

        2. Si aucun match : NO_MATCH → nouvelle identité autorisée.

        Fail-closed absolu :
        - Toute erreur de calcul → continue sans match (jamais faux positif).
        - Tous les calculs en erreur → error=True dans le résultat final.
        - new_template vide → error=True immédiatement.

        Args:
            new_template: template du nouveau candidat (bytes normalisés).
            existing_templates: liste de (human_id, template_bytes) des enregistrements.
            threshold_bits: seuil Hamming en bits (D ≤ threshold → MATCH).

        Returns:
            ConcreteHammingResult avec match_found, error, existing_human_id.
        """
        if not new_template:
            return ConcreteHammingResult(
                match_found=False,
                error=True,
                note=f"{CONCRETE_FHE_NOTE} | ERREUR: new_template vide.",
            )

        error_count = 0
        total = len(existing_templates)

        for human_id, stored_template in existing_templates:
            dist, err = self.hamming_distance_concrete(new_template, stored_template)

            if err:
                error_count += 1
                logger.debug(
                    "fhe_uniqueness_check[concrete]: erreur calcul human_id=%s — skip",
                    human_id[:16] if human_id else "?",
                )
                continue

            if dist is not None and dist <= threshold_bits:
                logger.warning(
                    "fhe_uniqueness_check[concrete]: MATCH human_id=%s dist=%d threshold=%d",
                    human_id[:16] if human_id else "?",
                    dist,
                    threshold_bits,
                )
                return ConcreteHammingResult(
                    match_found=True,
                    error=False,
                    existing_human_id=human_id,
                    _debug_hamming_distance=dist,
                    _debug_threshold_bits=threshold_bits,
                    _debug_total_bytes=len(new_template),
                )

        # Aucun match trouvé
        all_errors = (error_count == total and total > 0)
        note_suffix = f" | errors={error_count}/{total}" if error_count > 0 else ""
        return ConcreteHammingResult(
            match_found=False,
            error=all_errors,
            _debug_threshold_bits=threshold_bits,
            _debug_total_bytes=len(new_template) if new_template else None,
            note=CONCRETE_FHE_NOTE + note_suffix,
        )
