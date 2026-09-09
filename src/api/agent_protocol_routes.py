"""R268 — ARTCB Agent Memory Protocol HTTP.

GET  /api/v1/agent/bootstrap
POST /api/v1/agent/register
POST /api/v1/agent/events   (idempotent client_event_id)
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.api_keys_routes import require_write_actor
from src.artcb.agent_runtime import AgentRuntime, MEMORY_CAPABILITIES, PROTOCOL_VERSION

router = APIRouter(prefix="/api/v1/agent", tags=["agent-protocol"])


def _runtime(request: Request) -> AgentRuntime:
    state = request.app.state.artcb
    existing = getattr(state, "agent_runtime", None)
    if existing is None:
        existing = AgentRuntime(state.settings.data_dir)
        state.agent_runtime = existing
    return existing


class RegisterBody(BaseModel):
    provider: str = Field(default="generic", max_length=64)
    label: str = Field(min_length=1, max_length=128)
    capabilities: list[str] = Field(default_factory=lambda: ["memory:read", "memory:write", "memo:write"])
    agent_id: str | None = Field(default=None, max_length=64)


class EventBody(BaseModel):
    event_id: str = Field(min_length=8, max_length=128)
    kind: str = Field(default="observation", max_length=32)
    content: str = Field(min_length=1, description="Mémoire agent. Aucune limite de caractères.")
    visibility: str = Field(default="public", max_length=16)
    tags: list[str] = Field(default_factory=list)
    session_id: str = Field(default="agent-event", max_length=64)


@router.get("/bootstrap")
def agent_bootstrap(
    request: Request,
    key_record: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    rt = _runtime(request)
    health = {}
    try:
        chain = request.app.state.artcb.chain
        health = {
            "height": chain.height() if hasattr(chain, "height") else None,
            "last_hash": chain.last_hash() if hasattr(chain, "last_hash") else None,
        }
    except Exception:
        health = {}
    snap = rt.bootstrap(key_record, protocol_http=health)
    snap["memory_api"] = {
        "context": "/api/v1/ai/context",
        "memory": "/api/v1/ai/memory",
        "memo": "/api/v1/ai/memo",
        "events": "/api/v1/agent/events",
    }
    snap["mcp"] = {"module": "src.artcb.mcp.server", "tools": ["artcb_agent_bootstrap", "artcb_memory_event", "artcb_memo"]}
    return snap


@router.post("/register")
def agent_register(
    body: RegisterBody,
    request: Request,
    key_record: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    rt = _runtime(request)
    rec = key_record or {}
    unknown = [c for c in body.capabilities if c not in MEMORY_CAPABILITIES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown_capabilities:{unknown}")
    try:
        row = rt.register_agent(
            provider=body.provider,
            label=body.label,
            owner_address=rec.get("address") or rec.get("owner_address"),
            capabilities=body.capabilities,
            agent_id=body.agent_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "protocol": PROTOCOL_VERSION, "agent": row}


@router.post("/events")
def agent_event(
    body: EventBody,
    request: Request,
    key_record: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    """Idempotent memory write. Same event_id returns already_committed."""
    from src.api.ai_routes import MemoRequest, ai_memo

    rt = _runtime(request)
    rec = key_record or {}
    agent_id = str(rec.get("agent_id") or rec.get("label") or "agent_anonymous")
    digest = hashlib.sha256(body.content.encode("utf-8")).hexdigest()
    existing = rt.get_event(body.event_id)
    if existing:
        held = str(existing.get("content_sha256") or "")
        if held and held != digest:
            raise HTTPException(status_code=409, detail="idempotency_conflict")
        return {
            "status": "already_committed",
            "event_id": body.event_id,
            "block_index": existing.get("block_index"),
            "block_hash": existing.get("block_hash"),
            "graph_id": existing.get("graph_id"),
            "protocol": PROTOCOL_VERSION,
        }
    memo_body = MemoRequest(
        content=body.content,
        memo_type=body.kind if body.kind in {"observation", "lesson", "decision", "proof", "bug", "fix"} else "observation",
        tags=list(body.tags) + ["268", "agent_event"],
        session_id=body.session_id,
        visibility=body.visibility,
        inject_context=True,
    )
    stored = ai_memo(memo_body, request, key_record)
    committed = rt.commit_event(
        event_id=body.event_id,
        agent_id=agent_id,
        kind=body.kind,
        content_sha256=digest,
        block_index=stored.get("block_index"),
        block_hash=stored.get("block_hash"),
        graph_id=stored.get("graph_id"),
    )
    return {
        "status": committed.get("status"),
        "event_id": body.event_id,
        "protocol": PROTOCOL_VERSION,
        "memo": stored,
        "content_sha256": digest,
        "includes_thinking": False,
        "includes_system_prompt": False,
    }
