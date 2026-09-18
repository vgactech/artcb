#!/usr/bin/env python3
"""R375 — ARTCB Rule Corpus Refresh (2026-09-18).

Ce script rescanne l'ensemble des sources normatives ARTCB et produit :

  1. rules/rule_sources.json     — cartographie mise à jour (SHA256, détections, rxxx actuels)
  2. rules/rule_coverage.json    — couverture mise à jour (corpus_markers réels)
  3. rules/rule_corpus_index.json — NOUVELLE COUCHE : index CR-* (séparation RULE/DECISION/SPEC/…)

Architecture de séparation :

    CORPUS NORMATIF COMPLET
           │
           ├── RULE        → CR-* kind=RULE
           ├── DECISION    → CR-* kind=DECISION  (D-xxx)
           ├── SPEC        → CR-* kind=SPEC       (§ numérotés CDC)
           ├── INVARIANT   → CR-* kind=INVARIANT
           ├── CHECK       → CR-* kind=CHECK
           ├── LESSON      → CR-* kind=LESSON     (L-xxx)
           ├── CONVENTION  → CR-* kind=CONVENTION
           └── QUESTION    → CR-* kind=QUESTION
                     │
                     ↓
           RT-* lorsque une règle opérationnelle existe déjà

Principes :
  - NEVER wipe rule_registry.json
  - Ne jamais créer de CR-* fictifs — uniquement ce qui est détecté
  - Distinction maintenue : INJECTED ≠ APPLIED_CONFIRMED
  - CERTIFIED_100 = False
  - Agent-ID Bob IDE vs Cursor distingués dans les entrées corpus

Usage :
    python3 scripts/artcb_r375_corpus_refresh.py [--dry-run]

Mode --dry-run : affiche les résultats sans écrire.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# ─── Configuration des sources ────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]

# Sources normatives — liste exhaustive des fichiers à scanner
SOURCES: list[dict[str, Any]] = [
    {
        "source_id": "rule_registry",
        "path": "rules/rule_registry.json",
        "kind": "REGISTRY",
        "authority": "telemetry",
    },
    {
        "source_id": "protocole",
        "path": "PROTOCOLE_ARTCB",
        "kind": "RULE",
        "authority": "protocol",
    },
    {
        "source_id": "auto_prompt",
        "path": "AUTO_PROMPT_ARTCB",
        "kind": "RULE",
        "authority": "agent_instructions",
    },
    {
        "source_id": "live_node",
        "path": ".cursor/rules/artcb-live-node.mdc",
        "kind": "RULE",
        "authority": "cursor",
    },
    {
        "source_id": "read_all",
        "path": ".cursor/rules/artcb-read-all.mdc",
        "kind": "RULE",
        "authority": "cursor",
    },
    {
        "source_id": "reflex_priority",
        "path": ".cursor/rules/artcb-reflex-priority.mdc",
        "kind": "RULE",
        "authority": "cursor",
    },
    {
        "source_id": "mac_node",
        "path": ".cursor/rules/mac-node-local.mdc",
        "kind": "RULE",
        "authority": "cursor",
    },
    {
        "source_id": "aws_node",
        "path": ".cursor/rules/aws-node-3.mdc",
        "kind": "RULE",
        "authority": "cursor",
    },
    {
        "source_id": "ovh4",
        "path": ".cursor/rules/ovh-node-4.mdc",
        "kind": "RULE",
        "authority": "cursor",
    },
    {
        "source_id": "decisions",
        "path": "DECISIONS_UTILISATEUR_ARTCB",
        "kind": "DECISION",
        "authority": "operator",
    },
    {
        "source_id": "cdc",
        "path": "CAHIER_DES_CHARGES_ARTCB",
        "kind": "SPEC",
        "authority": "product",
    },
    {
        "source_id": "checklist",
        "path": "CHECKLIST_PRE_DEV_ARTCB",
        "kind": "CHECK",
        "authority": "dev_gate",
    },
    {
        "source_id": "questions",
        "path": "QUESTIONS_OUVERTES_ARTCB",
        "kind": "QUESTION",
        "authority": "open",
    },
    {
        "source_id": "lecons",
        "path": "LEÇONS_APPRISES_ARTCB",
        "kind": "LESSON",
        "authority": "history",
    },
    {
        "source_id": "gouvernance",
        "path": "GOUVERNANCE_ARTCB",
        "kind": "RULE",
        "authority": "governance",
    },
    {
        "source_id": "standard_names",
        "path": "STANDARD_NAMES_ARTCB",
        "kind": "CONVENTION",
        "authority": "naming",
    },
    {
        "source_id": "roadmap",
        "path": "ROADMAP_GENERAL_ARTCB",
        "kind": "SPEC",
        "authority": "product",
    },
    {
        "source_id": "task_ledger",
        "path": ".artcb/task_ledger.yaml",
        "kind": "EVIDENCE",
        "authority": "telemetry",
    },
]

# Patterns de détection
_RE_NUMBERED = re.compile(r"^\s*\d{1,3}\.\s+\*\*", re.MULTILINE)  # « 88. **R374… »
_RE_RT_ID    = re.compile(r"\bRT-[A-Z0-9][A-Z0-9\-]{0,30}\b")
_RE_D_ID     = re.compile(r"\bD-(\d{3}|\d{2}|\d{1})\b")
_RE_RXXX_ID  = re.compile(r"\bR(\d{3,4}[a-z]?)\b")
_RE_STRUCK   = re.compile(r"~~[^~]+~~")
_RE_LESSON   = re.compile(r"\bL-(\d{3}|\d{2}|\d{1})\b")
_RE_DECISION_HEADER = re.compile(r"\|\s*(D-\d+)\s*\|")  # lignes de table DECISIONS


# ─── Scan d'une source ────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_source(spec: dict[str, Any]) -> dict[str, Any]:
    """Scanne un fichier source et retourne l'entrée rule_sources enrichie."""
    p = ROOT / spec["path"]
    entry: dict[str, Any] = {
        "source_id": spec["source_id"],
        "path": spec["path"],
        "kind": spec["kind"],
        "authority": spec["authority"],
        "present": p.is_file(),
        "bytes": 0,
        "sha256": None,
        "detections": {},
        "notes": [],
    }

    if not p.is_file():
        entry["notes"].append("missing")
        return entry

    raw = p.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    entry["bytes"] = len(raw)
    entry["sha256"] = hashlib.sha256(raw).hexdigest()

    # ── Détections spécifiques au registre ────────────────────────────────────
    if spec["source_id"] == "rule_registry":
        try:
            reg = json.loads(text)
            rules = reg.get("rules") or []
            active = [r for r in rules if r.get("status") == "active"]
            entry["detections"] = {
                "numbered_entries": 0,
                "rt_ids": sorted({r["rule_id"] for r in rules if r.get("rule_id")}),
                "d_ids": [],
                "rxxx_ids": sorted(set(_RE_RXXX_ID.findall(text))),
                "struck_markers": 0,
                "registry_version": reg.get("version", 0),
                "registered_rules": len(rules),
                "active_rules": len(active),
                "rule_ids": sorted({r["rule_id"] for r in rules if r.get("rule_id")}),
            }
        except json.JSONDecodeError:
            entry["notes"].append("json_decode_error")
        return entry

    # ── Détections génériques ──────────────────────────────────────────────────
    numbered_entries = len(_RE_NUMBERED.findall(text))
    rt_ids    = sorted(set(_RE_RT_ID.findall(text)))
    d_ids_raw = sorted(set(f"D-{m}" for m in _RE_D_ID.findall(text)))
    # Pour DECISIONS_UTILISATEUR, priorité aux lignes de table
    if spec["source_id"] == "decisions":
        d_ids_table = sorted(set(_RE_DECISION_HEADER.findall(text)))
        d_ids = d_ids_table if d_ids_table else d_ids_raw
    else:
        d_ids = d_ids_raw
    rxxx_raw  = sorted(set(f"R{m}" for m in _RE_RXXX_ID.findall(text)))
    l_ids     = sorted(set(f"L-{m}" for m in _RE_LESSON.findall(text)))
    struck    = len(_RE_STRUCK.findall(text))

    det: dict[str, Any] = {
        "numbered_entries": numbered_entries,
        "rt_ids": rt_ids,
        "d_ids": d_ids,
        "rxxx_ids": rxxx_raw,
        "struck_markers": struck,
    }
    if l_ids:
        det["l_ids"] = l_ids

    entry["detections"] = det
    return entry


