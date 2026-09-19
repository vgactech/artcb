"""RT-LEG event models."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class RTLEGEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    timestamp: str = Field(default_factory=utc_now_iso)
    session_id: str
    agent: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    graph_id: str | None = None
    signature: str | None = None
