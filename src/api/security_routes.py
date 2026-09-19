"""
Routes de sécurité ARTCB — Anti-Sybil métriques + état
=======================================================
Endpoints :
  GET /api/v1/security/anti-sybil/config    — configuration actuelle (bypass, study, limites)
  GET /api/v1/security/anti-sybil/metrics   — métriques usage réel (intervalles, distribution, recommandation)
  POST /api/v1/security/anti-sybil/config   — modifier config à chaud (bypass, study, limite)
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.api_keys_routes import require_scope, verify_api_key

logger = logging.getLogger("artcb.api.security")

router_security = APIRouter(prefix="/api/v1/security", tags=["security"])


def _state(request: Request):
    return request.app.state.artcb


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/security/anti-sybil/config
# ─────────────────────────────────────────────────────────────────────────────

@router_security.get("/anti-sybil/config", summary="Configuration Anti-Sybil actuelle")
def anti_sybil_config(
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    Retourne la configuration Anti-Sybil en cours :
    - Intervalle min (secondes)
    - Mode bypass IA actif
    - Mode study (tout logué, rien rejeté pour rate-limit)
    - Variables d'environnement lues
    """
    state = _state(request)
    sybil = getattr(state.chain, "anti_sybil", None)
    if sybil is None:
        return {"enabled": False, "message": "Anti-Sybil désactivé sur cette instance"}

    return {
        "enabled": True,
        "min_block_interval_s": sybil.min_block_interval.total_seconds(),
        "min_pol_score": sybil.min_pol_score,
        "max_contributors_per_block": sybil.max_contributors_per_block,
        "ai_bypass": sybil.ai_bypass,
        "study_mode": sybil.study_mode,
        "env": {
            "ARTCB_MIN_BLOCK_INTERVAL_SEC": os.getenv("ARTCB_MIN_BLOCK_INTERVAL_SEC", "60"),
            "ARTCB_ANTI_SYBIL_AI_BYPASS": os.getenv("ARTCB_ANTI_SYBIL_AI_BYPASS", "false"),
            "ARTCB_ANTI_SYBIL_STUDY_MODE": os.getenv("ARTCB_ANTI_SYBIL_STUDY_MODE", "false"),
        },
        "active_rules": {
            "pol_minimum": True,
            "max_contributors": True,
            "blacklist": True,
            "rate_limit": not (sybil.ai_bypass or sybil.study_mode),
            "rate_limit_bypassed_for_ai": sybil.ai_bypass,
            "rate_limit_study_mode": sybil.study_mode,
        },
        "note": (
            "MODE BYPASS AI ACTIF — rate-limit désactivé pour blocs IA, "
            "métriques enregistrées pour calibrage futur."
            if sybil.ai_bypass else
            "MODE NORMAL — rate-limit actif. Activer ARTCB_ANTI_SYBIL_AI_BYPASS=true pour bypasser."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/security/anti-sybil/metrics
# ─────────────────────────────────────────────────────────────────────────────

@router_security.get("/anti-sybil/metrics", summary="Métriques usage réel Anti-Sybil — calibrage limite")
def anti_sybil_metrics(
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    Retourne toutes les métriques accumulées depuis le démarrage du serveur :
    - Nombre de tentatives (avec/sans bypass)
    - Distribution des intervalles inter-blocs par adresse
    - Recommandation dynamique de limite (basée sur p5 des intervalles réels)
    - 20 derniers événements détaillés

    Ces données permettent de calibrer la future limite ARTCB_MIN_BLOCK_INTERVAL_SEC
    sur l'usage réel plutôt que sur une hypothèse.

    Usage :
      1. Activer ARTCB_ANTI_SYBIL_AI_BYPASS=true
      2. Utiliser normalement pendant quelques heures/jours
      3. Consulter cet endpoint → recommendation.suggested_limit_s
      4. Appliquer la limite recommandée dans .env
      5. Désactiver le bypass → ARTCB_ANTI_SYBIL_AI_BYPASS=false
    """
    state = _state(request)
    sybil = getattr(state.chain, "anti_sybil", None)
    if sybil is None:
        raise HTTPException(status_code=503, detail="Anti-Sybil désactivé sur cette instance")

    snapshot = sybil.metrics.snapshot()
    snapshot["config"] = {
        "ai_bypass": sybil.ai_bypass,
        "study_mode": sybil.study_mode,
        "current_limit_s": sybil.min_block_interval.total_seconds(),
    }
    snapshot["how_to_use"] = (
        "Laissez tourner en mode bypass pour accumuler des données. "
        "La 'recommendation.suggested_limit_s' se met à jour automatiquement. "
        "Quand sample_count >= 50, la recommandation est statistiquement fiable."
    )
    return snapshot


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/security/anti-sybil/config — modifier à chaud
# ─────────────────────────────────────────────────────────────────────────────

class AntiSybilConfigUpdate(BaseModel):
    ai_bypass: bool | None = Field(default=None, description="Activer/désactiver le bypass IA")
    study_mode: bool | None = Field(default=None, description="Activer/désactiver le mode étude (tout loggué, rien rejeté)")
    min_block_interval_s: int | None = Field(default=None, ge=0, le=3600, description="Nouvelle limite en secondes (0 = désactivé)")


@router_security.post("/anti-sybil/config", summary="Modifier la configuration Anti-Sybil à chaud")
def update_anti_sybil_config(
    body: AntiSybilConfigUpdate,
    request: Request,
    key_record: Annotated[dict | None, Depends(require_scope("write"))] = None,
) -> dict:
    """
    Modifie la configuration Anti-Sybil à chaud, sans redémarrer le serveur.

    Attention : ces changements sont en mémoire uniquement.
    Pour les rendre permanents, mettre à jour .env.
    """
    state = _state(request)
    sybil = getattr(state.chain, "anti_sybil", None)
    if sybil is None:
        raise HTTPException(status_code=503, detail="Anti-Sybil désactivé sur cette instance")

    changes: dict = {}

    if body.ai_bypass is not None:
        sybil.ai_bypass = body.ai_bypass
        changes["ai_bypass"] = body.ai_bypass
        logger.info(
            "Anti-Sybil ai_bypass mis à %s par %s",
            body.ai_bypass,
            key_record["label"] if key_record else "anonymous",
        )

    if body.study_mode is not None:
        sybil.study_mode = body.study_mode
        changes["study_mode"] = body.study_mode
        logger.info(
            "Anti-Sybil study_mode mis à %s par %s",
            body.study_mode,
            key_record["label"] if key_record else "anonymous",
        )

    if body.min_block_interval_s is not None:
        from datetime import timedelta
        sybil.min_block_interval = timedelta(seconds=body.min_block_interval_s)
        changes["min_block_interval_s"] = body.min_block_interval_s
        logger.info(
            "Anti-Sybil min_block_interval mis à %ds par %s",
            body.min_block_interval_s,
            key_record["label"] if key_record else "anonymous",
        )

    if not changes:
        raise HTTPException(status_code=400, detail="Aucune modification fournie")

    return {
        "updated": True,
        "changes": changes,
        "note": "Changements en mémoire uniquement. Mettre à jour .env pour persistance.",
        "new_config": {
            "ai_bypass": sybil.ai_bypass,
            "study_mode": sybil.study_mode,
            "min_block_interval_s": sybil.min_block_interval.total_seconds(),
        },
    }
