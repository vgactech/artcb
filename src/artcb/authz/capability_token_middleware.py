"""Middleware / dependency helper for capability token enforcement — R456-integ.

Provides a FastAPI dependency `require_capability_token()` that:
  1. Reads the capability token from the X-Capability-Token header
  2. Validates it against the CapabilityTokenStore (FAIL-CLOSED)
  3. Raises HTTP 403 if denied (unknown, consumed, expired, mismatch)
  4. Returns the RedemptionResult on success

Usage in a FastAPI route:
    from src.artcb.authz.capability_token_middleware import require_capability_token, _GLOBAL_STORE

    @router.post("/domains/{domain_id}/blocks")
    def produce_block(
        domain_id: str,
        request: Request,
        cap: RedemptionResult = Depends(
            require_capability_token(
                capability=CAP_PRODUCE,
                get_node_id=lambda req: req.headers.get("X-Node-Id", ""),
                get_domain_id=lambda req, **kw: kw.get("domain_id", ""),
            )
        ),
    ):
        ...

Design constraints:
  - FAIL-CLOSED: any invalid/missing token → HTTP 403, never silently allowed
  - The global store is a process-level singleton; tests inject a fresh store
  - No dependency on FastAPI request parsing beyond headers
  - unique_human_proven never set here (biometric layer above capability layer)
  - CERTIFIED_100=false
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R456-integ

import logging
from typing import Any, Callable

from fastapi import HTTPException, Request

from src.artcb.authz.capability_token import (
    CapabilityTokenStore,
    RedemptionResult,
    REASON_UNKNOWN_TOKEN,
)

logger = logging.getLogger("artcb.authz.capability_token_middleware")

# ──────────────────────────────────────────────────────────────────────────────
# Global store — process-level singleton
# Tests can swap this with inject_test_store() / reset_store()
# ──────────────────────────────────────────────────────────────────────────────

_GLOBAL_STORE: CapabilityTokenStore = CapabilityTokenStore()

HEADER_CAPABILITY_TOKEN = "X-Capability-Token"
HEADER_NODE_ID = "X-Node-Id"
HEADER_DOMAIN_ID = "X-Domain-Id"


def inject_test_store(store: CapabilityTokenStore) -> None:
    """Replace the global store for testing. Call reset_store() after the test."""
    global _GLOBAL_STORE
    _GLOBAL_STORE = store


def reset_store() -> None:
    """Reset the global store to a fresh empty instance."""
    global _GLOBAL_STORE
    _GLOBAL_STORE = CapabilityTokenStore()


# ──────────────────────────────────────────────────────────────────────────────
# Dependency factory
# ──────────────────────────────────────────────────────────────────────────────

def require_capability_token(
    *,
    capability: str,
    get_node_id: Callable[[Request], str] | None = None,
    get_domain_id: Callable[[Request], str] | None = None,
    store: CapabilityTokenStore | None = None,
) -> Callable[[Request], RedemptionResult]:
    """
    FastAPI dependency factory for capability token enforcement.

    :param capability: Required capability (e.g. CAP_PRODUCE, CAP_VALIDATE)
    :param get_node_id: Optional callable to extract node_id from request
                        (default: reads X-Node-Id header)
    :param get_domain_id: Optional callable to extract domain_id from request
                          (default: reads X-Domain-Id header)
    :param store: Optional store override (useful for tests)

    :raises HTTPException 403: if token is missing, unknown, consumed, expired,
                                or mismatches capability/node/domain.
    :raises HTTPException 400: if required headers are missing.
    :returns: RedemptionResult with allowed=True
    """
    def dependency(request: Request) -> RedemptionResult:
        active_store = store if store is not None else _GLOBAL_STORE

        # Extract token from header
        token_id = (request.headers.get(HEADER_CAPABILITY_TOKEN) or "").strip()
        if not token_id:
            logger.warning(
                "capability_token_missing capability=%s path=%s",
                capability, request.url.path
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "capability_token_missing",
                    "required_header": HEADER_CAPABILITY_TOKEN,
                    "capability": capability,
                },
            )

        # Extract node_id
        if get_node_id is not None:
            node_id = get_node_id(request)
        else:
            node_id = (request.headers.get(HEADER_NODE_ID) or "").strip()

        # Extract domain_id
        if get_domain_id is not None:
            domain_id = get_domain_id(request)
        else:
            domain_id = (request.headers.get(HEADER_DOMAIN_ID) or "").strip()

        if not node_id:
            raise HTTPException(
                status_code=400,
                detail={"error": "node_id_missing", "required_header": HEADER_NODE_ID},
            )
        if not domain_id:
            raise HTTPException(
                status_code=400,
                detail={"error": "domain_id_missing", "required_header": HEADER_DOMAIN_ID},
            )

        # Attempt redemption (FAIL-CLOSED)
        actor = f"{request.client.host if request.client else 'unknown'}:{request.url.path}"
        result = active_store.redeem(
            token_id,
            expected_node_id=node_id,
            expected_domain_id=domain_id,
            expected_capability=capability,
            actor=actor,
        )

        if not result.allowed:
            logger.warning(
                "capability_token_denied token=%s reason=%s capability=%s node=%s",
                token_id[:8] + "...", result.reason, capability, node_id
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "capability_token_denied",
                    "reason": result.reason,
                    "capability": capability,
                    "token_id": token_id[:8] + "...",  # partial only — no full leak
                },
            )

        logger.info(
            "capability_token_consumed token=%s capability=%s node=%s",
            token_id[:8] + "...", capability, node_id
        )
        return result

    return dependency
