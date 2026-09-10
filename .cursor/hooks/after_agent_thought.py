#!/usr/bin/env python3
"""Cursor afterAgentThought — copy surfaced thinking to local append-only jsonl.

Observational. Fail open. Never prints thinking. Never ARTCB.
"""

from __future__ import annotations

import json
import os
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
    text = str(payload.get("text") or "")
    extra = {}
    if payload.get("duration_ms") is not None:
        extra["duration_ms"] = payload.get("duration_ms")
    dest = (os.getenv("ARTCB_THOUGHT_LOG") or "").strip()
    append_reason(
        kind="afterAgentThought",
        text=text,
        extra=extra,
        path=Path(dest) if dest else None,
    )
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
