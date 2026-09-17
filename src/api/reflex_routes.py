"""Routes API — Réflexe ARTCB (R350–R354, 2026-09-17).

Expose l'état du moteur réflexe :
  GET  /api/v1/reflex/status       → rapport complet du ReflexEngine
  POST /api/v1/reflex/check        → vérifier un texte/fichier vs le moteur
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from src.artcb.reflex.core import get_reflex_engine, ReflexPriority

router = APIRouter(prefix="/api/v1/reflex", tags=["reflex"])


class ReflexCheckRequest(BaseModel):
    text: str = ""
    files: list[str] = []


@router.get("/status", summary="État du moteur réflexe ARTCB (R350–R354)")
def reflex_status() -> dict:
    """Retourne le rapport complet du ReflexEngine ARTCB.

    CERTIFIED_100=false — stub fonctionnel.
    Activé via hooks Bob IDE et Cursor.
    """
    engine = get_reflex_engine()
    return engine.report()


@router.post("/check", summary="Vérifier un texte/fichier contre le réflexe ARTCB")
def reflex_check(body: ReflexCheckRequest) -> dict:
    """Analyse un texte et des fichiers pour détecter les déclencheurs réflexes.

    Retourne la priorité détectée et les triggers correspondants.
    CERTIFIED_100=false.
    """
    engine = get_reflex_engine()
    result = engine.activate(text=body.text, files=body.files)
    return result


@router.get("/priorities", summary="Table des priorités réflexes ARTCB")
def reflex_priorities() -> dict:
    """Retourne la table des niveaux de priorité du réflexe ARTCB."""
    return {
        "priorities": {
            p.name: {
                "value": int(p),
                "description": _PRIORITY_DESCRIPTIONS[p],
            }
            for p in ReflexPriority
        },
        "rules": "R350–R354 (2026-09-17)",
        "certified_100": False,
    }


_PRIORITY_DESCRIPTIONS = {
    ReflexPriority.REFLEX_MEMORY: (
        "PRIORITÉ ABSOLUE — Mémoire IA / thinking / raisonnement. "
        "Chantier prioritaire avant tout autre travail."
    ),
    ReflexPriority.SECURITY: (
        "PRIORITÉ 1 — Sécurité biométrique / identité humaine / WebAuthn / ADD_DEVICE."
    ),
    ReflexPriority.PQC: (
        "PRIORITÉ 2 — Certification post-quantique (ML-DSA-65, VPQC2, Kyber)."
    ),
    ReflexPriority.OTHER: (
        "Priorité standard — aucun réflexe critique détecté."
    ),
}
