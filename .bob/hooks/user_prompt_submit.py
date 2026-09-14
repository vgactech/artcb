#!/usr/bin/env python3
"""Bob IDE — UserPromptSubmit hook.

Capture le prompt entrant + injecte le contexte ARTCB dans chaque tour.
Archive dans data/trace/bob_prompts.jsonl (append-only, gitignored).
Injecte aussi l'état git HEAD courant pour que le modèle sache toujours où il en est.

Fail-open : exit 0 en cas d'erreur.
Jamais de secrets affichés.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "data" / "trace"

# Fichiers de règles à rappeler dans chaque prompt (résumé court)
RULE_REMINDERS = [
    "PROTOCOLE_ARTCB",
    "DECISIONS_UTILISATEUR_ARTCB",
    ".cursor/rules/artcb-live-node.mdc",
]


def get_git_head() -> str:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
        return f"{sha} ({branch})"
    except Exception:
        return "inconnu"


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "")
    ts_ns = time.time_ns()

    # Archive le prompt (jamais les secrets)
    try:
        TRACE.mkdir(parents=True, exist_ok=True)
        row = {
            "ts_ns": ts_ns,
            "kind": "bob_prompt_submit",
            "session_id": session_id,
            "prompt_len": len(prompt),
            "prompt_preview": prompt[:80].replace("\n", " "),
            "git_head": get_git_head(),
        }
        with (TRACE / "bob_prompts.jsonl").open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # Injecter contexte ARTCB dans stdout → ajouté au contexte du modèle
    git_head = get_git_head()
    lines = [
        f"## ARTCB — Rappel automatique (Bob IDE UserPromptSubmit)",
        f"git HEAD = {git_head}",
        f"CERTIFIED_100=false | Jamais wipe | Jamais inventer SHA/hauteur/tip",
        f"Mode DEBUG actif | Répondre en français | Python+C uniquement",
        f"Nœud live OVH1 = http://152.228.144.34:8000 (accès via SSM aws-node-3)",
        f"V-PQC-1 PASS ✅ (recompute artcb2 validé) | V-PQC-2 à implémenter",
        f"USER↔NODE: OVH1 ✅ | OVH2/OVH4/AWS3 ❌ (wallet absent — adresse non déterministe)",
        f"Hooks Bob IDE: SessionStart ✅ | Stop ✅ | PostToolUse ✅ | UserPromptSubmit ✅ (ce hook)",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
