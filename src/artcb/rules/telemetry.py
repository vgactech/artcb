"""R337 — Rule Telemetry engine (local proof layer).

Levels (honest):
  seen       — rule was present in registry / context for this turn
  checked    — agent explicitly recorded a control (RuleChecked) — NOT proof
  applied    — concrete evidence artifact attached (RuleApplied) — still claim
  applied_confirmed — independent evidence path present (file/HTTP/commit/test)
  violated / corrected / not_proven / waived

Thinking text alone must NEVER auto-increment ``applied`` or ``applied_confirmed``.
Absence of violation ≠ applied.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
# Seed registry is versioned under rules/ (data/ is often gitignored).
REGISTRY_PATH = ROOT / "rules" / "rule_registry.json"
# Runtime usage log stays local under data/trace (append-only, not source of truth for git).
USAGE_PATH = ROOT / "data" / "trace" / "rule_usage.jsonl"
# Optional overlay copy for local edits (never deletes rules/ seed).
LOCAL_REGISTRY_OVERLAY = ROOT / "data" / "rules" / "rule_registry.overlay.json"

COUNTERS = (
    "seen",
    "checked",
    "applied",
    "applied_confirmed",
    "violated",
    "corrected",
    "not_proven",
    "waived",
)

# Evidence kinds that may promote applied → applied_confirmed
CONFIRMED_EVIDENCE = frozenset(
    {
        "http_status",
        "git_sha",
        "pytest",
        "file_sha256",
        "measurement_json",
        "live_bootstrap",
        "commit",
    }
)


@dataclass
class RuleEvent:
    rule_id: str
    kind: str  # one of COUNTERS or "conflict" / "coverage_gap"
    ts_ns: int = 0
    turn_id: str = ""
    task_type: str = ""
    evidence_kind: str = ""
    evidence_ref: str = ""
    note: str = ""
    agent_claim_only: bool = False

    def __post_init__(self) -> None:
        if not self.ts_ns:
            self.ts_ns = time.time_ns()


def load_registry(path: Path | None = None) -> dict[str, Any]:
    p = path or REGISTRY_PATH
    if not p.is_file():
        return {"version": 0, "rules": [], "note": "registry_missing"}
    return json.loads(p.read_text(encoding="utf-8"))


def append_event(event: RuleEvent, path: Path | None = None) -> dict[str, Any]:
    """Append-only usage log. Never deletes. Returns the written row."""
    if event.kind not in COUNTERS and event.kind not in {"conflict", "coverage_gap", "new_rule"}:
        raise ValueError(f"invalid_event_kind:{event.kind}")
    # Guard: thinking-only claims cannot be applied_confirmed
    if event.kind == "applied_confirmed":
        if event.agent_claim_only or event.evidence_kind not in CONFIRMED_EVIDENCE:
            raise ValueError("applied_confirmed_requires_independent_evidence")
        if not (event.evidence_ref or "").strip():
            raise ValueError("applied_confirmed_requires_evidence_ref")
    if event.kind == "applied" and event.agent_claim_only and not event.evidence_ref:
        # allow applied as weak claim but flag it
        event.note = (event.note + " | weak_claim_no_evidence").strip(" |")

    dest = path or USAGE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    row = asdict(event)
    row["protocol"] = "r337-rule-telemetry-v1"
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def iter_events(path: Path | None = None) -> Iterable[dict[str, Any]]:
    p = path or USAGE_PATH
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize(path: Path | None = None, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = registry if registry is not None else load_registry()
    rules = {r["rule_id"]: r for r in (reg.get("rules") or []) if r.get("rule_id")}
    counts: dict[str, dict[str, int]] = {rid: {c: 0 for c in COUNTERS} for rid in rules}
    last_ts: dict[str, int] = {}
    conflicts: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    for ev in iter_events(path):
        rid = str(ev.get("rule_id") or "")
        kind = str(ev.get("kind") or "")
        if kind == "conflict":
            conflicts.append(ev)
            continue
        if kind == "coverage_gap":
            gaps.append(ev)
            continue
        if rid not in counts:
            counts[rid] = {c: 0 for c in COUNTERS}
        if kind in COUNTERS:
            counts[rid][kind] += 1
        ts = int(ev.get("ts_ns") or 0)
        if ts >= last_ts.get(rid, 0):
            last_ts[rid] = ts

    ranked_usage = sorted(
        (
            {
                "rule_id": rid,
                "applied_confirmed": c.get("applied_confirmed", 0),
                "applied": c.get("applied", 0),
                "checked": c.get("checked", 0),
                "violated": c.get("violated", 0),
                "severity": (rules.get(rid) or {}).get("severity") or "unknown",
            }
            for rid, c in counts.items()
        ),
        key=lambda x: (x["applied_confirmed"], x["applied"], x["checked"]),
        reverse=True,
    )

    ranked_risk = sorted(
        (
            {
                "rule_id": rid,
                "priority": priority_score(rules.get(rid) or {"rule_id": rid}, counts.get(rid, {}), last_ts.get(rid)),
                "severity": (rules.get(rid) or {}).get("severity") or "unknown",
                "violated": counts.get(rid, {}).get("violated", 0),
                "applied_confirmed": counts.get(rid, {}).get("applied_confirmed", 0),
                "last_ts_ns": last_ts.get(rid),
            }
            for rid in set(list(rules) + list(counts))
        ),
        key=lambda x: x["priority"],
        reverse=True,
    )

    # Optional corpus coverage (R340) — never pretend registry == full corpus
    coverage_path = ROOT / "rules" / "rule_coverage.json"
    corpus: dict[str, Any] = {}
    if coverage_path.is_file():
        try:
            corpus = json.loads(coverage_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            corpus = {}

    return {
        "protocol": "r337-rule-telemetry-v1",
        "registry_version": reg.get("version"),
        "rules_total": len(rules),  # legacy key = registered_rules only
        "registered_rules": len(rules),
        "counts": counts,
        "top_by_usage": ranked_usage[:15],
        "top_by_risk": ranked_risk[:15],
        "conflicts": conflicts[-20:],
        "coverage_gaps": gaps[-20:],
        "corpus": {
            "numbered_entry_sum": ((corpus.get("corpus_markers") or {}).get("numbered_entry_sum")),
            "unmapped_estimate": ((corpus.get("registry_coverage") or {}).get("unmapped_estimate")),
            "note": "registered_rules ≠ ARTCB total normative corpus",
        },
        "note": "absence_of_violation_is_not_applied; thinking_alone_never_applied_confirmed; rules_total=registry_only",
        "certified_100": False,
    }


def priority_score(rule: dict[str, Any], counters: dict[str, int], last_ts_ns: int | None) -> float:
    """Frequency must NOT dominate. Critical rare rules stay high."""
    sev = str(rule.get("severity") or "medium").lower()
    sev_w = {"critical": 100.0, "high": 60.0, "medium": 30.0, "low": 10.0}.get(sev, 20.0)
    viol = float(counters.get("violated") or 0) * 8.0
    miss = float(counters.get("not_proven") or 0) * 3.0
    # Recency of last validation (older → higher risk)
    age_boost = 0.0
    if last_ts_ns:
        age_days = max(0.0, (time.time_ns() - last_ts_ns) / 1e9 / 86400.0)
        age_boost = min(40.0, age_days * 2.0)
    else:
        age_boost = 25.0  # never evidenced
    # Soft frequency term (capped) — never overrides criticality
    freq = min(15.0, float(counters.get("checked") or 0) * 0.05)
    return sev_w + viol + miss + age_boost + freq


def badge_snapshot(path: Path | None = None) -> dict[str, Any]:
    """Compact block for ARTCB_THINKING.md header — display only, not source of truth."""
    s = summarize(path)
    counts = s.get("counts") or {}
    agg = {c: 0 for c in COUNTERS}
    for row in counts.values():
        for c in COUNTERS:
            agg[c] += int(row.get(c) or 0)
    corpus = s.get("corpus") or {}
    return {
        "status": "ACTIVE",
        "rule_registry_version": s.get("registry_version"),
        "rules_total": s.get("rules_total"),  # legacy alias
        "registered_rules": s.get("registered_rules") or s.get("rules_total"),
        "corpus_numbered_entry_sum": corpus.get("numbered_entry_sum"),
        "corpus_unmapped_estimate": corpus.get("unmapped_estimate"),
        "aggregate": agg,
        "top_rules_by_risk": (s.get("top_by_risk") or [])[:5],
        "top_rules_by_usage": (s.get("top_by_usage") or [])[:5],
        "conflicts": len(s.get("conflicts") or []),
        "coverage_gaps": len(s.get("coverage_gaps") or []),
        "evidence": {
            "rule_registry": str(REGISTRY_PATH.relative_to(ROOT)) if REGISTRY_PATH.exists() else None,
            "rule_usage": str(USAGE_PATH.relative_to(ROOT)) if True else None,
            "rule_coverage": "rules/rule_coverage.json",
        },
        "honest": {
            "thinking_alone_never_applied_confirmed": True,
            "absence_of_violation_not_applied": True,
            "rules_total_is_registry_only": True,
            "registered_neq_global_corpus": True,
            "applied_confirmed_independent_of_applied": True,
            "certified_100": False,
        },
        "counter_semantics": {
            "applied": "weak claim with optional evidence_ref",
            "applied_confirmed": "independent evidence_kind+ref; does NOT require prior applied event",
            "note": "applied_confirmed > applied is allowed by design (R344)",
        },
    }


def mark_turn_seen(rule_ids: Iterable[str], *, turn_id: str, task_type: str = "") -> list[dict[str, Any]]:
    rows = []
    for rid in rule_ids:
        rows.append(
            append_event(
                RuleEvent(rule_id=rid, kind="seen", turn_id=turn_id, task_type=task_type)
            )
        )
    return rows


def coverage_gap(*, expected: list[str], checked: list[str], turn_id: str, task_type: str = "") -> dict[str, Any]:
    missing = [r for r in expected if r not in set(checked)]
    return append_event(
        RuleEvent(
            rule_id="COVERAGE",
            kind="coverage_gap",
            turn_id=turn_id,
            task_type=task_type,
            note=json.dumps({"expected": expected, "checked": checked, "missing": missing}, ensure_ascii=False),
        )
    )
