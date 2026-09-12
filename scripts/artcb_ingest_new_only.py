#!/usr/bin/env python3
"""Classify a pasted ChatGPT/operator report: REPEATED vs NEW for selective ingest.

Protocol R16 still requires the FULL user_query in /tmp/artcb_turn_prompt.txt for
bootstrap. This tool only builds a *second* new-only memo so we do not re-encode
audits already sealed in CERTIFICATION_MATRIX / rapports 328–331.

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_ingest_new_only.py /tmp/artcb_turn_prompt.txt
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Themes already sealed in matrix/rapports — hits count as REPEATED, not novel facts.
REPEATED_PATTERNS = [
    r"CERTIFIED_100\s*=\s*FALSE",
    r"CERTIFIED_100\s*=\s*false",
    r"#77\b",
    r"#86\b",
    r"\bR273\b",
    r"\bR328\b",
    r"\bR329\b",
    r"\bR330\b",
    r"\bR331\b",
    r"height\(\)",
    r"public_last_index",
    r"4 couches",
    r"NodeID",
    r"invalid_replica_key_binding",
    r"ARTCB_THINKING\.md",
    r"afterAgentThought",
    r"agent_thoughts\.jsonl",
    r"Nouveau chantier",
]


def classify(text: str) -> dict:
    hits = {p: len(re.findall(p, text, flags=re.I)) for p in REPEATED_PATTERNS}
    # Heuristic NEW signals (operator intents not yet sealed as PASS_LIVE final)
    new_signals = []
    low = text.lower()
    if "langage" in low and ("validation live" in low or "pas encore" in low or "toujour" in low):
        new_signals.append("langage_ia_live_incomplete")
    if "rule telemetry" in low or "compteur" in low and "règle" in low or "regle" in low:
        new_signals.append("rule_telemetry_subsystem")
    if "thk-" in low or "thinkingid" in low.replace(" ", ""):
        new_signals.append("thinking_id_registry")
    if "seulement les nouveau" in low or "seulement les nouveaux" in low or "ingerer seulement" in low:
        new_signals.append("selective_ingest_policy")
    new_only = (
        f"ARTCB_TURN_NEW_ONLY ts_ns={time.time_ns()}\n"
        f"full_sha256={hashlib.sha256(text.encode()).hexdigest()}\n"
        f"full_chars={len(text)}\n"
        f"new_signals={new_signals}\n"
        f"repeated_hits={ {k: v for k, v in hits.items() if v} }\n"
        "policy: bootstrap_full_required; memo_new_only=delta_intents; "
        "do_not_reencode_chatgpt_r328_r331_audits_as_novel\n"
    )
    return {
        "ts_ns": time.time_ns(),
        "full_chars": len(text),
        "full_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "repeated_hits": hits,
        "new_signals": new_signals,
        "new_only_text": new_only,
        "new_only_sha256": hashlib.sha256(new_only.encode()).hexdigest(),
    }


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/artcb_turn_prompt.txt")
    text = path.read_text(encoding="utf-8", errors="replace")
    out = classify(text)
    dest = ROOT / "data" / "trace" / "turn_prompt_classify.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({k: v for k, v in out.items() if k != "new_only_text"}, indent=2) + "\n")
    Path("/tmp/artcb_turn_prompt_new_only.txt").write_text(out["new_only_text"], encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("full_chars", "full_sha256", "new_signals", "new_only_sha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
