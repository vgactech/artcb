"""ARTCB Agent Memory Protocol (R268).

Independent of Cursor / Claude / ChatGPT. Cursor alwaysApply is one adapter.
Does not ingest thinking, system prompts, or tokens.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "268-agent-memory-runtime"

MEMORY_CAPABILITIES = (
    "memory:read",
    "memory:write",
    "context:read",
    "memo:write",
    "kcg:read",
    "kcg:publish",
    "agent:register",
)
PRIVILEGED_CAPABILITIES = (
    "wallet:export",
    "wallet:seed",
    "wallet:sign",
    "admin:*",
)

SCOPE_TO_CAPS = {
    "read": ("memory:read", "context:read", "kcg:read"),
    "write": ("memory:write", "memo:write", "kcg:publish", "agent:register"),
    "mining": (),
    "admin": PRIVILEGED_CAPABILITIES,
}


def memory_required() -> bool:
    return os.environ.get("ARTCB_MEMORY_REQUIRED", "").lower() in {"1", "true", "yes"}


def capabilities_for_scopes(scopes: list[str] | None) -> list[str]:
    caps: list[str] = []
    for scope in scopes or []:
        caps.extend(SCOPE_TO_CAPS.get(str(scope), ()))
    seen: list[str] = []
    for c in caps:
        if c not in seen:
            seen.append(c)
    return seen


class AgentRuntime:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "agent_runtime" / "runtime.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"agents": {}, "events": {}}
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"agents": {}, "events": {}}
        if not isinstance(parsed, dict):
            return {"agents": {}, "events": {}}
        parsed.setdefault("agents", {})
        parsed.setdefault("events", {})
        return parsed

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.path.chmod(0o600)

    def bootstrap(self, key_record: dict[str, Any] | None, *, protocol_http: dict | None = None) -> dict[str, Any]:
        rec = key_record or {}
        agent_id = str(rec.get("agent_id") or rec.get("label") or "agent_anonymous")
        caps = capabilities_for_scopes(rec.get("scopes") if isinstance(rec.get("scopes"), list) else ["read", "write"])
        required = [
            "GET /api/v1/agent/bootstrap",
            "GET /api/v1/ai/context",
            "GET /api/v1/ai/memory",
            "POST /api/v1/agent/events",
        ]
        return {
            "protocol": PROTOCOL_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "platform_hook": False,
            "ingest_platform_hook": False,
            "agent_id": agent_id,
            "kind": rec.get("kind") or "anonymous",
            "owner_address": rec.get("address") or rec.get("owner_address"),
            "capabilities": caps,
            "privileged_capabilities": list(PRIVILEGED_CAPABILITIES),
            "memory_required": memory_required(),
            "required_actions": required,
            "includes_thinking": False,
            "includes_system_prompt": False,
            "token_count_known": False,
            "idempotent_events": True,
            "health": protocol_http or {},
        }

    def register_agent(
        self,
        *,
        provider: str,
        label: str,
        owner_address: str | None,
        capabilities: list[str],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        aid = agent_id or f"agent_{uuid.uuid4().hex[:12]}"
        allowed = [c for c in capabilities if c in MEMORY_CAPABILITIES]
        row = {
            "agent_id": aid,
            "provider": (provider or "generic")[:64],
            "label": (label or aid)[:128],
            "owner_address": owner_address,
            "capabilities": allowed,
            "created_at": time.time(),
            "revoked": False,
        }
        self._state["agents"][aid] = row
        self._save()
        return row

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = (self._state.get("events") or {}).get(event_id)
        return row if isinstance(row, dict) else None

    def commit_event(
        self,
        *,
        event_id: str,
        agent_id: str,
        kind: str,
        content_sha256: str,
        block_index: int | None,
        block_hash: str | None,
        graph_id: str | None,
    ) -> dict[str, Any]:
        existing = self.get_event(event_id)
        if existing:
            return {**existing, "status": "already_committed"}
        row = {
            "event_id": event_id,
            "agent_id": agent_id,
            "kind": kind,
            "content_sha256": content_sha256,
            "block_index": block_index,
            "block_hash": block_hash,
            "graph_id": graph_id,
            "committed_at": time.time(),
            "status": "committed",
        }
        self._state["events"][event_id] = row
        self._save()
        return {"status": "committed", **row}
