"""Capability token API routes — R459 / S09 enforcement proof.

Provides two routes that demonstrate the full capability token lifecycle
in a real API P2P context:

  POST /p2p/cap-tokens/issue
    Operator issues a single-use capability token for a node/domain/capability.
    Requires operator Bearer auth.
    Returns token_id (NOT the full internal token — only the ID is shared).

  POST /p2p/cap-tokens/redeem
    Any caller redeems a token by providing:
      - X-Capability-Token header
      - X-Node-Id header
      - X-Domain-Id header
    FAIL-CLOSED: any invalid token → 403.
    On success, performs the authorized operation stub (extensible).

  GET /p2p/cap-tokens/audit
    Operator reads the audit trail of all token redemption attempts.
    Requires operator Bearer auth.

This module proves S09: security mechanism ENFORCED on a real API route,
not just available as a library function.

CERTIFIED_100=false — this is an API enforcement proof, not production coverage
of all P2P routes.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R459

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.artcb.authz.capability_token import (
    CapabilityTokenStore,
    issue_token,
)
from src.artcb.authz.capability_token_middleware import (
    HEADER_CAPABILITY_TOKEN,
    HEADER_DOMAIN_ID,
    HEADER_NODE_ID,
    RedemptionResult,
    require_capability_token,
)
from src.artcb.authz.node_roles import (
    CAP_HOST,
    CAP_PRODUCE,
    CAP_REPLICATE,
    CAP_VALIDATE,
)

logger = logging.getLogger("artcb.api.capability_token_routes")

router = APIRouter(prefix="/p2p/cap-tokens", tags=["capability-tokens"])

# ──────────────────────────────────────────────────────────────────────────────
# Process-level store — shared across all requests
# Tests can replace this via dependency override
# ──────────────────────────────────────────────────────────────────────────────

_STORE: CapabilityTokenStore = CapabilityTokenStore()

ALLOWED_CAPABILITIES = {CAP_HOST, CAP_REPLICATE, CAP_PRODUCE, CAP_VALIDATE}
ALLOWED_ROLES = {"HOST_ONLY", "REPLICA", "CONSENSUS", "GOVERNANCE"}


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class IssueTokenRequest(BaseModel):
    node_id: str
    domain_id: str
    capability: str
    role: str
    valid_until: str | None = None


class IssueTokenResponse(BaseModel):
    token_id: str
    node_id: str
    domain_id: str
    capability: str
    role: str
    issued_at: str
    valid_until: str | None


class RedeemOperationRequest(BaseModel):
    """Body for a capability-guarded operation stub."""
    operation_context: dict[str, Any] = {}


class RedeemOperationResponse(BaseModel):
    authorized: bool
    token_id: str
    node_id: str
    domain_id: str
    capability: str
    redeemed_at: str
    operation_result: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────────────

def _get_store() -> CapabilityTokenStore:
    """Dependency: returns the process-level store. Tests can override."""
    return _STORE


def _require_operator(request: Request) -> None:
    """Minimal operator auth: requires Bearer token in Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "operator_auth_required", "hint": "Authorization: Bearer <token>"},
        )
    # In production: verify the Bearer token against the operator wallet.
    # Here we verify it is non-empty after "Bearer ".
    token = auth[len("Bearer "):].strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"error": "operator_bearer_empty"},
        )


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/issue",
    summary="Émettre un capability token usage unique (opérateur)",
    response_model=IssueTokenResponse,
)
def issue_capability_token(
    body: IssueTokenRequest,
    request: Request,
    store: CapabilityTokenStore = Depends(_get_store),
    _auth: None = Depends(_require_operator),
) -> IssueTokenResponse:
    """
    Operator issues a single-use capability token for a node.

    FAIL-CLOSED: unknown role or capability → 422.
    """
    if body.capability not in ALLOWED_CAPABILITIES:
        raise HTTPException(
            status_code=422,
            detail={"error": "capability_not_allowed", "allowed": sorted(ALLOWED_CAPABILITIES)},
        )
    if body.role.upper() not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=422,
            detail={"error": "role_not_allowed", "allowed": sorted(ALLOWED_ROLES)},
        )
    try:
        tok = issue_token(
            node_id=body.node_id,
            domain_id=body.domain_id,
            capability=body.capability,
            role=body.role.upper(),
            valid_until=body.valid_until,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc

    store.register(tok)
    logger.info(
        "cap_token_issued node=%s domain=%s cap=%s token=%s",
        body.node_id, body.domain_id, body.capability, tok.token_id[:8] + "..."
    )
    return IssueTokenResponse(
        token_id=tok.token_id,
        node_id=tok.node_id,
        domain_id=tok.domain_id,
        capability=tok.capability,
        role=tok.role,
        issued_at=tok.issued_at,
        valid_until=tok.valid_until,
    )


def _redeem_with_store(
    capability: str,
    request: Request,
    store: CapabilityTokenStore,
) -> RedemptionResult:
    """Internal: validate and consume a token using the injected store."""
    return require_capability_token(
        capability=capability,
        store=store,
    )(request)


@router.post(
    "/redeem/produce-block",
    summary="Exécuter une opération CAP_PRODUCE après validation du token (S09 enforcement)",
    response_model=RedeemOperationResponse,
)
def redeem_produce_block(
    body: RedeemOperationRequest,
    request: Request,
    store: CapabilityTokenStore = Depends(_get_store),
) -> RedeemOperationResponse:
    """
    S09 enforcement proof: this route requires a valid single-use CAP_PRODUCE token.

    FAIL-CLOSED: any invalid/missing token → 403 before the operation runs.
    Only after successful token consumption does the route execute its operation.
    """
    # Validate + consume token FAIL-CLOSED using the injected store
    redemption = _redeem_with_store(CAP_PRODUCE, request, store)

    node_id = request.headers.get(HEADER_NODE_ID, "")
    operation_result = {
        "stub": True,
        "description": "CAP_PRODUCE token validated — block production authorized",
        "node_id": node_id,
        "context": body.operation_context,
        "note": "Production: replace this stub with actual block production logic",
    }
    logger.info(
        "cap_produce_authorized token=%s node=%s",
        redemption.token_id[:8] + "...", node_id
    )
    return RedeemOperationResponse(
        authorized=True,
        token_id=redemption.token_id,
        node_id=node_id,
        domain_id=request.headers.get(HEADER_DOMAIN_ID, ""),
        capability=CAP_PRODUCE,
        redeemed_at=redemption.redeemed_at or datetime.now(UTC).isoformat(),
        operation_result=operation_result,
    )


@router.post(
    "/redeem/replicate",
    summary="Exécuter une opération CAP_REPLICATE après validation du token (S09 enforcement)",
    response_model=RedeemOperationResponse,
)
def redeem_replicate(
    body: RedeemOperationRequest,
    request: Request,
    store: CapabilityTokenStore = Depends(_get_store),
) -> RedeemOperationResponse:
    """
    S09 enforcement proof: requires CAP_REPLICATE single-use token.
    Corresponds to the /replica/push route protection pattern.
    """
    redemption = _redeem_with_store(CAP_REPLICATE, request, store)

    node_id = request.headers.get(HEADER_NODE_ID, "")
    operation_result = {
        "stub": True,
        "description": "CAP_REPLICATE token validated — block replication authorized",
        "node_id": node_id,
        "context": body.operation_context,
    }
    return RedeemOperationResponse(
        authorized=True,
        token_id=redemption.token_id,
        node_id=node_id,
        domain_id=request.headers.get(HEADER_DOMAIN_ID, ""),
        capability=CAP_REPLICATE,
        redeemed_at=redemption.redeemed_at or datetime.now(UTC).isoformat(),
        operation_result=operation_result,
    )


@router.get(
    "/audit",
    summary="Lire l'audit trail des rédemptions de tokens (opérateur)",
)
def get_audit_trail(
    request: Request,
    store: CapabilityTokenStore = Depends(_get_store),
    _auth: None = Depends(_require_operator),
    token_id: str | None = None,
) -> dict[str, Any]:
    """
    Read capability token redemption audit trail.
    Operator only. Filtered by token_id if provided.
    The trail is append-only — never erased.
    """
    trail = store.get_audit_trail(token_id)
    counts = store.count_by_state()
    return {
        "audit_trail": trail,
        "total_entries": len(trail),
        "token_counts": counts,
        "filter_token_id": token_id,
    }


@router.get(
    "/health",
    summary="Vérifier que le capability token store est opérationnel",
)
def cap_token_health(
    store: CapabilityTokenStore = Depends(_get_store),
) -> dict[str, Any]:
    """Public health check — does not expose token data."""
    counts = store.count_by_state()
    return {
        "store_operational": True,
        "pending": counts.get("PENDING", 0),
        "consumed": counts.get("CONSUMED", 0),
        "expired": counts.get("EXPIRED", 0),
        "certified_100": False,
        "note": "S09 enforcement proof — see /redeem/produce-block and /redeem/replicate",
    }
