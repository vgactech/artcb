"""R379/R431 — Routes admin WalletDeviceBinding — reset/revoke contrôlé.

⚠️ ACCÈS OPÉRATEUR UNIQUEMENT (require_write_actor).
Ces endpoints sont réservés à :
  - Tests (migration de version, reset environnement test)
  - Récupération d'accès (seed_hex requis côté utilisateur)
  - Debug live sur un nœud autorisé

Ils ne désactivent PAS la protection anti-fraude globale.
Seul le binding de cet appareil/wallet précis est affecté.

Endpoints :
  GET  /api/v1/admin/device-binding/list
    → Liste tous les bindings PRODUCTION + TEST (ACTIVE + REVOKED)

  GET  /api/v1/admin/device-binding/list-active
    → Liste uniquement les bindings ACTIVE (R431)

  GET  /api/v1/admin/device-binding/list-revoked
    → Liste uniquement les bindings REVOKED (R431)

  POST /api/v1/admin/device-binding/revoke
    → Révocation avec historique conservé (R431) — état ACTIVE → REVOKED

  DELETE /api/v1/admin/device-binding/fingerprint/{fingerprint}
    → [R379 — DEPRECATED] Supprime physiquement le binding PRODUCTION pour ce fingerprint

  DELETE /api/v1/admin/device-binding/wallet/{wallet_name}
    → [R379 — DEPRECATED] Supprime physiquement le binding PRODUCTION pour ce wallet_name

  DELETE /api/v1/admin/device-binding/test/wallet/{wallet_name}
    → [R379 — DEPRECATED] Supprime physiquement le binding TEST pour ce wallet_name

PROTOCOLE ARTCB — mode DEBUG actif — logs WARNING obligatoires sur toute opération.
"""

from __future__ import annotations
MODULE_VERSION = '1.2.1'  # R432 — actor authentifié + purge séparé

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from src.api.api_keys_routes import require_write_actor
from src.artcb.security.wallet_device_binding import (
    BindingPurgeError,
    BindingRevocationError,
)
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