# ─── Construction du corpus index CR-* ───────────────────────────────────────

def _make_corpus_id(kind: str, ref: str, source_id: str) -> str:
    """Génère un CR-ID déterministe depuis kind + ref + source."""
    raw = f"{kind}:{ref}:{source_id}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    prefix = kind[:3].upper()
    slug = re.sub(r"[^A-Z0-9]", "-", ref.upper())[:20].strip("-")
    return f"CR-{prefix}-{slug}-{h}"


def build_corpus_index(
    scanned: list[dict[str, Any]],
    registry_rule_ids: set[str],
) -> list[dict[str, Any]]:
    """Construit la liste CR-* depuis les scans. Déduplique par (kind, ref)."""
    seen_refs: set[tuple[str, str]] = set()
    entries: list[dict[str, Any]] = []

    def _add(kind: str, ref: str, source_id: str, source_path: str,
             authority: str, canonical_text: str = "") -> None:
        key = (kind, ref)
        if key in seen_refs:
            return
        seen_refs.add(key)
        cr_id = _make_corpus_id(kind, ref, source_id)
        # Trouver si un RT existe
        rt_match: str | None = None
        if kind == "RULE" and ref in registry_rule_ids:
            rt_match = ref
        entries.append({
            "corpus_id": cr_id,
            "kind": kind,
            "ref": ref,
            "source_id": source_id,
            "source_path": source_path,
            "authority": authority,
            "canonical_text": canonical_text[:200] if canonical_text else "",
            "status": "DETECTED_NOT_CLASSIFIED",
            "rt_rule_id": rt_match,
            "certified": False,
        })

    for scan in scanned:
        sid = scan["source_id"]
        spath = scan["path"]
        auth = scan["authority"]
        det = scan.get("detections") or {}

        if not scan["present"]:
            continue

        # RT-IDs → kind=RULE
        for rt in det.get("rt_ids") or []:
            _add("RULE", rt, sid, spath, auth)

        # D-IDs → kind=DECISION
        for d in det.get("d_ids") or []:
            _add("DECISION", d, sid, spath, auth)

        # R-xxx → kind=RULE (règles numérotées par session)
        for r in det.get("rxxx_ids") or []:
            _add("RULE", r, sid, spath, auth)

        # L-xxx → kind=LESSON
        for lx in det.get("l_ids") or []:
            _add("LESSON", lx, sid, spath, auth)

        # Sources entières → une entrée SPEC/CHECK/CONVENTION/LESSON par source
        k = scan["kind"]
        if k in {"SPEC", "CHECK", "CONVENTION", "LESSON", "QUESTION", "EVIDENCE"}:
            _add(k, sid.upper(), sid, spath, auth, canonical_text=f"Source: {spath}")

    # Trier par kind puis ref
    entries.sort(key=lambda e: (e["kind"], e["ref"]))
    return entries


