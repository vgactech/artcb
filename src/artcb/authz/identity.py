"""Resolve the caller from session / API key / wallet — never from the body.

`actor_address` and `group_id` in a JSON body are claims. They are not
proof. Proof is: a sess_ token, an artcb_ API key bound to a wallet, or
a successfully decrypted wallet file (wallet_name + password).
"""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

from src.artcb.authz.models import Principal

AGENT_HEADER = "x-artcb-agent-id"


def resolve_principal(request: Request, *, required: bool = False) -> Principal:
    authorization = request.headers.get("authorization")
    agent_id = (request.headers.get(AGENT_HEADER) or "").strip() or None

    if not authorization:
        if required:
            raise HTTPException(status_code=401, detail="authentication_required")
        return Principal()

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="bearer_required")
    raw = authorization.removeprefix("Bearer ").strip()

    if raw.startswith("sess_"):
        from src.api.auth_routes import require_session

        record = require_session(request, authorization)
        address = record.get("address") or None
        assurance = record.get("assurance") if isinstance(record.get("assurance"), dict) else None
        unique_human = bool(record.get("unique_human_proven"))
        if agent_id:
            if not address:
                raise HTTPException(status_code=401, detail="agent_requires_human_session")
            return Principal(
                address=address,
                wallet_name=record.get("wallet_name"),
                kind="agent",
                agent_id=agent_id,
                parent_address=address,
                source="session",
                unique_human_proven=False,
                assurance=assurance,
            )
        return Principal(
            address=address,
            wallet_name=record.get("wallet_name"),
            kind="human",
            source="session",
            unique_human_proven=unique_human,
            assurance=assurance,
        )

    if raw.startswith("artcb_"):
        from src.api.api_keys_routes import verify_api_key

        record = verify_api_key(request, authorization)
        if record is None:
            env_key = os.getenv("ARTCB_API_KEY", "").strip()
            if env_key and len(env_key) == len(raw) and hmac.compare_digest(raw, env_key):
                return Principal(kind="operator", source="operator")
            raise HTTPException(status_code=401, detail="invalid_api_key")
        address = record.get("owner_address") or None
        if agent_id:
            return Principal(
                address=address,
                wallet_name=record.get("owner_wallet"),
                kind="agent",
                agent_id=agent_id,
                parent_address=address,
                source="api_key",
            )
        return Principal(
            address=address,
            wallet_name=record.get("owner_wallet"),
            kind="human" if address else "operator",
            source="api_key",
        )

    if required:
        raise HTTPException(status_code=401, detail="unrecognized_bearer")
    return Principal()