def _extract_authenticated_actor(actor_dict: dict | None) -> str:
    """Extrait l'identité vérifiée de require_write_actor (R432).

    L'identité retournée provient exclusivement du mécanisme d'authentification
    serveur (Bearer token vérifié) — jamais du body HTTP client.
    Ordre de priorité : wallet_name → label → address → kind → 'operator'.
    """
    if actor_dict is None:
        return "anonymous"
    return (
        actor_dict.get("wallet_name")
        or actor_dict.get("label")
        or actor_dict.get("address")
        or actor_dict.get("kind")
        or "operator"
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
# GET /api/v1/admin/device-binding/list-active  (R431)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/list-active",
    summary="[ADMIN R431] Liste les bindings ACTIVE uniquement",
)
def list_active_bindings(
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
) -> dict:
    """Liste les bindings PRODUCTION + TEST dont l'état est ACTIVE (R431)."""
    store = _binding_store(request)
    prod = store.list_active_bindings(namespace="PRODUCTION")
    test = store.list_active_bindings(namespace="TEST")
    logger.debug("[ADMIN R431] list_active_bindings: prod=%d test=%d", len(prod), len(test))
    return {
        "production": prod, "test": test,
        "prod_count": len(prod), "test_count": len(test),
        "filter": "ACTIVE", "certified_100": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/admin/device-binding/list-revoked  (R431)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/list-revoked",
    summary="[ADMIN R431] Liste les bindings REVOKED uniquement (audit trail)",
)
def list_revoked_bindings(
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
) -> dict:
    """Liste les bindings PRODUCTION + TEST dont l'état est REVOKED (R431)."""
    store = _binding_store(request)
    prod = store.list_revoked_bindings(namespace="PRODUCTION")
    test = store.list_revoked_bindings(namespace="TEST")
    logger.debug("[ADMIN R431] list_revoked_bindings: prod=%d test=%d", len(prod), len(test))
    return {
        "production": prod, "test": test,
        "prod_count": len(prod), "test_count": len(test),
        "filter": "REVOKED", "certified_100": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/admin/device-binding/revoke  (R431/R432)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/revoke",
    summary="[ADMIN R432] Révoquer un binding avec historique conservé (ACTIVE → REVOKED)",
)
def revoke_with_history(
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
    wallet_name: str | None = Body(default=None, description="Nom du wallet"),
    device_fingerprint: str | None = Body(default=None, description="Fingerprint device"),
    binding_id: str | None = Body(default=None, description="UUID binding (prioritaire)"),
    reason: str = Body(default="", description="Raison de la révocation"),
    requested_actor: str | None = Body(default=None, description="Identité fournie par le client (informative)"),
    namespace: str = Body(default="PRODUCTION", description="PRODUCTION ou TEST"),
    expected_version: int | None = Body(default=None, description="Version CAS attendue (optionnelle)"),
) -> dict:
    """Révoque un binding wallet↔device avec historique conservé (R432).

    NE SUPPRIME PAS l'enregistrement — change l'état ACTIVE → REVOKED.
    L'identité de l'opérateur (revocation_actor) provient du token Bearer authentifié,
    jamais du body. Le champ requested_actor du body est informatif uniquement.
    Double révocation → HTTP 409. Binding introuvable → HTTP 404.
    Conflit de version CAS → HTTP 409.
    """
    store = _binding_store(request)
    # R432 : identité forensic = token vérifié par le serveur, pas le body client
    authenticated_actor = _extract_authenticated_actor(_actor)
    try:
        result = store.revoke_with_history(
            wallet_name=wallet_name,
            device_fingerprint=device_fingerprint,
            binding_id=binding_id,
            reason=reason,
            authenticated_actor=authenticated_actor,
            requested_actor=requested_actor,
            namespace=namespace,
            expected_version=expected_version,
        )
    except BindingRevocationError as exc:
        err_msg = str(exc)
        status = 409 if ("déjà révoqué" in err_msg or "Conflit de version" in err_msg) else 404
        code = (
            "binding_already_revoked" if "déjà révoqué" in err_msg
            else "binding_version_conflict" if "Conflit de version" in err_msg
            else "binding_not_found_or_invalid"
        )
        raise HTTPException(status_code=status, detail={"code": code, "message": err_msg})

    _emit_admin_trace(
        request,
        "revoke_with_history",
        str(wallet_name or device_fingerprint or binding_id or "?"),
        {"revoked": result},
    )
    logger.warning(
        "[ADMIN R432] REVOKE_WITH_HISTORY binding_id=%s wallet=%s "
        "authenticated_actor=%s requested_actor=%s reason=%s v%s→v%s",
        result.get("binding_id"),
        result.get("new_state", {}).get("wallet_name"),
        authenticated_actor,
        requested_actor or "<none>",
        reason or "<none>",
        result.get("version_before"),
        result.get("version_after"),
    )
    return {
        "ok": True,
        "binding_id": result.get("binding_id"),
        "revoked_at": result.get("revoked_at"),
        "version_before": result.get("version_before"),
        "version_after": result.get("version_after"),
        "previous_state": result.get("previous_state"),
        "new_state": result.get("new_state"),
        "message": "Binding révoqué avec historique conservé (REVOKED, enregistrement intact).",
        "certified_100": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/admin/device-binding/purge  (R432)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/purge",
    summary="[ADMIN R432] Purge physique d'un binding REVOKED (chemin exceptionnel, journalisé)",
)
def purge_binding(
    request: Request,
    _actor: Annotated[dict, Depends(require_write_actor)],
    binding_id: str = Body(..., description="UUID du binding REVOKED à purger (obligatoire)"),
    purge_reason: str = Body(..., description="Motif de la purge (obligatoire)"),
    namespace: str = Body(default="PRODUCTION", description="PRODUCTION ou TEST"),
) -> dict:
    """Purge physique d'un binding REVOKED (R432).

    Distinct de la révocation : supprime physiquement l'enregistrement
    après avoir écrit un journal forensic immuable dans binding_purge_log.json.

    Règles :
      - Seuls les bindings REVOKED peuvent être purgés.
      - Un binding ACTIVE est rejeté (HTTP 409) — révoquer d'abord.
      - L'identité forensic provient du token Bearer authentifié.
      - purge_reason est obligatoire.
    """
    store = _binding_store(request)
    authenticated_actor = _extract_authenticated_actor(_actor)
    try:
        result = store.purge_binding(
            binding_id=binding_id,
            authenticated_actor=authenticated_actor,
            purge_reason=purge_reason,
            namespace=namespace,
        )
    except BindingPurgeError as exc:
        err_msg = str(exc)
        status = 409 if "REVOKED" in err_msg or "obligatoire" in err_msg else 404
        code = (
            "binding_not_revoked" if "REVOKED" in err_msg
            else "purge_params_missing" if "obligatoire" in err_msg
            else "binding_not_found"
        )
        raise HTTPException(status_code=status, detail={"code": code, "message": err_msg})

    _emit_admin_trace(request, "purge_binding", binding_id, {"revoked": result})
    logger.warning(
        "[ADMIN R432] PURGE_PHYSICAL binding_id=%s namespace=%s "
        "authenticated_actor=%s purge_id=%s reason=%s",
        binding_id, namespace, authenticated_actor,
        result.get("purge_id"), purge_reason,
    )
    return {
        "ok": True,
        "purge_id": result.get("purge_id"),
        "binding_id": binding_id,
        "purged_at": result.get("purged_at"),
        "authenticated_actor": authenticated_actor,
        "snapshot": result.get("snapshot"),
        "message": "Binding purgé physiquement. Journal forensic enregistré dans binding_purge_log.json.",
        "certified_100": False,
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
