#!/usr/bin/env python3
"""Append-only local reasoning / surfaced-thinking journal.

Never prints secrets. Never POSTs to ARTCB. data/ is gitignored.
~~2026-09-10T00:05:00Z~~ This is not private model CoT. Cursor generates
thinking on the hosted backend first (afterAgentThought is a later copy).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = ROOT / "data" / "trace"
REASON_PATH = TRACE_DIR / "agent_reasoning.jsonl"
THOUGHT_PATH = TRACE_DIR / "agent_thoughts.jsonl"
COMPACT_PATH = TRACE_DIR / "precompact.jsonl"

# ~~do not send these kinds to ARTCB ingest~~
ARTCB_FORBIDDEN_KINDS = frozenset({"afterAgentThought", "thinking", "system", "tokens"})


def _write(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return row


def append_reason(
    *,
    kind: str,
    text: str,
    extra: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    raw = text or ""
    row: dict[str, Any] = {
        "ts_ns": time.time_ns(),
        "kind": kind,
        "chars": len(raw),
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "text": raw,
        "includes_thinking": kind in {"afterAgentThought", "thinking"},
        "artcb_bound": False,
        "note": "local_only_not_artcb",
    }
    if extra:
        for key, value in extra.items():
            if key not in row:
                row[key] = value
    dest = path or (THOUGHT_PATH if kind == "afterAgentThought" else REASON_PATH)
    if kind == "preCompact":
        dest = path or COMPACT_PATH
    return _write(dest, row)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(json.dumps({"ok": False, "reason": "usage: artcb_reason_log.py KIND [text]"}))
        return 2
    kind = args[0]
    text = " ".join(args[1:]) if len(args) > 1 else sys.stdin.read()
    row = append_reason(kind=kind, text=text)
    print(
        json.dumps(
            {
                "ok": True,
                "kind": row["kind"],
                "chars": row["chars"],
                "sha256": row["sha256"],
                "ts_ns": row["ts_ns"],
                "artcb_bound": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
