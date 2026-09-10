#!/usr/bin/env python3
"""Cursor preCompact — log WHEN context is dropped mid-turn.

This is the documented moment memory is lost inside a conversation.
Observational. Cannot block compaction. Never ARTCB.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from artcb_reason_log import append_reason  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    extra = {
        "trigger": payload.get("trigger"),
        "context_usage_percent": payload.get("context_usage_percent"),
        "context_tokens": payload.get("context_tokens"),
        "context_window_size": payload.get("context_window_size"),
        "message_count": payload.get("message_count"),
        "messages_to_compact": payload.get("messages_to_compact"),
        "is_first_compaction": payload.get("is_first_compaction"),
    }
    append_reason(
        kind="preCompact",
        text="context_compaction",
        extra=extra,
    )
    sys.stdout.write(
        json.dumps(
            {
                "user_message": (
                    "ARTCB R300: compaction — relire TOUS les fichiers de règles "
                    "de la première à la dernière ligne avant de continuer."
                )
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
