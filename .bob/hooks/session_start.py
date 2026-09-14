#!/usr/bin/env python3
"""Bob IDE — SessionStart hook.

Injecte dans le contexte :
  1. Les fichiers de règles ARTCB à relire (même liste que Cursor sessionStart)
  2. L'état git HEAD + SHA live OVH1 si accessible
  3. Archive l'événement dans data/trace/bob_sessions.jsonl

Fail-open : toute erreur → exit 0, message stdout uniquement.
Jamais de secrets affichés.
"""
from __future__ import annotations
import hashlib, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

RULE_FILES = [
    ".cursor/rules/artcb-live-node.mdc",
    ".cursor/rules/artcb-read-all.mdc",
    ".cursor/rules/mac-node-local.mdc",
    "AUTO_PROMPT_ARTCB",
    "PROTOCOLE_ARTCB",
    "LEÇONS_APPRISES_ARTCB",
    "ROADMAP_GENERAL_ARTCB",
    "DECISIONS_UTILISATEUR_ARTCB",
]

def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # Archive
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_ns": time.time_ns(),
            "kind": "bob_session_start",
            "source": payload.get("source", "?"),
            "session_id": payload.get("session_id"),
            "artcb_bound": False,
            "note": "bob_ide_hook",
        }
        with (TRACE / "bob_sessions.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Injecter le contexte dans stdout → sera ajouté au contexte du modèle
    lines = ["## ARTCB — Contexte automatique (Bob IDE SessionStart)\n"]

    # Git HEAD
    try:
        import subprocess
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()[:12]
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), text=True).strip()
        lines.append(f"git HEAD = {sha} ({branch})")
    except Exception:
        lines.append("git HEAD = inconnu")

    # Fichiers de règles à relire
    lines.append("\nFichiers de règles ARTCB à relire (première→dernière ligne) :")
    for f in RULE_FILES:
        p = ROOT / f
        exists = "✅" if p.exists() else "❌"
        lines.append(f"  {exists} {f}")

    # Rappel protocole
    lines.append("\n⚠️  CERTIFIED_100=false — Jamais wipe — Jamais inventer SHA/hauteur/tip")
    lines.append("⚠️  Relire artcb-live-node.mdc + artcb-read-all.mdc avant tout travail")

    print("\n".join(lines))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
