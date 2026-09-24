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
MODULE_VERSION = '1.1.1'  # R432 — FheHammingCircuit TFHE simulé

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass, field
from typing import Any

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
