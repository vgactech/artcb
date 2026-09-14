#!/usr/bin/env python3
"""Bob IDE — PostToolUse hook.

Après chaque outil write_file / apply_diff / insert_content / search_and_replace :
  - Vérifie qu'aucun secret connu n'a été écrit (seed_hex, privkey, dp.st., etc.)
  - Archive l'usage outil dans bob_tool_usage.jsonl

Exit 0 toujours (PostToolUse ne bloque pas). Les alertes vont dans stdout → contexte.
"""
from __future__ import annotations
import hashlib, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

# Patterns sensibles à détecter dans le contenu écrit
SENSITIVE = [
    re.compile(r"dp\.st\.[A-Za-z0-9]{20,}"),       # token Doppler
    re.compile(r"seed_hex\s*[:=]\s*['\"][0-9a-f]{60,}", re.I),
    re.compile(r"private[_\s]?key\s*[:=]\s*['\"][0-9a-f]{60,}", re.I),
    re.compile(r"-----BEGIN.*PRIVATE KEY-----"),
    re.compile(r"amelie92"),                          # mot de passe sudo connu exposé
]

WRITE_TOOLS = {"write_file", "apply_diff", "search_and_replace", "insert_content"}

def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    tool_response = str(payload.get("tool_response", ""))

    # Archive usage
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_ns": time.time_ns(),
            "kind": "bob_post_tool",
            "tool": tool_name,
            "path": tool_input.get("path", ""),
            "session_id": payload.get("session_id"),
            "artcb_bound": False,
        }
        with (TRACE / "bob_tool_usage.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Vérification secrets sur outils d'écriture
    if tool_name in WRITE_TOOLS:
        content = str(tool_input.get("content", "") or tool_input.get("diff", ""))
        alerts = []
        for pat in SENSITIVE:
            if pat.search(content):
                alerts.append(f"⚠️  SECRET DÉTECTÉ dans {tool_input.get('path','?')} : pattern '{pat.pattern[:40]}'")
        if alerts:
            print("## ARTCB — Alerte sécurité PostToolUse")
            for a in alerts:
                print(a)
            print("→ Vérifier manuellement avant git push")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
