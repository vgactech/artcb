"""PreflightGate partagée — module d'enforcement central (R369/R370, 2026-09-18).

Ce fichier expose une Gate singleton utilisée par :
  - les routes FastAPI sensibles (identity_device_routes, routes.py, chain)
  - les hooks Bob IDE (user_prompt_submit.py)
  - les tests adversariaux (test_r369_adversarial.py)

## Règle fondamentale (R369-enforcement)

Toute opération classifiée CRITICAL, DEPLOY, LIVE_WRITE ou CODE_CHANGE
DOIT appeler require_operation_authorized() avant de modifier l'état.

Si le preflight échoue (BLOCKED) → PreflightBlockedError levée.
FastAPI transforme PreflightBlockedError en HTTP 503 via l'exception handler.

## ARTCB_PREFLIGHT_GATE_DISABLED — règle de sécurité R370

Cette variable d'environnement est RÉSERVÉE aux tests unitaires isolés.
En production (ARTCB_ENV=production ou NODE_ENV=production), la Gate NE PEUT PAS
être désactivée. Toute tentative lève GateProductionBypassError au démarrage.

## Limite documentée (honnêteté)

La Gate est un enforcement LOGICIEL au niveau Python.
Un appel à `ChainManager.append_block()` ou `WalletManager.create_wallet()`
depuis un worker interne (mining, bridge, memory) passe par la Gate
car celle-ci est intégrée dans append_block() lui-même (R369).
Bypass restant : modifier directement `blocks.jsonl` sans passer par append_block
→ non couvert par cette Gate (couche OS, hors portée Python).
CERTIFIED_100=false.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

_log = logging.getLogger("artcb.agent_control.gate")

from src.artcb.reflex.preflight import (
    PreflightBlockedError,
    PreflightEngine,
    PreflightGate,
    PreflightMode,
    OperationRisk,
    required_preflight_mode,
)

# ─── Gate singleton (partagée Bob + Cursor + FastAPI) ─────────────────────────

_gate_lock = threading.Lock()
_gate_instance: Optional[PreflightGate] = None


class GateProductionBypassError(RuntimeError):
    """Levée si ARTCB_PREFLIGHT_GATE_DISABLED=1 est tenté en production (R370).

    Cette erreur provoque l'arrêt du démarrage de l'application.
    Elle ne peut jamais être interceptée silencieusement en production.
    """


def _is_production() -> bool:
    """Retourne True si l'environnement est la production."""
    return os.environ.get("ARTCB_ENV", "").lower() in ("production", "prod") or \
        os.environ.get("NODE_ENV", "").lower() in ("production", "prod")


def _check_gate_disabled() -> bool:
    """Vérifie ARTCB_PREFLIGHT_GATE_DISABLED.

    En production, lève GateProductionBypassError si la Gate est désactivée.
    En test/dev, retourne True (skip silencieux autorisé).

    Returns:
        True si la Gate est désactivée (jamais True en production).

    Raises:
        GateProductionBypassError: si tenté en production.
    """
    disabled = os.environ.get("ARTCB_PREFLIGHT_GATE_DISABLED", "").lower() in (
        "1", "true", "yes"
    )
    if disabled and _is_production():
        raise GateProductionBypassError(
            "ARTCB_PREFLIGHT_GATE_DISABLED=1 est interdit en production (R370). "
            "Retirer cette variable d'environnement et redémarrer le nœud."
        )
    if disabled:
        _log.warning(
            "ARTCB_PREFLIGHT_GATE_DISABLED=1 actif — Gate désactivée. "
            "RÉSERVÉ AUX TESTS UNIQUEMENT. Jamais en production."
        )
    return disabled


# Évalué au chargement du module — lève GateProductionBypassError en production
_GATE_DISABLED: bool = _check_gate_disabled()


def get_gate() -> PreflightGate:
    """Retourne la Gate singleton thread-safe."""
    global _gate_instance
    if _gate_instance is None:
        with _gate_lock:
            if _gate_instance is None:
                _gate_instance = PreflightGate(PreflightEngine())
    return _gate_instance


def reset_gate() -> None:
    """Réinitialise la Gate (tests uniquement)."""
    global _gate_instance
    with _gate_lock:
        _gate_instance = None


# ─── Point d'entrée principal ─────────────────────────────────────────────────


def require_operation_authorized(
    operation: str,
    risk: OperationRisk = OperationRisk.CRITICAL,
    task_id: str = "unknown",
    *,
    do_fetch: bool = False,
) -> None:
    """Vérifie que l'opération est autorisée par le PreflightGate.

    À appeler AU DÉBUT de toute opération protégée avant toute modification d'état.

    Args:
        operation:  Nom de l'opération (ex : "add_device", "wallet_create", "append_block")
        risk:       Classification du risque (par défaut CRITICAL pour les opérations sensibles)
        task_id:    Identifiant de la tâche courante (pour traçabilité)
        do_fetch:   Si True, exécute git fetch avant la vérification remote

    Raises:
        PreflightBlockedError: Si preflight BLOCKED et risque fail-closed.

    Note:
        Si ARTCB_PREFLIGHT_GATE_DISABLED=1 (tests), skip silencieux.
        En production, jamais désactiver.
    """
    if _GATE_DISABLED:
        return

    gate = get_gate()

    # DEPLOY et CRITICAL font automatiquement fetch_remote
    auto_fetch = do_fetch or risk in (OperationRisk.DEPLOY, OperationRisk.CRITICAL)

    # Exécuter preflight avec le mode déterminé par le risque
    mode = required_preflight_mode(risk)
    result = gate._engine.run_checks(
        task_id=task_id,
        mode=mode,
        operation_risk=risk,
        do_fetch=auto_fetch,
    )

    auth = gate.authorize(
        operation=operation,
        risk=risk,
        task_id=task_id,
        preflight_result=result,
    )
    gate.require_authorized(auth)


# ─── Instance globale pour import direct ──────────────────────────────────────

GLOBAL_GATE = get_gate


# ─── Re-exports pratiques ─────────────────────────────────────────────────────

__all__ = [
    "require_operation_authorized",
    "get_gate",
    "reset_gate",
    "GLOBAL_GATE",
    "OperationRisk",
    "PreflightBlockedError",
    "PreflightGate",
    "PreflightEngine",
]
