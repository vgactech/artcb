"""ARTCB — Politique d'identité humaine multi-appareil (R373, 2026-09-18).

Ce module centralise les règles qui découlent de R372 :
  - UV=true ≠ empreinte biométrique prouvée (limite W3C WebAuthn issue #1728)
  - PIN seul → jamais unique_human_proven, jamais création wallet économique
  - Un HumanID → au plus un wallet économique actif (wallet_per_human_limit)
  - Les 5 cas d'identité multi-appareil sont traités séparément

## Les 5 cas (TASK-001-BIOMETRIE-SUITE)

CASE_1 : même humain → même appareil (credential connue)
    → WebAuthn OK, UV ok, appareil connu → DEVICE_VERIFIED
    → Wallet existant : autoriser login / opérations

CASE_2 : même humain → nouvel appareil légitime (ADD_DEVICE)
    → WebAuthn de l'appareil existant requis → DEVICE_VERIFIED
    → Pas de nouveau wallet (spec §10, R363 déjà implémenté)

CASE_3 : même humain tentant plusieurs identités économiques (Anti-Sybil)
    → Détection : HumanID déjà lié à un wallet actif
    → Bloquer : wallet_per_human_limit → 409 human_wallet_limit_reached

CASE_4 : autre humain sur appareil déjà connu
    → Credential inconnue → 401 credential_not_found (R363)
    → Authentification normale : nouveau HumanID possible

CASE_5 : PIN seul (UV=true mais pas biométrique)
    → WebAuthn assertion valide (signature cryptographique ok)
    → MAIS : user_verification_method = PIN | UNKNOWN
    → unique_human_proven reste False
    → Opérations permises : login, ADD_DEVICE
    → Opérations BLOQUÉES : création wallet économique si politique stricte active

## UserVerificationMethod

WebAuthn ne transmet pas au serveur le mécanisme UV local utilisé
(empreinte, Face ID, PIN, autre). Le serveur ARTCB ne peut donc que :
  - déduire BIOMETRIC si l'authenticator l'atteste explicitement (pas toujours disponible)
  - stocker UNKNOWN par défaut
  - permettre à l'utilisateur de déclarer la méthode (auto-déclaration non prouvée)

Ce module implémente une politique conservatrice :
  - UNKNOWN = traité comme PIN pour les décisions d'unicité humaine
  - unique_human_proven = False dans TOUS les cas actuels

CERTIFIED_100 = False.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import enum
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.identity.human_identity_policy")

# ─── Constantes ───────────────────────────────────────────────────────────────

# Politique actuelle : 1 wallet économique actif max par HumanID.
# Peut être élevé par configuration future (D-xxx).
WALLET_PER_HUMAN_LIMIT = int(os.environ.get("ARTCB_WALLET_PER_HUMAN_LIMIT", "1"))


# ─── Enum : méthode de vérification utilisateur WebAuthn ─────────────────────

class UserVerificationMethod(str, enum.Enum):
    """Méthode de vérification utilisateur (UV) utilisée par l'authenticator.

    WebAuthn UV=true indique que l'authenticator a vérifié l'utilisateur,
    MAIS ne précise pas le mécanisme local utilisé.
    Le serveur ARTCB ne peut pas distinguer PIN de biométrie sans attestation
    explicite (limite W3C documentée, issue #1728).
    """
    BIOMETRIC = "BIOMETRIC"       # empreinte digitale, Face ID, etc. — attesté explicitement
    PIN = "PIN"                    # PIN local ou mot de passe local
    UNKNOWN = "UNKNOWN"            # défaut : UV=true mais mécanisme non connu du serveur
    NONE = "NONE"                  # UV=false (user_verified absent ou False)

    @classmethod
    def from_authenticator_flags(
        cls,
        user_verified: bool,
        *,
        declared_method: str | None = None,
        authenticator_attachment: str | None = None,
    ) -> "UserVerificationMethod":
        """Dérive la méthode UV depuis les flags WebAuthn et les métadonnées disponibles.

        Politique conservatrice (R372) :
          - user_verified=False → NONE
          - user_verified=True + declared_method="biometric" → BIOMETRIC (auto-déclaré, non prouvé)
          - user_verified=True + declared_method="pin" → PIN
          - user_verified=True + aucune info → UNKNOWN
          - authenticator_attachment="platform" seul ≠ garantit biométrie

        NOTE : declared_method vient du client — pas une preuve serveur.
        La politique d'unicité humaine utilise UNKNOWN comme conservateur (= PIN).
        """
        if not user_verified:
            return cls.NONE

        if declared_method:
            dm = declared_method.lower().strip()
            if dm in ("biometric", "fingerprint", "face", "faceid", "touchid"):
                return cls.BIOMETRIC
            if dm in ("pin", "password", "passcode", "pattern"):
                return cls.PIN

        # Aucune info sur le mécanisme → conservateur
        return cls.UNKNOWN

    def implies_unique_human(self) -> bool:
        """Une valeur UV=BIOMETRIC peut-elle contribuer à unique_human_proven ?

        Politique actuelle : NON dans tous les cas (CERTIFIED_100=False, FHE non implémenté).
        Cette méthode est là pour documenter la future logique, pas pour la déclencher.
        """
        return False   # Toujours False jusqu'à implémentation FHE + NIST BSSR

    def is_strong_for_wallet_creation(self) -> bool:
        """Ce mécanisme est-il suffisant pour créer un wallet économique ?

        Politique actuelle conservatrice :
          - BIOMETRIC → pas encore suffisant seul (FHE requis)
          - PIN / UNKNOWN / NONE → insuffisant

        Future : BIOMETRIC + ECC + FHE + anti-Sybil → True possible.
        """
        return False   # Toujours False jusqu'à certification complète


# ─── Enum : statut d'identité humaine ─────────────────────────────────────────

class HumanIdentityStatus(str, enum.Enum):
    """Statut d'identité humaine — progression vers unique_human_proven.

    Niveaux (jamais collapsés — spec §4 rapport 367) :
        UNVERIFIED         → aucune preuve
        DEVICE_VERIFIED    → WebAuthn cryptographiquement valide (credential + signature)
        AUTHENTICATOR_VERIFIED → UV=true (mécanisme inconnu)
        BIOMETRIC_CLAIMED  → UV=true + declared BIOMETRIC (auto-déclaré côté client)
        HUMAN_VERIFIED     → RESERVED — nécessite preuve externe (FHE, TEE, NIST)
        UNIQUE_HUMAN_VERIFIED → RESERVED — nécessite anti-Sybil complet

    Les niveaux HUMAN_VERIFIED et UNIQUE_HUMAN_VERIFIED ne sont jamais atteints
    automatiquement dans cette implémentation (CERTIFIED_100=False).
    """
    UNVERIFIED              = "UNVERIFIED"
    DEVICE_VERIFIED         = "DEVICE_VERIFIED"
    AUTHENTICATOR_VERIFIED  = "AUTHENTICATOR_VERIFIED"
    BIOMETRIC_CLAIMED       = "BIOMETRIC_CLAIMED"
    HUMAN_VERIFIED          = "HUMAN_VERIFIED"          # RESERVED
    UNIQUE_HUMAN_VERIFIED   = "UNIQUE_HUMAN_VERIFIED"   # RESERVED

    @classmethod
    def from_webauthn_result(
        cls,
        *,
        assertion_valid: bool,
        user_verified: bool,
        uv_method: UserVerificationMethod,
    ) -> "HumanIdentityStatus":
        """Détermine le statut depuis les résultats WebAuthn.

        Politique conservatrice (R372) : UV=true ≠ HUMAN_VERIFIED.
        """
        if not assertion_valid:
            return cls.UNVERIFIED
        if not user_verified:
            return cls.DEVICE_VERIFIED
        if uv_method == UserVerificationMethod.BIOMETRIC:
            return cls.BIOMETRIC_CLAIMED  # auto-déclaré, pas prouvé
        return cls.AUTHENTICATOR_VERIFIED  # UV=true, mécanisme inconnu


# ─── Décision de création de wallet ──────────────────────────────────────────

@dataclass
class WalletCreationDecision:
    """Résultat de la vérification wallet_per_human_limit.

    allowed=True → création autorisée (aucun wallet actif pour ce HumanID).
    allowed=False → refusée (wallet_per_human_limit atteint).
    """
    allowed: bool
    reason: str
    existing_wallet: str | None = None
    case_number: int | None = None  # parmi les 5 cas TASK-001


def check_wallet_per_human_limit(
    human_id: str,
    existing_wallet_links: list[dict[str, Any]],
    *,
    limit: int = WALLET_PER_HUMAN_LIMIT,
) -> WalletCreationDecision:
    """Vérifie qu'un HumanID n'a pas déjà atteint la limite de wallets économiques actifs.

    Un wallet est considéré "actif" si :
      - lié à ce human_id
      - non révoqué (revoked=False ou champ absent)

    CASE_3 (TASK-001) : même humain tentant plusieurs identités économiques.
    Bloquer si la limite est atteinte.

    Args:
        human_id: identifiant de l'humain (human_xxx).
        existing_wallet_links: liste de dicts {human_id, wallet_address, revoked, ...}.
        limit: nombre max de wallets actifs par HumanID (défaut WALLET_PER_HUMAN_LIMIT).

    Returns:
        WalletCreationDecision avec allowed=True/False.
    """
    active = [
        link for link in existing_wallet_links
        if link.get("human_id") == human_id
        and not link.get("revoked", False)
    ]

    if len(active) >= limit:
        existing = active[0].get("wallet_address") if active else None
        logger.warning(
            "wallet_per_human_limit: BLOCKED human_id=%s active_wallets=%d limit=%d existing=%s",
            human_id[:16], len(active), limit, (existing or "")[:16],
        )
        return WalletCreationDecision(
            allowed=False,
            reason=(
                f"human_wallet_limit_reached — HumanID déjà lié à {len(active)} wallet(s) actif(s). "
                f"Limite : {limit}. "
                "Créer un second wallet économique depuis le même HumanID est refusé (anti-Sybil CASE_3)."
            ),
            existing_wallet=existing,
            case_number=3,
        )

    logger.debug(
        "wallet_per_human_limit: ALLOWED human_id=%s active=%d limit=%d",
        human_id[:16], len(active), limit,
    )
    return WalletCreationDecision(
        allowed=True,
        reason="no_existing_wallet — création autorisée",
        case_number=None,
    )


# ─── Classifieur des 5 cas multi-appareils ───────────────────────────────────

@dataclass
class DeviceScenario:
    """Classification d'un scénario d'authentification multi-appareil.

    case_number : 1–5 (TASK-001-BIOMETRIE-SUITE)
    identity_status : HumanIdentityStatus résultant
    wallet_action : "allow_login" | "allow_add_device" | "block_new_wallet" | "deny"
    unique_human_proven : toujours False (CERTIFIED_100=False)
    """
    case_number: int
    description: str
    identity_status: HumanIdentityStatus
    wallet_action: str
    uv_method: UserVerificationMethod
    unique_human_proven: bool = False  # immuable
    certified_100: bool = False        # immuable


def classify_device_scenario(
    *,
    credential_known: bool,
    human_id_known: bool,
    human_has_active_wallet: bool,
    assertion_valid: bool,
    user_verified: bool,
    uv_method: UserVerificationMethod,
    is_new_credential: bool,
) -> DeviceScenario:
    """Classifie le scénario parmi les 5 cas TASK-001-BIOMETRIE-SUITE.

    Les 5 cas (R372) :
      CASE_1 : même humain / même appareil / credential connue
      CASE_2 : même humain / nouvel appareil légitime (ADD_DEVICE)
      CASE_3 : même humain / tentative nouveau wallet économique (Anti-Sybil)
      CASE_4 : autre humain / appareil déjà connu d'un autre HumanID
      CASE_5 : PIN seul (UV=true mais mécanisme = PIN ou UNKNOWN)

    Args:
        credential_known      : la credential_id est dans credential_store.
        human_id_known        : le human_id existe dans human_records.
        human_has_active_wallet : ce HumanID a déjà un wallet économique actif.
        assertion_valid       : verify_assertion() a réussi.
        user_verified         : flag UV de l'authenticatorData.
        uv_method             : mécanisme UV déduit.
        is_new_credential     : est-ce une nouvelle credential (ADD_DEVICE) ?

    Returns:
        DeviceScenario classifié.
    """
    status = HumanIdentityStatus.from_webauthn_result(
        assertion_valid=assertion_valid,
        user_verified=user_verified,
        uv_method=uv_method,
    )

    # CASE_5 : PIN seul — détecter en premier (transversal à d'autres cas)
    # human_id_known requis : si l'humain est inconnu → CASE_4 prime sur CASE_5
    if (
        assertion_valid
        and user_verified
        and uv_method in (UserVerificationMethod.PIN, UserVerificationMethod.UNKNOWN)
        and not is_new_credential
        and credential_known
        and human_id_known
    ):
        return DeviceScenario(
            case_number=5,
            description="PIN seul — UV=true mais mécanisme PIN ou UNKNOWN",
            identity_status=HumanIdentityStatus.AUTHENTICATOR_VERIFIED,
            wallet_action="allow_login",  # login autorisé, création wallet bloquée si stricte
            uv_method=uv_method,
        )

    # CASE_1 : même humain / même appareil
    if credential_known and human_id_known and not is_new_credential and assertion_valid:
        return DeviceScenario(
            case_number=1,
            description="même humain / même appareil / credential connue",
            identity_status=status,
            wallet_action="allow_login",
            uv_method=uv_method,
        )

    # CASE_2 : même humain / nouvel appareil (ADD_DEVICE)
    if human_id_known and is_new_credential and assertion_valid:
        return DeviceScenario(
            case_number=2,
            description="même humain / nouvel appareil légitime (ADD_DEVICE)",
            identity_status=status,
            wallet_action="allow_add_device",
            uv_method=uv_method,
        )

    # CASE_3 : même humain / tentative nouveau wallet économique
    if human_id_known and human_has_active_wallet and not is_new_credential:
        return DeviceScenario(
            case_number=3,
            description="même humain / tentative multi-wallet économique (Anti-Sybil)",
            identity_status=status,
            wallet_action="block_new_wallet",
            uv_method=uv_method,
        )

    # CASE_4 : autre humain / appareil déjà connu d'un autre HumanID
    if credential_known and not human_id_known:
        return DeviceScenario(
            case_number=4,
            description="autre humain / appareil déjà connu d'un autre HumanID",
            identity_status=HumanIdentityStatus.DEVICE_VERIFIED if assertion_valid else HumanIdentityStatus.UNVERIFIED,
            wallet_action="allow_login",  # authentification normale — nouveau HumanID possible
            uv_method=uv_method,
        )

    # Fallback générique
    return DeviceScenario(
        case_number=0,
        description="scénario non classifié — vérification requise",
        identity_status=status,
        wallet_action="deny" if not assertion_valid else "allow_login",
        uv_method=uv_method,
    )


# ─── Politique de création de wallet (combinaison des règles) ────────────────

@dataclass
class WalletCreationPolicy:
    """Décision finale de politique pour la création d'un wallet économique.

    Combine :
      - wallet_per_human_limit
      - uv_method (PIN / UNKNOWN → avertissement)
      - identity_status

    allowed=False → bloquer la création, retourner reason.
    """
    allowed: bool
    reason: str
    case_number: int | None = None
    warnings: list[str] = field(default_factory=list)
    unique_human_proven: bool = False
    certified_100: bool = False


def evaluate_wallet_creation(
    *,
    human_id: str | None,
    existing_wallet_links: list[dict[str, Any]],
    uv_method: UserVerificationMethod,
    assertion_valid: bool,
) -> WalletCreationPolicy:
    """Évalue si la création d'un nouveau wallet économique est autorisée.

    Règles (R372 + TASK-001) :
      1. Si human_id lié → vérifier wallet_per_human_limit (CASE_3)
      2. Si uv_method = PIN | UNKNOWN → avertir (pas bloquer par défaut)
      3. unique_human_proven = False dans tous les cas

    Args:
        human_id            : identifiant humain si connu, None si nouvel humain.
        existing_wallet_links : liens wallet↔human existants.
        uv_method           : mécanisme UV de la session.
        assertion_valid     : assertion WebAuthn valide.

    Returns:
        WalletCreationPolicy avec décision et raisons.
    """
    warnings: list[str] = []

    # Avertissement UV=PIN ou UNKNOWN
    if uv_method in (UserVerificationMethod.PIN, UserVerificationMethod.UNKNOWN):
        warnings.append(
            f"uv_method={uv_method.value} — PIN ou mécanisme non identifié. "
            "unique_human_proven reste False. "
            "Cette session ne constitue pas une preuve d'unicité humaine (R372)."
        )

    # Si aucun HumanID connu → pas de limite à vérifier (nouvel humain possible)
    if not human_id:
        return WalletCreationPolicy(
            allowed=True,
            reason="no_human_id — nouveau HumanID, création wallet autorisée",
            warnings=warnings,
        )

    # Vérifier wallet_per_human_limit
    limit_decision = check_wallet_per_human_limit(
        human_id, existing_wallet_links
    )
    if not limit_decision.allowed:
        return WalletCreationPolicy(
            allowed=False,
            reason=limit_decision.reason,
            case_number=3,
            warnings=warnings,
        )

    return WalletCreationPolicy(
        allowed=True,
        reason="wallet_creation_authorized",
        warnings=warnings,
    )


# ─── Store des liens wallet ↔ human ──────────────────────────────────────────

def _wallet_human_links_path() -> Path:
    data_dir = Path(os.environ.get("ARTCB_DATA_DIR", "data"))
    return data_dir / "identity" / "wallet_human_links.jsonl"


def load_wallet_human_links() -> list[dict[str, Any]]:
    """Charge les liens wallet↔human depuis wallet_human_links.jsonl."""
    p = _wallet_human_links_path()
    if not p.exists():
        return []
    links = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                links.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return links


def save_wallet_human_link(
    human_id: str,
    wallet_address: str,
    *,
    uv_method: UserVerificationMethod = UserVerificationMethod.UNKNOWN,
    created_at: float | None = None,
) -> dict[str, Any]:
    """Enregistre un lien wallet↔human dans wallet_human_links.jsonl.

    Appelé lors de la création d'un wallet économique après autorisation.
    """
    p = _wallet_human_links_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    link = {
        "human_id": human_id,
        "wallet_address": wallet_address,
        "uv_method": uv_method.value,
        "created_at": created_at or time.time(),
        "revoked": False,
        "revoked_at": None,
        "unique_human_proven": False,
        "certified_100": False,
    }

    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(link, ensure_ascii=False) + "\n")

    logger.info(
        "wallet_human_link: human_id=%s wallet=%s uv=%s",
        human_id[:16], wallet_address[:16], uv_method.value,
    )
    return link
