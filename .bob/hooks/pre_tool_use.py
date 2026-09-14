#!/usr/bin/env python3
"""Bob IDE — PreToolUse hook.

Bloque toute tentative d'écrire dans :
  - blocks.jsonl (D-043/D-044/D-045 : jamais wipe)
  - chain.key (jamais toucher la clé de nœud)
  - Toute commande `git reset --hard` ou `rm -rf data/`

Archive l'événement dans data/trace/bob_pretooluse.jsonl.
Fail-open sauf pour les cas bloquants (exit 2).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

# Patterns BLOQUANTS (exit 2)
BLOCKED_PATHS = [
    "blocks.jsonl",
    "chain.key",
    "genesis.json",
]

BLOCKED_COMMANDS = [
    "git reset --hard",
    "rm -rf data/",
    "rm -rf blocks",
    "> blocks.jsonl",
    "truncate.*blocks",
]


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    session_id = payload.get("session_id", "")
    ts_ns = time.time_ns()

    violation = None

    # Vérifier write_file / apply_diff / search_and_replace sur fichiers critiques
    if tool_name in ("write_file", "apply_diff", "search_and_replace", "insert_content"):
        path = str(tool_input.get("path", ""))
        for blocked in BLOCKED_PATHS:
            if blocked in path:
                violation = f"BLOCKED: tentative d'écriture dans {blocked} (D-043)"
                break

    # Vérifier execute_command pour commandes dangereuses
    if tool_name == "execute_command":
        cmd = str(tool_input.get("command", ""))
        import re
        for pattern in BLOCKED_COMMANDS:
            if re.search(pattern, cmd, re.IGNORECASE):
                violation = f"BLOCKED: commande dangereuse détectée: {cmd[:60]}"
                break

    # Archive
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_ns": ts_ns,
            "kind": "bob_pretooluse",
            "session_id": session_id,
            "tool_name": tool_name,
            "violation": violation,
            "path": str(tool_input.get("path", "")),
            "cmd_preview": str(tool_input.get("command", ""))[:80],
        }
        with (TRACE / "bob_pretooluse.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    if violation:
        sys.stderr.write(violation + "\n")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
