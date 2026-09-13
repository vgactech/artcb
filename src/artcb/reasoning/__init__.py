"""R333 package — reasoning identity (canonical, not human text)."""

from src.artcb.reasoning.canonical import (
    CanonicalReasoning,
    canonicalize_structured,
    canonicalize_text,
    human_view,
    semantic_identity_report,
)

__all__ = [
    "CanonicalReasoning",
    "canonicalize_structured",
    "canonicalize_text",
    "human_view",
    "semantic_identity_report",
]
