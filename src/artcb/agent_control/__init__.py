"""agent_control — Barrière d'exécution partagée Bob/Cursor (R369-enforcement, 2026-09-18).

Ce module fournit le point d'entrée UNIQUE pour l'enforcement du PreflightGate
dans les routes métier sensibles (identity, wallet, chain).

Usage minimal dans une route FastAPI protégée :

    from src.artcb.agent_control import require_operation_authorized

    def my_sensitive_route(...):
        require_operation_authorized("add_device", OperationRisk.CRITICAL)
        # ... logique métier ...

Si le preflight échoue sur une opération CRITICAL/DEPLOY/LIVE_WRITE/CODE_CHANGE,
PreflightBlockedError est levée → FastAPI retourne 503 PREFLIGHT_BLOCKED.

HONNÊTETÉ : Cette Gate est une couche logicielle, pas une primitive système
irréfutable. Elle peut être contournée en appelant directement la logique métier
sans passer par la route FastAPI. L'enforcement complet exige un test de bypass
direct (test T dans test_r369_adversarial.py).
CERTIFIED_100=false.
"""
from src.artcb.agent_control.gate import (
    require_operation_authorized,
    get_gate,
    reset_gate,
    GLOBAL_GATE,
    OperationRisk,
    PreflightBlockedError,
    GateProductionBypassError,
)

__all__ = [
    "require_operation_authorized",
    "get_gate",
    "reset_gate",
    "GLOBAL_GATE",
    "OperationRisk",
    "PreflightBlockedError",
    "GateProductionBypassError",
]
