"""Routes API confidentialité homomorphe — Phase 14.3.

Endpoints :
    POST /api/v1/privacy/context    — générer un contexte HE (clés)
    POST /api/v1/privacy/encrypt    — chiffrer un vecteur côté client
    POST /api/v1/privacy/aggregate  — agréger des vecteurs chiffrés côté serveur
    GET  /api/v1/privacy/status     — état du module homomorphe

Contrôlé par ARTCB_HOMOMORPHIC_MODE=true/false dans .env
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import os

from fastapi import APIRouter

from src.artcb.privacy.homomorphic import HomomorphicProcessor, HECipherVector

logger = logging.getLogger("artcb.api.privacy")
router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])

_HOMOMORPHIC_MODE = os.getenv("ARTCB_HOMOMORPHIC_MODE", "false").lower() == "true"

try:
    import tenseal as ts  # noqa: F401
    _TENSEAL_AVAILABLE = True
except ImportError:
    _TENSEAL_AVAILABLE = False


# ── Modèles Pydantic inline ────────────────────────────────────────────────
from pydantic import BaseModel


class EncryptRequest(BaseModel):
    vector: list[float]
    participant_id: str | None = None


class EncryptResponse(BaseModel):
    cipher_hex: str
    vector_size: int
    participant_id: str
    mode: str
    homomorphic_active: bool


class AggregateRequest(BaseModel):
    ciphers: list[dict]   # liste de HECipherVector.to_dict()


class AggregateResponse(BaseModel):
    aggregated_cipher: dict
    participant_count: int
    mode: str


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/status")
def privacy_status():
    """État du module homomorphe."""
    return {
        "homomorphic_mode": _HOMOMORPHIC_MODE,
        "tenseal_available": _TENSEAL_AVAILABLE,
        "scheme": "CKKS" if _TENSEAL_AVAILABLE else "simulated",
        "activation": "ARTCB_HOMOMORPHIC_MODE=true dans .env",
        "description": (
            "Chiffrement homomorphe actif — les données restent chiffrées "
            "pendant l'agrégation. Le serveur ne voit jamais les données brutes."
            if _HOMOMORPHIC_MODE else
            "Mode classique — activer avec ARTCB_HOMOMORPHIC_MODE=true"
        ),
    }


@router.post("/context")
def create_he_context(participant_id: str | None = None):
    """Génère un nouveau contexte HE (paire de clés) pour un participant.

    La clé secrète doit être conservée localement par le participant.
    Seul le contexte public est partagé avec le pool.
    """
    proc = HomomorphicProcessor.create(participant_id=participant_id)
    ctx = proc.context
    return {
        "public_context": ctx.to_public_dict(),
        "mode": ctx.mode,
        "homomorphic_active": _HOMOMORPHIC_MODE,
        "warning": (
            "IMPORTANT : La clé secrète n'est pas retournée ici. "
            "Utiliser HomomorphicProcessor.create() côté client pour générer et conserver la clé."
        ),
    }


@router.post("/encrypt", response_model=EncryptResponse)
def encrypt_vector(req: EncryptRequest):
    """Chiffre un vecteur de flottants (vecteur IR PoL).

    Le chiffrement se fait idéalement côté client (les données ne quittent pas
    la machine du participant sous forme brute). Cet endpoint est fourni
    pour les clients qui ne peuvent pas utiliser TenSEAL directement.
    """
    proc = HomomorphicProcessor.create(participant_id=req.participant_id)
    cipher = proc.encrypt(req.vector, participant_id=req.participant_id or "api-client")
    return EncryptResponse(
        cipher_hex=cipher.cipher_bytes.hex(),
        vector_size=cipher.vector_size,
        participant_id=cipher.participant_id,
        mode=cipher.mode,
        homomorphic_active=_HOMOMORPHIC_MODE,
    )


@router.post("/aggregate", response_model=AggregateResponse)
def aggregate_ciphers(req: AggregateRequest):
    """Agrège des vecteurs chiffrés — opération homomorphique côté serveur.

    Le serveur ne déchiffre AUCUN vecteur. Il effectue uniquement
    l'addition homomorphique des ciphertexts. Les données individuelles
    restent strictement privées.
    """
    if len(req.ciphers) < 2:
        from fastapi import HTTPException
        raise HTTPException(400, "Au moins 2 vecteurs chiffrés requis pour l'agrégation")

    ciphers = [HECipherVector.from_dict(c) for c in req.ciphers]
    aggregated = HomomorphicProcessor.aggregate(ciphers)

    return AggregateResponse(
        aggregated_cipher=aggregated.to_dict(),
        participant_count=len(ciphers),
        mode=aggregated.mode,
    )
