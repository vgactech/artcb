"""R379 — Routes admin WalletDeviceBinding — reset/revoke contrôlé.

⚠️ ACCÈS OPÉRATEUR UNIQUEMENT (require_write_actor).
Ces endpoints sont réservés à :
  - Tests (migration de version, reset environnement test)
  - Récupération d'accès (seed_hex requis côté utilisateur)
  - Debug live sur un nœud autorisé

Ils ne désactivent PAS la protection anti-fraude globale.
Seul le binding de cet appareil/wallet précis est supprimé.

Endpoints :
  GET  /api/v1/admin/device-binding/list
    → Liste tous les bindings PRODUCTION + TEST

  DELETE /api/v1/admin/device-binding/fingerprint/{fingerprint}
    → Supprime le binding PRODUCTION pour ce fingerprint (permet recréation wallet)

  DELETE /api/v1/admin/device-binding/wallet/{wallet_name}
    → Supprime le binding PRODUCTION pour ce wallet_name

  DELETE /api/v1/admin/device-binding/test/wallet/{wallet_name}
    → Supprime le binding TEST pour ce wallet_name

PROTOCOLE ARTCB — mode DEBUG actif — logs WARNING obligatoires sur toute opération.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.api_keys_routes import require_write_actor
from src.artcb.trace.ns import emit, now_mono_ns, now_wall_ns

logger = logging.getLogger("artcb.api.admin_device_binding")

router = APIRouter(prefix="/api/v1/admin/device-binding", tags=["admin", "security"])


def _state(request: Request):
    return request.app.state.artcb


def _binding_store(request: Request):
    state = _state(request)
    store = getattr(state, "wallet_device_binding", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "wallet_device_binding_unavailable",
                "message": "WalletDeviceBindingStore non initialisé sur ce nœud.",
            },
        )
    return store


def _emit_admin_trace(request: Request, action: str, target: str, result: dict) -> None:
    """Trace nanoseconde pour chaque opération admin de binding (audit trail)."""
    state = _state(request)
    data_dir = getattr(getattr(state, "settings", None), "data_dir", None)
    emit(
        data_dir,
        {
            "kind": "admin_device_binding",
            "action": action,
            "target": target,
            "result_ok": result.get("revoked") is not None or result.get("found") is True,
            "ts_wall_ns": now_wall_ns(),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/admin/device-binding/list
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/list",
    summary="[ADMIN] Liste tous les bindings PRODUCTION + TEST",
)
def list_all_bindings(
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
) -> dict:
    """Liste les bindings PRODUCTION et TEST enregistrés.

    ⚠️ Accès opérateur uniquement — contient les fingerprints d'appareils.
    """
    store = _binding_store(request)
    prod = store.list_bindings()
    test = store.list_test_bindings()
    logger.debug("[ADMIN] list_all_bindings: prod=%d test=%d", len(prod), len(test))
    return {
        "production": prod,
        "test": test,
        "prod_count": len(prod),
        "test_count": len(test),
        "certified_100": False,
        "note": "Admin only — fingerprints are device hashes, not biometric data.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/v1/admin/device-binding/fingerprint/{fingerprint}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/fingerprint/{fingerprint}",
    summary="[ADMIN] Supprimer le binding PRODUCTION pour ce fingerprint",
)
def revoke_by_fingerprint(
    fingerprint: str,
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
) -> dict:
    """Supprime le binding PRODUCTION wallet↔appareil pour ce fingerprint.

    Après suppression, l'appareil peut créer un nouveau wallet.
    La protection anti-fraude globale reste active pour tous les autres appareils.
    """
    store = _binding_store(request)
    removed = store.admin_revoke_by_fingerprint(fingerprint)
    _emit_admin_trace(request, "revoke_by_fingerprint", fingerprint[:16], {"revoked": removed})
    if removed is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "binding_not_found",
                "message": f"Aucun binding PRODUCTION pour fingerprint={fingerprint[:16]}…",
            },
        )
    logger.warning("[ADMIN] Binding PRODUCTION supprimé : fingerprint=%s wallet=%s", fingerprint[:16], removed.get("wallet_name"))
    return {
        "ok": True,
        "revoked": removed,
        "message": "Binding PRODUCTION supprimé. L'appareil peut maintenant créer un nouveau wallet.",
        "certified_100": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/v1/admin/device-binding/wallet/{wallet_name}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/wallet/{wallet_name}",
    summary="[ADMIN] Supprimer le binding PRODUCTION pour ce wallet_name",
)
def revoke_by_wallet(
    wallet_name: str,
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
) -> dict:
    """Supprime le binding PRODUCTION pour ce wallet_name."""
    store = _binding_store(request)
    removed = store.admin_revoke_by_wallet(wallet_name)
    _emit_admin_trace(request, "revoke_by_wallet", wallet_name, {"revoked": removed})
    if removed is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "binding_not_found",
                "message": f"Aucun binding PRODUCTION pour wallet_name={wallet_name}",
            },
        )
    logger.warning("[ADMIN] Binding PRODUCTION supprimé : wallet=%s fingerprint=%s", wallet_name, removed.get("device_fingerprint", "?")[:16])
    return {
        "ok": True,
        "revoked": removed,
        "message": "Binding PRODUCTION supprimé. L'appareil peut maintenant créer un nouveau wallet.",
        "certified_100": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/v1/admin/device-binding/test/wallet/{wallet_name}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/test/wallet/{wallet_name}",
    summary="[ADMIN] Supprimer le binding TEST pour ce wallet_name",
)
def revoke_test_by_wallet(
    wallet_name: str,
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
) -> dict:
    """Supprime le binding TEST pour ce wallet_name."""
    store = _binding_store(request)
    removed = store.admin_revoke_test_by_wallet(wallet_name)
    _emit_admin_trace(request, "revoke_test_by_wallet", wallet_name, {"revoked": removed})
    if removed is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "test_binding_not_found",
                "message": f"Aucun binding TEST pour wallet_name={wallet_name}",
            },
        )
    logger.warning("[ADMIN] Binding TEST supprimé : wallet=%s", wallet_name)
    return {
        "ok": True,
        "revoked": removed,
        "message": "Binding TEST supprimé.",
        "certified_100": False,
    }
