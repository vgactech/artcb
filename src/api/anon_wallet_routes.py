"""Routes anonymes de création de wallet — R358.

Architecture cible :
  L'utilisateur ne fournit AUCUN nom.
  Le name technique du wallet est dérivé automatiquement
  du credential_id WebAuthn (SHA-256 tronqué à 16 hex = 64 bits).

Flux :
  POST /api/v1/auth/anon/register/options
    → challenge WebAuthn, user_id aléatoire, pas de modality exposée
  POST /api/v1/auth/anon/register/verify
    → vérifie l'attestation, dérive wallet_name depuis credential_id,
      crée le wallet, retourne adresse + session

Séparation garantie :
  credential WebAuthn (clé de l'OS) ≠ clé du wallet ARTCB (Ed25519)
  wallet_name technique ≠ identité humaine unique
  CERTIFIED_100=false — inchangé
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.api.auth_routes import issue_session
from src.artcb.security.webauthn_cose import public_key_from_cose
from src.artcb.security.webauthn_protocol import (
    WebAuthnError,
    b64u_decode,
    expected_origins,
    pop_pending,
    registration_options,
    rp_id_for_host,
    verify_attestation,
)
from src.artcb.security.webauthn_store import (
    MODALITY_FINGERPRINT,
    save_credential,
)

logger = logging.getLogger("artcb.api.anon_wallet")
audit = logging.getLogger("artcb.api.webauthn.audit")

router = APIRouter(prefix="/api/v1/auth/anon", tags=["auth-anon-wallet"])

# Modality interne fixe — jamais exposée à l'utilisateur
_MODALITY = MODALITY_FINGERPRINT


def _derive_wallet_name(credential_id: str) -> str:
    """Dérive un nom technique déterministe depuis le credential_id WebAuthn.

    credential_id (base64url) → SHA-256 → 16 premiers hex chars → "w-<16hex>"
    Exemple : "w-4a3f8c1d9e2b0f7a"

    Ce n'est pas l'identité humaine — c'est un identifiant de wallet technique.
    CERTIFIED_100=false.
    """
    digest = hashlib.sha256(credential_id.encode("utf-8")).hexdigest()
    return f"w-{digest[:16]}"


def _host_scheme(request: Request) -> tuple[str, str]:
    host = (request.headers.get("host") or request.url.hostname or "localhost").split(",")[0].strip()
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    return host, proto


class AnonRegisterOptionsBody(BaseModel):
    """Corps de la requête /anon/register/options.
    Aucun nom, aucune modality — tout est géré côté serveur.
    """
    create_wallet: bool = True


class CredentialResponse(BaseModel):
    id: str
    rawId: str | None = None
    type: str = "public-key"
    response: dict[str, str]
    authenticatorAttachment: str | None = None
    clientExtensionResults: dict[str, Any] | None = None


class AnonRegisterVerifyBody(BaseModel):
    """Corps de la requête /anon/register/verify.
    Seul le credential WebAuthn est requis.
    """
    credential: CredentialResponse
    create_wallet: bool = True


def _create_wallet_auto(name: str, *, request: Request | None = None) -> dict[str, Any]:
    """Crée le wallet avec un nom dérivé automatiquement.

    Le nom est un identifiant technique (w-<16hex>), pas un nom humain.
    vault = token aléatoire non transmis au client.
    CERTIFIED_100=false — unique_human_proven=false.
    """
    from src.artcb.wallet.manager import WalletManager
    from src.api.auth_routes import device_fingerprint as client_device_fingerprint
    from src.artcb.security.wallet_device_binding import WalletDeviceBindingError

    wm = WalletManager()
    key_path = wm.wallet_dir / f"{name}.key"

    # Idempotent : si le wallet existe déjà (credential réinscrit), on le retourne
    if key_path.exists():
        wallets = wm.list_wallets()
        rec = next((w for w in wallets if w.get("name") == name), None)
        if not rec:
            raise HTTPException(status_code=500, detail="wallet_metadata_missing")
        return {
            "created": False,
            "name": name,
            "address": rec.get("address"),
            "seed_hex": None,
        }

    # Vérification device binding (limite par appareil navigateur)
    if request is not None:
        state = request.app.state.artcb
        client_fp = client_device_fingerprint(request)
        if state.wallet_device_binding and client_fp:
            try:
                state.wallet_device_binding.check_and_bind(
                    wallet_name=name,
                    device_fingerprint=client_fp,
                    env_type="client_ua_device_id_anon",
                )
            except WalletDeviceBindingError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "device_wallet_limit",
                        "message": str(exc),
                        "hint": "Un seul wallet par appareil navigateur. WebAuthn ≠ HumanIdentity unique mondiale.",
                        "unique_human_proven": False,
                    },
                ) from exc

    vault = secrets.token_urlsafe(32)
    wallet = wm.create_wallet(name=name, user_password=vault)
    seed_hex = wallet.signing_key.encode().hex()
    logger.info(
        "Anon wallet created name=%s address=%s hybrid=%s",
        name, wallet.address, wallet.is_hybrid,
    )
    # R361 — restitution complète des clés privées au client.
    # Ed25519 seed (32 octets = 64 hex) + ML-DSA-65 secret (4032 octets = 8064 hex).
    # Les deux doivent être sauvegardées par l'utilisateur pour récupération hybride.
    # Affichées UNE SEULE FOIS — jamais loggées, jamais stockées dans la session.
    # Le serveur conserve les fichiers .key et .pqc chiffrés comme backup opérateur.
    result: dict[str, Any] = {
        "created": True,
        "name": name,
        "address": wallet.address,
        "seed_hex": seed_hex,
        "public_key_hex": wallet.public_key_hex,
        "WARNING": (
            "SAUVEGARDEZ seed_hex ET pqc_secret_key_hex MAINTENANT — "
            "ces clés privées ne seront plus jamais affichées. "
            "Sans elles, la récupération du wallet hybride est impossible "
            "si le serveur est indisponible."
        ),
        "unique_human_proven": False,
    }
    # PQC : clé privée ML-DSA-65 (4032 octets = 8064 hex)
    # Transmise UNE SEULE FOIS — c'est la clé privée post-quantique du wallet.
    if wallet.pqc_secret_key is not None:
        result["pqc_secret_key_hex"] = wallet.pqc_secret_key.hex()
    # Clés publiques + adresse hybride
    if wallet.pqc_public_key_hex:
        result["pqc_public_key_hex"] = wallet.pqc_public_key_hex
    if wallet.address_v2:
        result["address_v2"] = wallet.address_v2
    return result


@router.post("/register/options")
def anon_register_options(body: AnonRegisterOptionsBody, request: Request) -> dict[str, Any]:
    """Démarre la cérémonie WebAuthn sans nom utilisateur.

    - user_id : aléatoire (32 octets), non lié à une identité
    - user_name affiché par l'OS : "wallet ARTCB" (générique)
    - modality : non exposée (MODALITY_FINGERPRINT interne)
    - Retourne le challenge + publicKey WebAuthn standard
    """
    host, _scheme = _host_scheme(request)
    # user_id aléatoire — pas de lien avec un nom existant
    user_id = secrets.token_bytes(32)
    options = registration_options(
        wallet_name="wallet ARTCB",  # affiché par l'OS comme nom de compte
        user_id=user_id,
        host=host,
        modality=_MODALITY,
    )
    return {
        "publicKey": options,
        "create_wallet": body.create_wallet,
        "raw_biometric_never_stored": True,
        "certified": False,
        "note": "R358 — aucun nom fourni par l'utilisateur. Identifiant wallet dérivé du credential après vérification.",
    }


@router.post("/register/verify")
def anon_register_verify(body: AnonRegisterVerifyBody, request: Request) -> dict[str, Any]:
    """Vérifie l'attestation WebAuthn et crée le wallet automatiquement.

    1. Vérifie la signature WebAuthn
    2. Dérive wallet_name = "w-<sha256(credential_id)[:16]>"
    3. Crée le wallet Ed25519 (vault aléatoire, non transmis)
    4. Retourne adresse + session token + seed (une seule fois)

    La clé WebAuthn (credential) ≠ la clé du wallet ARTCB (Ed25519).
    CERTIFIED_100=false. unique_human_proven=false.
    """
    host, scheme = _host_scheme(request)
    rp_id = rp_id_for_host(host)
    origins = expected_origins(host, scheme)

    try:
        client_json = b64u_decode(body.credential.response["clientDataJSON"])
        att_obj = b64u_decode(body.credential.response["attestationObject"])
        client_data = json.loads(client_json.decode("utf-8"))
        challenge = client_data.get("challenge")
        if not isinstance(challenge, str):
            raise WebAuthnError("challenge_missing")
        # pop_pending avec wallet_name=None car on n'a pas de nom à valider
        # On utilise "wallet ARTCB" comme wallet_name d'attente (cohérent avec options)
        pending = pop_pending(challenge, kind="create", wallet_name="wallet ARTCB")
        verified = verify_attestation(
            client_data_json=client_json,
            attestation_object=att_obj,
            challenge_b64=challenge,
            rp_id=pending.get("rp_id") or rp_id,
            origins=origins,
        )
    except (KeyError, ValueError, WebAuthnError) as exc:
        audit.info("biometric event=anon_register_failed client=%s reason=%s",
                   request.client.host if request.client else "?", str(exc))
        raise HTTPException(
            status_code=400,
            detail=str(exc) if str(exc) else "anon_register_failed",
        ) from exc

    # Dériver le nom technique du wallet depuis le credential_id
    credential_id = verified["credential_id"]
    wallet_name = _derive_wallet_name(str(credential_id))

    wallet = _create_wallet_auto(wallet_name, request=request)

    # Sauvegarder le credential WebAuthn lié au wallet dérivé
    save_credential(
        {
            "credential_id": credential_id,
            "cose_b64": verified["cose_b64"],
            "sign_count": verified["sign_count"],
            "wallet_name": wallet_name,
            "address": wallet["address"],
            "modality": _MODALITY,
            "rp_id": verified["rp_id"],
        }
    )

    audit.info(
        "biometric event=anon_register_ok wallet=%s address=%s client=%s created=%s",
        wallet_name,
        wallet["address"],
        request.client.host if request.client else "?",
        wallet["created"],
    )

    session = issue_session(wallet_name=wallet_name, address=str(wallet["address"]))
    out: dict[str, Any] = {
        "ok": True,
        "wallet_name": wallet_name,
        "address": wallet["address"],
        "wallet_created": wallet["created"],
        "raw_biometric_stored": False,
        "unique_human_proven": False,
        "certified": False,
        # Clé publique Ed25519 — à stocker côté navigateur pour vérifications
        "public_key_hex": wallet.get("public_key_hex"),
        **session,
    }
    # PQC : clé publique ML-DSA + adresse hybride
    if wallet.get("pqc_public_key_hex"):
        out["pqc_public_key_hex"] = wallet["pqc_public_key_hex"]
    if wallet.get("address_v2"):
        out["address_v2"] = wallet["address_v2"]
    # R361 — restitution complète : seed Ed25519 + clé privée PQC, affichées UNE SEULE FOIS
    if wallet.get("seed_hex"):
        out["seed_hex"] = wallet["seed_hex"]
        out["WARNING"] = wallet.get("WARNING")
    if wallet.get("pqc_secret_key_hex"):
        out["pqc_secret_key_hex"] = wallet["pqc_secret_key_hex"]
    return out
