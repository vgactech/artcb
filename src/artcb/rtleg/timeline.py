"""Append-only RT-LEG timeline."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from pathlib import Path

from src.artcb.config import load_settings
from src.artcb.rtleg.events import RTLEGEvent

logger = logging.getLogger("artcb.rtleg.timeline")


class RTLEGTimeline:
    """Signed temporal execution graph — append-only journal."""

    def __init__(self, path: Path | None = None) -> None:
        settings = load_settings()
        self.path = path or (settings.data_dir / "rtleg" / "events.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: RTLEGEvent) -> RTLEGEvent:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        logger.debug("RT-LEG append type=%s id=%s", event.event_type, event.event_id)
        return event

    def list_events(self, session_id: str | None = None, limit: int = 100) -> list[RTLEGEvent]:
        if not self.path.exists():
            return []
        events: list[RTLEGEvent] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                event = RTLEGEvent(**json.loads(line))
                if session_id and event.session_id != session_id:
                    continue
                events.append(event)
        return events[-limit:]
