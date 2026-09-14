#!/usr/bin/env python3
"""R341 — Divergence matrix: RULE → SOURCE → CODE → TEST → LIVE → EVIDENCE → STATUS.

Honest levels (do not collapse):
  DECIDED → REGISTERED → CODED → TESTED → LIVE_MEASURED → CERTIFIED

Also marks: SIMULATED_ONLY, OPEN, NOT_PROVEN, INVALID_NO_SAMPLE.

Does NOT invent CERTIFIED_100. registered_rules ≠ corpus.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "rules" / "rule_divergence_matrix.json"
LOG = ROOT / "logs" / "R341"

# Curated provenance for the 18 telemetry rules (append-only knowledge).
# status_max = highest demonstrated level, not aspiration.
CURATED: dict[str, dict[str, Any]] = {
    "RT-002": {
        "sources": [".cursor/rules/artcb-live-node.mdc", "AUTO_PROMPT_ARTCB", "rules/rule_registry.json"],
        "code": ["scripts/artcb_live_bootstrap.py", "scripts/artcb_dns_fix.py"],
        "tests": ["tests/test_r340_rule_corpus.py"],
        "live_evidence": ["logs/R340/sha_live.json", "logs/R341/sha_live.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "live /health ×4 vs origin/main; may lag follow-main after push",
    },
    "RT-003": {
        "sources": [".cursor/rules/artcb-live-node.mdc", "PROTOCOLE_ARTCB", "rules/rule_registry.json"],
        "code": ["scripts/artcb_live_bootstrap.py"],
        "tests": ["tests/test_r337_rule_telemetry.py"],
        "live_evidence": ["logs/R340/dns_poison_long_poll_INVALID_NO_SAMPLE.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "discipline + INVALID_NO_SAMPLE; not a formal adversarial liar-agent test",
    },
    "RT-004": {
        "sources": [".cursor/rules/artcb-live-node.mdc", "AUTO_PROMPT_ARTCB"],
        "code": [],
        "tests": [],
        "live_evidence": [],
        "status_max": "REGISTERED",
        "notes": "policy; historical 285/288 leak left; no automated secret scanner PASS claimed",
    },
    "RT-009": {
        "sources": [".cursor/rules/artcb-live-node.mdc"],
        "code": ["src/artcb"],  # path prefix — presence scanned
        "tests": [],
        "live_evidence": ["data/trace/ns.jsonl", "trace/ns.jsonl"],
        "status_max": "CODED",
        "notes": "ns tracing exists on some paths; full coverage of every exercised path NOT_PROVEN",
    },
    "RT-011": {
        "sources": [".cursor/rules/artcb-live-node.mdc", "AUTO_PROMPT_ARTCB"],
        "code": [],
        "tests": ["tests/test_r340_rule_corpus.py"],
        "live_evidence": [],
        "status_max": "REGISTERED",
        "notes": "enforced by process (strike+timestamp); not a runtime gate",
    },
    "RT-013": {
        "sources": [".cursor/rules/artcb-live-node.mdc", "rules/rule_registry.json"],
        "code": [],
        "tests": [],
        "live_evidence": ["rapports/339_hardware_identity_v2.md", "rapports/340_rule_corpus_cartography.md"],
        "status_max": "LIVE_MEASURED",
        "notes": "parallel OPEN remesures practiced; not 100% of historical opens closed",
    },
    "RT-016": {
        "sources": [".cursor/rules/artcb-live-node.mdc"],
        "code": ["scripts/artcb_live_bootstrap.py", "scripts/artcb_ingest_new_only.py"],
        "tests": [],
        "live_evidence": ["logs/R341/bootstrap.json", "logs/R340/bootstrap.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "ingest public memo when API key+HTTPS OK",
    },
    "RT-039": {
        "sources": [".cursor/rules/artcb-live-node.mdc", "AUTO_PROMPT_ARTCB"],
        "code": ["scripts/artcb_follow_main.sh", "scripts/artcb_r336_https_restart.py"],
        "tests": [],
        "live_evidence": ["logs/R340/sha_live.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "complete=push+follow+SHA measured intermittently; SSH:22 often CLOSED",
    },
    "RT-077-N04": {
        "sources": ["rules/rule_registry.json", "AUTO_PROMPT_ARTCB"],
        "code": [],
        "tests": [],
        "live_evidence": [],
        "status_max": "REGISTERED",
        "notes": "OPEN — SSH:22 CLOSED; N04 NOT_PROVEN",
        "open": True,
    },
    "RT-SYBIL-076": {
        "sources": ["rules/rule_registry.json", "AUTO_PROMPT_ARTCB"],
        "code": ["scripts/artcb_r337_anti_sybil_campaign.py"],
        "tests": ["tests/test_r337_rule_telemetry.py"],
        "live_evidence": ["logs/R339/sybil2.json", "logs/R337/anti_sybil_baseline.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "sample_count typically <50; campaign_certified=false",
        "open": True,
    },
    "RT-TELEMETRY": {
        "sources": ["rules/rule_registry.json", "AUTO_PROMPT_ARTCB"],
        "code": ["src/artcb/rules/telemetry.py", ".cursor/hooks/after_agent_thought.py"],
        "tests": ["tests/test_r337_rule_telemetry.py"],
        "live_evidence": ["data/trace/ARTCB_THINKING.md", "data/trace/rule_usage.jsonl"],
        "status_max": "TESTED",
        "notes": "engine v1; thinking≠applied_confirmed enforced in code; full conflict engine OPEN",
    },
    "RT-CAPABILITY-FIRST": {
        "sources": ["rules/rule_registry.json", ".cursor/rules/artcb-live-node.mdc"],
        "code": ["src/artcb/platform/capability_discovery.py", "scripts/artcb_r338_c04_capability_preflight.py"],
        "tests": ["tests/test_r338_capability_discovery.py"],
        "live_evidence": ["logs/R338/mac_c04_capability.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "MacBookAir7,1 UNSUPPORTED_HARDWARE measured",
    },
    "RT-077-C04": {
        "sources": ["rules/rule_registry.json", ".cursor/rules/artcb-live-node.mdc"],
        "code": ["src/artcb/platform/capability_discovery.py", "src/artcb/platform/mac_hardware_inventory.py"],
        "tests": ["tests/test_r338_capability_discovery.py", "tests/test_r339_mac_hardware_inventory.py"],
        "live_evidence": ["logs/R338/mac_c04_capability.json", "logs/R339/mac_inventory.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "C04 PASS on capable host still OPEN; this Mac = UNSUPPORTED",
        "open": True,
    },
    "RT-ISSUE-87": {
        "sources": ["rules/rule_registry.json", ".cursor/rules/artcb-live-node.mdc"],
        "code": [],
        "tests": [],
        "live_evidence": [],
        "status_max": "REGISTERED",
        "notes": "master execution order; OPEN items still listed in rapports",
        "open": True,
    },
    "RT-HW-H1": {
        "sources": ["docs/ARTCB_HARDWARE_IDENTITY_V2.md", "rules/rule_registry.json"],
        "code": ["src/artcb/platform/mac_hardware_inventory.py", "scripts/artcb_r339_mac_hardware_enrollment.py"],
        "tests": ["tests/test_r339_mac_hardware_inventory.py"],
        "live_evidence": ["logs/R339/enrollment_summary.json", "logs/R339/mac_inventory.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "H1 on MacBookAir7,1; H3/H4 not claimed; NodeCertificate CA OPEN",
        "open": True,
    },
    "RT-HW-BINDING": {
        "sources": ["docs/ARTCB_HARDWARE_IDENTITY_V2.md", "rules/rule_registry.json"],
        "code": ["src/artcb/platform/mac_hardware_inventory.py"],
        "tests": ["tests/test_r339_mac_hardware_inventory.py"],
        "live_evidence": [],
        "status_max": "CODED",
        "notes": "policy in enrollment bundle; FIDO/external H2 path NOT_PROVEN live",
        "open": True,
    },
    "RT-CORPUS-MAP": {
        "sources": ["rules/rule_registry.json", "AUTO_PROMPT_ARTCB", "rapports/340_rule_corpus_cartography.md"],
        "code": ["scripts/artcb_r340_rule_corpus_audit.py", "src/artcb/rules/telemetry.py", ".cursor/hooks/after_agent_thought.py"],
        "tests": ["tests/test_r340_rule_corpus.py"],
        "live_evidence": ["rules/rule_coverage.json", "logs/R340/audit_summary.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "cartography PARTIAL; unmapped_estimate high",
    },
    "RT-MEASURE-VALID": {
        "sources": ["rules/rule_registry.json", "AUTO_PROMPT_ARTCB"],
        "code": ["scripts/artcb_dns_fix.py", "scripts/artcb_r340_rule_corpus_audit.py"],
        "tests": ["tests/test_r340_rule_corpus.py"],
        "live_evidence": ["logs/R340/dns_poison_long_poll_INVALID_NO_SAMPLE.json", "logs/R340/sha_live.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "INVALID_NO_SAMPLE formalized; SHA campaign ≠ SHA executed",
    },
    "RT-DIVERGENCE-341": {
        "sources": ["rules/rule_registry.json", "AUTO_PROMPT_ARTCB", "rapports/341_rule_divergence_matrix.md"],
        "code": ["scripts/artcb_r341_rule_divergence_matrix.py"],
        "tests": ["tests/test_r341_rule_divergence.py"],
        "live_evidence": ["rules/rule_divergence_matrix.json", "logs/R341/summary.json"],
        "status_max": "LIVE_MEASURED",
        "notes": "matrix for 18+ registry rows + unmapped buckets; certified always 0",
    },
}

# Explicit unmapped / external normative buckets (not auto-counted as RULE PASS)
UNMAPPED_BUCKETS: list[dict[str, Any]] = [
    {
        "bucket_id": "UB-TOKENOMICS-R-H",
        "kind": "INVARIANT",
        "canonical_text": "R(H) emission schedule / 21M / HBP / OwnerDecay",
        "sources": ["DECISIONS_UTILISATEUR_ARTCB", "CAHIER_DES_CHARGES_ARTCB"],
        "status_max": "SIMULATED_ONLY",
        "notes": "simulations ≠ mainnet enforcement; do not auto-register as RT-*",
    },
    {
        "bucket_id": "UB-POL-TARGET",
        "kind": "SPEC",
        "canonical_text": "TargetPoL ≈ 70–80% × Capacity_measured",
        "sources": ["DECISIONS_UTILISATEUR_ARTCB"],
        "status_max": "SIMULATED_ONLY",
        "notes": "spec/simulation; not proven on live settlement path",
    },
    {
        "bucket_id": "UB-V01-V07",
        "kind": "CHECK",
        "canonical_text": "Validation ladder V-01…V-07",
        "sources": ["AUTO_PROMPT_ARTCB", "CERTIFICATION_MATRIX_ARTCB.md"],
        "status_max": "OPEN",
        "notes": "R340 did not close V-01…V-07; mostly PARTIAL/NOT_VALIDATED",
    },
    {
        "bucket_id": "UB-HUMAN-BIOMETRIC",
        "kind": "SPEC",
        "canonical_text": "HumanIdentity via verifiable credential; no raw biometrics on-chain",
        "sources": ["CAHIER_DES_CHARGES_ARTCB", "AUTO_PROMPT_ARTCB"],
        "status_max": "DECIDED",
        "notes": "wallet creation ≠ unique human proof",
    },
    {
        "bucket_id": "UB-ISSUE-86-ACL",
        "kind": "CHECK",
        "canonical_text": "ORG body multi-node ACL / session",
        "sources": ["AUTO_PROMPT_ARTCB", "logs/R331/measurement.json"],
        "status_max": "NOT_PROVEN",
        "notes": "NOT_PROVEN_acl_session measured",
    },
    {
        "bucket_id": "UB-CONSENSUS-PBFT",
        "kind": "INVARIANT",
        "canonical_text": "PBFT PRE-PREPARE/PREPARE/COMMIT/VC/NV; no double finality",
        "sources": [".cursor/rules/artcb-live-node.mdc", "AUTO_PROMPT_ARTCB"],
        "status_max": "PARTIAL",
        "notes": "many live campaigns; CERTIFIED_100 still false; N04 last FAIL historically",
    },
    {
        "bucket_id": "UB-PROTOCOLE-17",
        "kind": "RULE",
        "canonical_text": "PROTOCOLE_ARTCB ~17 explicit numbered obligations",
        "sources": ["PROTOCOLE_ARTCB"],
        "status_max": "DECIDED",
        "notes": "not 1:1 mapped into RT-* IDs",
    },
]


LEVELS = [
    "DECIDED",
    "REGISTERED",
    "CODED",
    "TESTED",
    "LIVE_MEASURED",
    "CERTIFIED",
    "SIMULATED_ONLY",
    "OPEN",
    "NOT_PROVEN",
    "PARTIAL",
]


def _exists(rel: str) -> bool:
    if not rel:
        return False
    p = ROOT / rel
    if p.exists():
        return True
    # prefix directory
    if rel.endswith("/") or (ROOT / rel).is_dir():
        return (ROOT / rel).exists()
    # soft: any file under prefix for src/artcb
    if rel == "src/artcb":
        return (ROOT / "src" / "artcb").is_dir()
    return False


def _filter_existing(paths: list[str]) -> list[str]:
    return [p for p in paths if _exists(p)]


def build_row(rule: dict[str, Any], curated: dict[str, Any]) -> dict[str, Any]:
    rid = rule["rule_id"]
    code = _filter_existing(list(curated.get("code") or []))
    tests = _filter_existing(list(curated.get("tests") or []))
    live = _filter_existing(list(curated.get("live_evidence") or []))
    sources = list(curated.get("sources") or [])
    status = curated.get("status_max") or "REGISTERED"
    # Downgrade if claimed higher than artifacts allow
    if status == "LIVE_MEASURED" and not live:
        status = "TESTED" if tests else ("CODED" if code else "REGISTERED")
    if status == "TESTED" and not tests:
        status = "CODED" if code else "REGISTERED"
    if status == "CODED" and not code:
        status = "REGISTERED"
    return {
        "rule_id": rid,
        "kind": "RULE",
        "priority": rule.get("priority"),
        "canonical_text": rule.get("title"),
        "registry_status": rule.get("status"),
        "sources": sources,
        "code": code,
        "tests": tests,
        "live_evidence": live,
        "status_max": status,
        "open": bool(curated.get("open")),
        "notes": curated.get("notes") or "",
        "pipeline": {
            "decided": True,
            "registered": True,
            "coded": bool(code),
            "tested": bool(tests),
            "live_measured": bool(live) and status in {"LIVE_MEASURED", "CERTIFIED"},
            "certified": False,  # never auto from this audit
        },
    }


def summarize(rows: list[dict[str, Any]], buckets: list[dict[str, Any]]) -> dict[str, Any]:
    by: dict[str, int] = {}
    for r in rows:
        by[r["status_max"]] = by.get(r["status_max"], 0) + 1
    coded = sum(1 for r in rows if r["pipeline"]["coded"])
    tested = sum(1 for r in rows if r["pipeline"]["tested"])
    live = sum(1 for r in rows if r["pipeline"]["live_measured"])
    open_n = sum(1 for r in rows if r.get("open"))
    return {
        "registered_rules": len(rows),
        "by_status_max": by,
        "coded": coded,
        "tested": tested,
        "live_measured": live,
        "certified": 0,
        "open_flagged": open_n,
        "unmapped_buckets": len(buckets),
        "coverage_note": "18 registered rows mapped at lineage depth; corpus markers still unmapped (see R340)",
        "certified_100": False,
    }


def main() -> int:
    LOG.mkdir(parents=True, exist_ok=True)
    reg = json.loads((ROOT / "rules" / "rule_registry.json").read_text())
    rules = reg.get("rules") or []
    rows = []
    missing_curation = []
    for rule in rules:
        rid = rule.get("rule_id")
        if rid not in CURATED:
            missing_curation.append(rid)
            rows.append(
                {
                    "rule_id": rid,
                    "kind": "RULE",
                    "canonical_text": rule.get("title"),
                    "sources": ["rules/rule_registry.json"],
                    "code": [],
                    "tests": [],
                    "live_evidence": [],
                    "status_max": "REGISTERED",
                    "open": True,
                    "notes": "no curated divergence row yet",
                    "pipeline": {
                        "decided": True,
                        "registered": True,
                        "coded": False,
                        "tested": False,
                        "live_measured": False,
                        "certified": False,
                    },
                }
            )
        else:
            rows.append(build_row(rule, CURATED[rid]))

    # Attach R340 corpus numbers if present
    corpus = {}
    cov_path = ROOT / "rules" / "rule_coverage.json"
    if cov_path.is_file():
        corpus = json.loads(cov_path.read_text())

    doc = {
        "protocol": "r341-rule-divergence-matrix-v1",
        "ts_ns": time.time_ns(),
        "registry_version": reg.get("version"),
        "levels": LEVELS,
        "honest": {
            "registered_neq_corpus": True,
            "six_levels_not_collapsed": True,
            "no_auto_certified_100": True,
            "simulated_neq_live": True,
        },
        "corpus_snapshot": {
            "registered_rules": (corpus.get("registry") or {}).get("registered_rules"),
            "numbered_entry_sum": (corpus.get("corpus_markers") or {}).get("numbered_entry_sum"),
            "unmapped_estimate": (corpus.get("registry_coverage") or {}).get("unmapped_estimate"),
        },
        "matrix": rows,
        "unmapped_buckets": UNMAPPED_BUCKETS,
        "summary": summarize(rows, UNMAPPED_BUCKETS),
        "missing_curation": missing_curation,
        "certified_100": False,
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    (LOG / "divergence_matrix.json").write_text(json.dumps(doc, indent=2) + "\n")
    (LOG / "summary.json").write_text(json.dumps(doc["summary"], indent=2) + "\n")
    print(json.dumps({"summary": doc["summary"], "missing_curation": missing_curation, "out": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
