#!/usr/bin/env python3
"""R340 — Rule corpus cartography (sources ≠ telemetry registry).

Honest labels:
  registry_version / registered_rules  = rules/rule_registry.json only
  corpus_*                             = detections across normative files
Does NOT invent CERTIFIED_100. Does NOT delete history.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "rules"
LOG_DIR = ROOT / "logs" / "R340"

SOURCE_SPECS: list[dict[str, Any]] = [
    {"id": "rule_registry", "path": "rules/rule_registry.json", "kind": "REGISTRY", "authority": "telemetry"},
    {"id": "protocole", "path": "PROTOCOLE_ARTCB", "kind": "RULE", "authority": "protocol"},
    {"id": "auto_prompt", "path": "AUTO_PROMPT_ARTCB", "kind": "RULE", "authority": "agent_instructions"},
    {"id": "live_node", "path": ".cursor/rules/artcb-live-node.mdc", "kind": "RULE", "authority": "cursor"},
    {"id": "read_all", "path": ".cursor/rules/artcb-read-all.mdc", "kind": "RULE", "authority": "cursor"},
    {"id": "mac_node", "path": ".cursor/rules/mac-node-local.mdc", "kind": "RULE", "authority": "cursor"},
    {"id": "aws_node", "path": ".cursor/rules/aws-node-3.mdc", "kind": "RULE", "authority": "cursor"},
    {"id": "ovh4", "path": ".cursor/rules/ovh-node-4.mdc", "kind": "RULE", "authority": "cursor"},
    {"id": "decisions", "path": "DECISIONS_UTILISATEUR_ARTCB", "kind": "DECISION", "authority": "operator"},
    {"id": "cdc", "path": "CAHIER_DES_CHARGES_ARTCB", "kind": "SPEC", "authority": "product"},
    {"id": "checklist", "path": "CHECKLIST_PRE_DEV_ARTCB", "kind": "CHECK", "authority": "dev_gate"},
    {"id": "questions", "path": "QUESTIONS_OUVERTES_ARTCB", "kind": "QUESTION", "authority": "open"},
    {"id": "lecons", "path": "LEÇONS_APPRISES_ARTCB", "kind": "LESSON", "authority": "history"},
    {"id": "gouvernance", "path": "GOUVERNANCE_ARTCB", "kind": "RULE", "authority": "governance"},
    {"id": "standard_names", "path": "STANDARD_NAMES_ARTCB", "kind": "CONVENTION", "authority": "naming"},
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _count_numbered_entries(text: str) -> int:
    # "73. **R338" or "1. " style at line start
    return len(re.findall(r"(?m)^\s*(?:~~)?\d+\.\s+", text))


def _count_rt_ids(text: str) -> list[str]:
    return sorted(set(re.findall(r"\bRT-[A-Z0-9-]+\b", text)))


def _count_d_ids(text: str) -> list[str]:
    return sorted(set(re.findall(r"\bD-\d{3}\b", text)))


def _count_rxxx(text: str) -> list[str]:
    return sorted(set(re.findall(r"\bR(?:3\d{2}|2\d{2}|1\d{2})\b", text)))


def _protocol_bullets(text: str) -> int:
    # PROTOCOLE often uses numbered 1. … 17.
    return _count_numbered_entries(text)


def scan_source(spec: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / spec["path"]
    row: dict[str, Any] = {
        "source_id": spec["id"],
        "path": spec["path"],
        "kind": spec["kind"],
        "authority": spec["authority"],
        "present": path.is_file(),
        "bytes": 0,
        "sha256": None,
        "detections": {},
        "notes": [],
    }
    if not path.is_file():
        row["notes"].append("missing")
        return row
    raw = path.read_text(encoding="utf-8", errors="replace")
    row["bytes"] = len(raw.encode("utf-8"))
    row["sha256"] = _sha(raw)
    dets: dict[str, Any] = {
        "numbered_entries": _count_numbered_entries(raw),
        "rt_ids": _count_rt_ids(raw),
        "d_ids": _count_d_ids(raw),
        "rxxx_ids": _count_rxxx(raw),
        "struck_markers": len(re.findall(r"~~.+?~~", raw, flags=re.S)),
    }
    if spec["id"] == "rule_registry":
        try:
            reg = json.loads(raw)
            rules = reg.get("rules") or []
            dets["registry_version"] = reg.get("version")
            dets["registered_rules"] = len(rules)
            dets["active_rules"] = sum(1 for r in rules if (r.get("status") or "active") == "active")
            dets["rule_ids"] = [r.get("rule_id") for r in rules]
        except json.JSONDecodeError as e:
            row["notes"].append(f"json_error:{e}")
    if spec["id"] == "protocole":
        dets["explicit_numbered_estimate"] = _protocol_bullets(raw)
    row["detections"] = dets
    return row


def build_coverage(sources: list[dict[str, Any]]) -> dict[str, Any]:
    reg = next((s for s in sources if s["source_id"] == "rule_registry"), {})
    reg_d = (reg.get("detections") or {})
    registered = int(reg_d.get("registered_rules") or 0)
    registered_ids = set(reg_d.get("rule_ids") or [])

    # Naive normative signal = sum of numbered entries across rule-like sources
    # (NOT unique semantic rules — honest "detected markers")
    marker_sum = 0
    by_authority: dict[str, int] = {}
    for s in sources:
        if not s.get("present"):
            continue
        n = int((s.get("detections") or {}).get("numbered_entries") or 0)
        if s["kind"] in {"RULE", "REGISTRY", "DECISION", "SPEC", "CHECK", "LESSON"}:
            marker_sum += n
            by_authority[s["authority"]] = by_authority.get(s["authority"], 0) + n

    live_has_r339 = False
    live = next((s for s in sources if s["source_id"] == "live_node"), None)
    if live and live.get("present"):
        text = (ROOT / " .cursor/rules/artcb-live-node.mdc".replace(" ", "")).read_text(encoding="utf-8", errors="replace") if False else (ROOT / ".cursor/rules/artcb-live-node.mdc").read_text(encoding="utf-8", errors="replace")
        live_has_r339 = "R339" in text

    return {
        "protocol": "r340-rule-corpus-coverage-v1",
        "ts_ns": time.time_ns(),
        "registry": {
            "version": reg_d.get("registry_version"),
            "registered_rules": registered,
            "active_rules": reg_d.get("active_rules"),
            "note": "registered_rules ≠ total ARTCB normative corpus",
        },
        "corpus_markers": {
            "numbered_entry_sum": marker_sum,
            "by_authority": by_authority,
            "note": "markers are detections not unique semantic RULE count",
        },
        "registry_coverage": {
            "registered": registered,
            "mapped_to_source": "PARTIAL",  # lineage file starts empty / manual
            "unmapped_estimate": max(0, marker_sum - registered),
            "live_node_includes_r339": live_has_r339,
            "sync_gap_live_node_vs_registry": (not live_has_r339) and ("RT-HW-H1" in registered_ids),
        },
        "categories": ["RULE", "DECISION", "SPEC", "INVARIANT", "CHECK", "EVIDENCE", "QUESTION", "LESSON", "CONVENTION"],
        "certified_100": False,
        "honest": {
            "rules_total_is_registry_only": True,
            "no_honest_global_X_rules_without_canonical_map": True,
            "dns_poison_match0_is_invalid_no_sample": True,
        },
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sources = [scan_source(s) for s in SOURCE_SPECS]
    coverage = build_coverage(sources)

    sources_doc = {
        "protocol": "r340-rule-sources-v1",
        "ts_ns": time.time_ns(),
        "note": "Append-only cartography. Does not replace PROTOCOLE/AUTO_PROMPT/Cursor. CERTIFIED_100=false.",
        "sources": sources,
    }
    lineage_stub = {
        "protocol": "r340-rule-lineage-v1",
        "ts_ns": time.time_ns(),
        "entries": [],
        "note": "Fill RuleID↔source↔decision↔code↔test↔evidence over time; empty ≠ zero corpus",
        "seed_from_registry": True,
    }
    # Seed lineage rows from registry IDs (source pointer only)
    reg_path = ROOT / "rules" / "rule_registry.json"
    if reg_path.is_file():
        reg = json.loads(reg_path.read_text())
        for r in reg.get("rules") or []:
            lineage_stub["entries"].append(
                {
                    "rule_id": r.get("rule_id"),
                    "status": r.get("status") or "active",
                    "priority": r.get("priority"),
                    "canonical_text": r.get("title"),
                    "source_incident": r.get("source_incident"),
                    "authority": "telemetry_registry",
                    "source": {"file": "rules/rule_registry.json"},
                    "supersedes": None,
                    "superseded_by": None,
                    "enforcement": "agent_telemetry",
                    "tests": [],
                    "evidence": ["data/trace/rule_usage.jsonl"],
                    "mapped": "registry_only",
                }
            )

    conflicts = {
        "protocol": "r340-rule-conflicts-v1",
        "ts_ns": time.time_ns(),
        "conflicts": [
            {
                "id": "SYNC_GAP_LIVE_NODE_R339",
                "severity": "high",
                "detail": "registry mentions R339 / RT-HW-* but artcb-live-node.mdc may lag at R338",
                "status": "detected_if_gap",
            },
            {
                "id": "LABEL_rules_total_MISREAD",
                "severity": "critical",
                "detail": "rules_total must be labeled registered_rules (telemetry), not global corpus size",
                "status": "open_until_dashboard_fix",
            },
        ],
        "certified_100": False,
    }

    (OUT_DIR / "rule_sources.json").write_text(json.dumps(sources_doc, indent=2) + "\n")
    (OUT_DIR / "rule_lineage.json").write_text(json.dumps(lineage_stub, indent=2) + "\n")
    (OUT_DIR / "rule_conflicts.json").write_text(json.dumps(conflicts, indent=2) + "\n")
    (OUT_DIR / "rule_coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
    (LOG_DIR / "coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")

    print(
        json.dumps(
            {
                "registered_rules": coverage["registry"]["registered_rules"],
                "registry_version": coverage["registry"]["version"],
                "numbered_entry_sum": coverage["corpus_markers"]["numbered_entry_sum"],
                "sync_gap": coverage["registry_coverage"]["sync_gap_live_node_vs_registry"],
                "live_has_r339": coverage["registry_coverage"]["live_node_includes_r339"],
                "certified_100": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
