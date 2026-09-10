#!/usr/bin/env python3
"""Cursor sessionStart — inject the full rule-file reading list.

Fire-and-forget. Fail open. No secrets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from artcb_reason_log import append_reason  # noqa: E402

RULE_FILES = [
    ".cursor/rules/artcb-live-node.mdc",
    ".cursor/rules/artcb-read-all.mdc",
    ".cursor/rules/mac-node-local.mdc",
    ".cursor/rules/aws-node-3.mdc",
    ".cursor/rules/ovh-node-4.mdc",
    "AUTO_PROMPT_ARTCB",
    "PROTOCOLE_ARTCB",
    "LEÇONS_APPRISES_ARTCB",
    "STANDARD_NAMES_ARTCB",
    "ROADMAP_GENERAL_ARTCB",
    "INDEX_ARTCB",
    "CONFIGURATION_ARTCB",
    "CHECKLIST_PRE_DEV_ARTCB",
    "QUESTIONS_OUVERTES_ARTCB",
    "CAHIER_DES_CHARGES_ARTCB",
]


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    append_reason(
        kind="sessionStart",
        text="session_start_rule_index",
        extra={
            "session_id": payload.get("session_id"),
            "composer_mode": payload.get("composer_mode"),
            "rule_files": RULE_FILES,
        },
    )
    listing = "\n".join(f"- {p}" for p in RULE_FILES)
    ctx = (
        "ARTCB R300 (2026-09-10T00:05:00Z). Relire TOUS ces fichiers de la "
        "première à la dernière ligne au début de CHAQUE tour ET après chaque "
        "compaction / étape majeure à l'intérieur du tour. Le chat n'est pas "
        "le protocole. 11-15 = ne jamais supprimer ; ce n'est PAS la seule "
        "règle.\n"
        f"{listing}\n"
        "ARTCB thinking: Cursor UI label stays « Thought briefly » (product; "
        "NOT renamable). Capture AUTO = afterAgentThought → "
        "data/trace/ARTCB_THINKING.md + thinking/latest.raw.txt + sha256. "
        "Pin ARTCB_THINKING.md to see capture live. CoT privé jamais ici. "
        "ARTCB private memo only if ARTCB_INGEST_THINKING=1. "
        "Verify: scripts/artcb_verify_thinking_bridge.py.\n"
        "~~Bob §4 Mac = observateur~~ barré 2026-09-10T00:05:00Z. Mac = "
        "replica PBFT officiel (R297b). Transport RFC1918 ≠ rôle."
    )
    sys.stdout.write(json.dumps({"additional_context": ctx}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
