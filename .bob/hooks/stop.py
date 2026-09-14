#!/usr/bin/env python3
"""Bob IDE — Stop hook.

À la fin de chaque tour :
  - Archive le dernier message assistant + métadonnées dans bob_turns.jsonl
  - Log les outils utilisés dans bob_tool_usage.jsonl

Fail-open. Jamais de secrets.
"""
from __future__ import annotations
import hashlib, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        last_msg = str(payload.get("last_assistant_message") or "")
        row = {
            "ts_ns": time.time_ns(),
            "kind": "bob_stop",
            "session_id": payload.get("session_id"),
            "chars": len(last_msg),
            "sha256": hashlib.sha256(last_msg.encode()).hexdigest(),
            "artcb_bound": False,
            "note": "bob_ide_hook_stop",
        }
        with (TRACE / "bob_turns.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
