"""Routes API — Réflexe ARTCB (R350–R354, R368-R370, R369-enforcement, 2026-09-18).

Expose l'état complet du moteur réflexe + PreflightGate :
  GET  /api/v1/reflex/status       → rapport ReflexEngine + PreflightGate + R369 enforcement
  POST /api/v1/reflex/check        → vérifier un texte/fichier vs le moteur
  GET  /api/v1/reflex/preflight    → rapport préflight brut (git + live + ledger)
  GET  /api/v1/reflex/priorities   → table des priorités
"""
from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from src.artcb.reflex.core import get_reflex_engine, ReflexPriority

router = APIRouter(prefix="/api/v1/reflex", tags=["reflex"])


class ReflexCheckRequest(BaseModel):
    text: str = ""
    files: list[str] = []


@router.get("/status", summary="État complet réflexe + PreflightGate ARTCB (R350–R370)")
def reflex_status() -> dict:
    """Retourne le rapport complet du ReflexEngine + PreflightGate ARTCB.

    Inclut l'état R369-enforcement : quelles routes sont protégées par la Gate.
    CERTIFIED_100=false.
    """
    engine = get_reflex_engine()
    reflex_report = engine.report()

    # ── R369-enforcement : état de la Gate ──────────────────────────────────
    try:
        from src.artcb.agent_control import get_gate
        from src.artcb.reflex.preflight import PreflightMode
        gate = get_gate()
        preflight_result = gate._engine.run_checks(
            task_id="reflex_status_probe",
            mode=PreflightMode.LITE,
        )

        def _sval(x):
            """Sérialise enum ou dataclass en string propre pour JSON."""
            if hasattr(x, "value"):
                return x.value
            if hasattr(x, "__dataclass_fields__"):
                return {k: _sval(getattr(x, k)) for k in x.__dataclass_fields__}
            return str(x)

        gate_state = {
            "gate_active": True,
            "preflight_status": _sval(preflight_result.overall_status),
            "git_state": _sval(preflight_result.git),
            "live_state": _sval(preflight_result.live),
            "ledger_state": _sval(preflight_result.ledger),
        }
    except Exception as exc:
        gate_state = {"gate_active": False, "error": str(exc)}

    # ── R369 : liste des routes protégées ───────────────────────────────────
    r369_enforcement = {
        "routes_protected": [
            {
                "route": "POST /api/v1/identity/device/add-verify",
                "risk": "CRITICAL",
                "status": "ACTIVE ✅",
            },
            {
                "route": "DELETE /api/v1/identity/device/revoke",
                "risk": "CRITICAL",
                "status": "ACTIVE ✅",
            },
            {
                "route": "POST /api/v1/wallet/create",
                "risk": "CRITICAL",
                "status": "ACTIVE ✅",
            },
            {
                "route": "chain.append_block() (interne)",
                "risk": "LIVE_WRITE",
                "status": "ACTIVE ✅ (skip si dry_run=True)",
            },
        ],
        "certified_100": False,
        "note": (
            "Enforcement logiciel via FastAPI routes. "
            "Un appel Python direct sans passer par les routes contourne la Gate. "
            "CERTIFIED_100=false."
        ),
    }

    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "reflex_engine": reflex_report,
        "preflight_gate": gate_state,
        "r369_enforcement": r369_enforcement,
        "rules": "R350–R354 + R368–R370 + R369-enforcement (2026-09-18)",
        "certified_100": False,
    }


@router.post("/check", summary="Vérifier un texte/fichier contre le réflexe ARTCB")
def reflex_check(body: ReflexCheckRequest) -> dict:
    """Analyse un texte et des fichiers pour détecter les déclencheurs réflexes.

    Retourne la priorité détectée et les triggers correspondants.
    CERTIFIED_100=false.
    """
    engine = get_reflex_engine()
    result = engine.activate(text=body.text, files=body.files)
    return result


@router.get("/preflight", summary="Rapport préflight brut (git + live + ledger) R368-R370")
def reflex_preflight() -> dict:
    """Rapport préflight brut : git_state, live_state, ledger_state, bloquants actifs.

    Utilise PreflightMode.LITE (pas de réseau, rapide, safe pour le UI).
    CERTIFIED_100=false.
    """
    try:
        from src.artcb.agent_control import get_gate
        from src.artcb.reflex.preflight import PreflightMode
        gate = get_gate()
        result = gate._engine.run_checks(
            task_id="preflight_probe",
            mode=PreflightMode.LITE,
        )

        def _val(x):
            """Sérialise enum ou dataclass en string propre pour JSON."""
            if hasattr(x, "value"):
                return x.value
            if hasattr(x, "__dataclass_fields__"):
                return {k: _val(getattr(x, k)) for k in x.__dataclass_fields__}
            return str(x)

        return {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": _val(result.overall_status),
            "git_state": _val(result.git),
            "live_state": _val(result.live),
            "ledger_state": _val(result.ledger),
            "remote_sync": _val(result.remote_sync) if hasattr(result, "remote_sync") else "unknown",
            "summary": result.summary_lines if hasattr(result, "summary_lines") else [],
            "context_sha": result.context_sha if hasattr(result, "context_sha") else None,
            "certified_100": False,
        }
    except Exception as exc:
        return {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "ERROR",
            "error": str(exc),
            "certified_100": False,
        }


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
