"""R337 — Rule Telemetry & Compliance (append-only; never invent applied)."""

try:
    from artcb.rules.telemetry import (  # noqa: F401
        COUNTERS,
        RuleEvent,
        append_event,
        badge_snapshot,
        load_registry,
        priority_score,
        summarize,
    )
except ImportError:  # pytest with src.* path style
    from src.artcb.rules.telemetry import (  # noqa: F401
        COUNTERS,
        RuleEvent,
        append_event,
        badge_snapshot,
        load_registry,
        priority_score,
        summarize,
    )

__all__ = [
    "COUNTERS",
    "RuleEvent",
    "append_event",
    "badge_snapshot",
    "load_registry",
    "priority_score",
    "summarize",
]