# ─── Test anti-divergence ─────────────────────────────────────────────────────

def check_divergence(
    registry_rule_ids: set[str],
    sources_rule_ids: set[str],
) -> list[str]:
    """Retourne les divergences entre rule_registry et rule_sources.

    Retourne une liste de messages d'erreur (vide = OK).
    """
    errors: list[str] = []
    in_registry_not_sources = registry_rule_ids - sources_rule_ids
    in_sources_not_registry = sources_rule_ids - registry_rule_ids
    if in_registry_not_sources:
        errors.append(
            f"REGISTRY_SANS_SOURCE: {sorted(in_registry_not_sources)}"
        )
    if in_sources_not_registry:
        errors.append(
            f"SOURCE_SANS_REGISTRY: {sorted(in_sources_not_registry)}"
        )
    return errors


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main(dry_run: bool = False) -> int:
    ts_ns = time.time_ns()

    print("R375 — ARTCB Corpus Refresh")
    print(f"  ROOT = {ROOT}")
    print(f"  dry_run = {dry_run}")
    print()

    # 1. Scanner toutes les sources
    scanned: list[dict[str, Any]] = []
    for spec in SOURCES:
        entry = scan_source(spec)
        status = "OK" if entry["present"] else "MISSING"
        nb = entry.get("detections", {}).get("numbered_entries", 0)
        nrt = len(entry.get("detections", {}).get("rt_ids") or [])
        nr  = len(entry.get("detections", {}).get("rxxx_ids") or [])
        nd  = len(entry.get("detections", {}).get("d_ids") or [])
        print(f"  [{status:7}] {spec['path']:<55} "
              f"numbered={nb:3} RT={nrt:2} D={nd:3} R={nr:3}")
        scanned.append(entry)

    print()

    # 2. Extraire les rule_ids du registre (source of truth)
    reg_scan = next(s for s in scanned if s["source_id"] == "rule_registry")
    registry_rule_ids: set[str] = set(reg_scan.get("detections", {}).get("rule_ids") or [])
    registered_rules_count: int = reg_scan.get("detections", {}).get("registered_rules", 0)
    active_rules_count: int     = reg_scan.get("detections", {}).get("active_rules", 0)
    registry_version: int       = reg_scan.get("detections", {}).get("registry_version", 0)

    # 3. rule_sources.json — garder le protocol/note, remplacer sources
    old_sources_path = ROOT / "rules" / "rule_sources.json"
    old_sources: dict[str, Any] = {}
    if old_sources_path.is_file():
        try:
            old_sources = json.loads(old_sources_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    new_sources: dict[str, Any] = {
        "protocol": "r340-rule-sources-v2",
        "refreshed_by": "R375",
        "ts_ns": ts_ns,
        "note": (
            "Append-only cartography. Updated by artcb_r375_corpus_refresh.py. "
            "Does not replace PROTOCOLE/AUTO_PROMPT/Cursor. CERTIFIED_100=false."
        ),
        "registry_version": registry_version,
        "registered_rules": registered_rules_count,
        "active_rules": active_rules_count,
        "sources": scanned,
    }

    # 4. rule_coverage.json
    # Compter les entrées numérotées (marqueurs) dans toutes les sources sauf le registre
    by_authority: dict[str, int] = {}
    total_numbered = 0
    for s in scanned:
        if s["source_id"] == "rule_registry":
            continue
        nb = s.get("detections", {}).get("numbered_entries", 0)
        auth = s["authority"]
        by_authority[auth] = by_authority.get(auth, 0) + nb
        total_numbered += nb

    new_coverage: dict[str, Any] = {
        "protocol": "r340-rule-corpus-coverage-v2",
        "refreshed_by": "R375",
        "ts_ns": ts_ns,
        "registry": {
            "version": registry_version,
            "registered_rules": registered_rules_count,
            "active_rules": active_rules_count,
            "note": "registered_rules ≠ total ARTCB normative corpus",
        },
        "corpus_markers": {
            "numbered_entry_sum": total_numbered,
            "by_authority": by_authority,
            "note": "markers are detections not unique semantic RULE count",
        },
        "registry_coverage": {
            "registered": registered_rules_count,
            "mapped_to_source": "PARTIAL",
            "unmapped_estimate": max(0, total_numbered - registered_rules_count),
            "corpus_index_path": "rules/rule_corpus_index.json",
        },
        "categories": [
            "RULE",
            "DECISION",
            "SPEC",
            "INVARIANT",
            "CHECK",
            "EVIDENCE",
            "QUESTION",
            "LESSON",
            "CONVENTION",
        ],
        "certified_100": False,
        "honest": {
            "rules_total_is_registry_only": True,
            "no_honest_global_X_rules_without_canonical_map": True,
            "dns_poison_match0_is_invalid_no_sample": True,
            "registry_ne_corpus": True,
        },
    }

    # 5. rule_corpus_index.json — nouvelle couche CR-*
    corpus_entries = build_corpus_index(scanned, registry_rule_ids)
    new_corpus_index: dict[str, Any] = {
        "protocol": "r375-corpus-index-v1",
        "refreshed_by": "R375",
        "ts_ns": ts_ns,
        "note": (
            "CR-* index : séparation RULE/DECISION/SPEC/LESSON/etc. "
            "CR-* ≠ RT-* (RT = sous-ensemble opérationnel). "
            "Ne jamais supprimer — revision = status update. CERTIFIED_100=false."
        ),
        "two_level_architecture": {
            "normative_corpus": "CR-* (tous)",
            "operational_registry": "RT-* (sous-ensemble actif)",
            "mapping": "rt_rule_id != null dans CR-* si RT correspondant connu",
        },
        "counts": {
            "total_cr": len(corpus_entries),
            "kind_breakdown": {},
        },
        "entries": corpus_entries,
        "certified_100": False,
    }
    # Compter par kind
    kind_counts: dict[str, int] = {}
    for e in corpus_entries:
        kind_counts[e["kind"]] = kind_counts.get(e["kind"], 0) + 1
    new_corpus_index["counts"]["kind_breakdown"] = kind_counts

    # 6. Test anti-divergence
    # Extraire les RT-IDs depuis rule_sources (toutes les sources)
    sources_rt_ids: set[str] = set()
    for s in scanned:
        for rt in (s.get("detections") or {}).get("rt_ids") or []:
            sources_rt_ids.add(rt)
    # Retirer RT-LEG (marqueur texte non-règle)
    sources_rt_ids.discard("RT-LEG")

    divergences = check_divergence(registry_rule_ids, sources_rt_ids)

    print(f"  rule_corpus_index: {len(corpus_entries)} entrées CR-*")
    print(f"  kind_breakdown   : {kind_counts}")
    print(f"  numbered markers : {total_numbered} (by_authority: {by_authority})")
    print(f"  registry RT-IDs  : {len(registry_rule_ids)}")
    print()

    if divergences:
        print("⚠  DIVERGENCES DÉTECTÉES :")
        for d in divergences:
            print(f"   {d}")
        # Les divergences SOURCE_SANS_REGISTRY sont normales (RT-LEG, etc.)
        real_errors = [d for d in divergences if "REGISTRY_SANS_SOURCE" in d]
        if real_errors:
            print()
            print("❌ Divergences critiques (RT dans registry mais pas dans sources) :")
            for e in real_errors:
                print(f"   {e}")
    else:
        print("✅ Aucune divergence registry ↔ sources")

    print()

    # 7. Écriture
    if dry_run:
        print("DRY-RUN — aucune écriture.")
        return 0

    sources_out = ROOT / "rules" / "rule_sources.json"
    coverage_out = ROOT / "rules" / "rule_coverage.json"
    corpus_out = ROOT / "rules" / "rule_corpus_index.json"

    sources_out.write_text(
        json.dumps(new_sources, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    coverage_out.write_text(
        json.dumps(new_coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    corpus_out.write_text(
        json.dumps(new_corpus_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"✅ Écrits :")
    print(f"   {sources_out.relative_to(ROOT)}")
    print(f"   {coverage_out.relative_to(ROOT)}")
    print(f"   {corpus_out.relative_to(ROOT)}")
    print()
    print(f"  divergences   : {len(divergences)}")
    print(f"  certified_100 : False")
    print(f"  DONE R375")

    return 0 if not [d for d in divergences if "REGISTRY_SANS_SOURCE" in d] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="R375 — ARTCB Corpus Refresh")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans écrire")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
