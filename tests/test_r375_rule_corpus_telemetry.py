"""Tests R375 — Rule Corpus Telemetry v2 : anti-divergence + intégrité.

Suite de tests garantissant que :
  T01 : rule_sources.json existe et est valide JSON
  T02 : rule_sources.json — registered_rules == 20 (synchro registry)
  T03 : rule_sources.json — active_rules == registered_rules
  T04 : rule_sources.json — reflex_priority présent (source ajoutée R375)
  T05 : rule_sources.json — aucun source_id dupliqué
  T06 : rule_corpus_index.json existe et est valide JSON
  T07 : rule_corpus_index.json — total_cr > 100 (détection complète)
  T08 : rule_corpus_index.json — kind DECISION présent (D-xxx détectés)
  T09 : rule_corpus_index.json — kind RULE présent (RT-* + Rxxx)
  T10 : rule_corpus_index.json — tous les CR-IDs sont uniques
  T11 : rule_corpus_index.json — RT-* registry mappés (rt_rule_id != null pour les 20)
  T12 : rule_corpus_index.json — CERTIFIED_100 = False
  T13 : rule_coverage.json — corpus_index_path référencé
  T14 : rule_coverage.json — certified_100 = False
  T15 : rule_coverage.json — registered_rules == 20
  T16 : ANTI-DIVERGENCE : rule_registry RT-IDs ⊆ rule_sources RT-IDs détectés
  T17 : ANTI-DIVERGENCE : rule_registry RT-IDs == rule_corpus_index RT-* mappés
  T18 : rule_corpus_index — R374 présent (entrée BCH R374)
  T19 : rule_corpus_index — D-045 présent (dernière décision connue)
  T20 : rule_sources — auto_prompt a des rxxx_ids incluant R371→R374
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH    = ROOT / "rules" / "rule_sources.json"
REGISTRY_PATH   = ROOT / "rules" / "rule_registry.json"
COVERAGE_PATH   = ROOT / "rules" / "rule_coverage.json"
CORPUS_IDX_PATH = ROOT / "rules" / "rule_corpus_index.json"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sources() -> dict:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def coverage() -> dict:
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def corpus_index() -> dict:
    return json.loads(CORPUS_IDX_PATH.read_text(encoding="utf-8"))


# ─── T01 : rule_sources.json existe et est valide JSON ────────────────────────

def test_T01_rule_sources_exists_and_valid() -> None:
    assert SOURCES_PATH.is_file(), "rule_sources.json doit exister"
    data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "sources" in data


# ─── T02 : registered_rules == 20 ─────────────────────────────────────────────

def test_T02_sources_registered_rules_20(sources: dict) -> None:
    assert sources["registered_rules"] == 20, (
        f"registered_rules = {sources['registered_rules']} ≠ 20"
    )


# ─── T03 : active_rules == registered_rules ───────────────────────────────────

def test_T03_sources_active_eq_registered(sources: dict) -> None:
    assert sources["active_rules"] == sources["registered_rules"]


# ─── T04 : reflex_priority présent ────────────────────────────────────────────

def test_T04_sources_has_reflex_priority(sources: dict) -> None:
    ids = {s["source_id"] for s in sources["sources"]}
    assert "reflex_priority" in ids, (
        "reflex_priority (.cursor/rules/artcb-reflex-priority.mdc) doit être dans sources"
    )


# ─── T05 : aucun source_id dupliqué ───────────────────────────────────────────

def test_T05_sources_no_duplicate_ids(sources: dict) -> None:
    ids = [s["source_id"] for s in sources["sources"]]
    assert len(ids) == len(set(ids)), f"source_ids dupliqués : {ids}"


# ─── T06 : rule_corpus_index.json existe ─────────────────────────────────────

def test_T06_corpus_index_exists() -> None:
    assert CORPUS_IDX_PATH.is_file(), "rule_corpus_index.json doit exister (créé par R375)"
    data = json.loads(CORPUS_IDX_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "entries" in data


# ─── T07 : total_cr > 100 ─────────────────────────────────────────────────────

def test_T07_corpus_index_total_cr(corpus_index: dict) -> None:
    total = corpus_index["counts"]["total_cr"]
    assert total > 100, f"total_cr = {total} — devrait dépasser 100"


# ─── T08 : kind DECISION présent ─────────────────────────────────────────────

def test_T08_corpus_index_has_decisions(corpus_index: dict) -> None:
    kinds = {e["kind"] for e in corpus_index["entries"]}
    assert "DECISION" in kinds, "Aucune entrée DECISION dans corpus_index"
    decisions = [e for e in corpus_index["entries"] if e["kind"] == "DECISION"]
    assert len(decisions) >= 45, f"Moins de 45 décisions D-xxx détectées : {len(decisions)}"


# ─── T09 : kind RULE présent ─────────────────────────────────────────────────

def test_T09_corpus_index_has_rules(corpus_index: dict) -> None:
    kinds = {e["kind"] for e in corpus_index["entries"]}
    assert "RULE" in kinds, "Aucune entrée RULE dans corpus_index"
    rules = [e for e in corpus_index["entries"] if e["kind"] == "RULE"]
    assert len(rules) > 50, f"Moins de 50 entrées RULE : {len(rules)}"


# ─── T10 : tous les CR-IDs sont uniques ──────────────────────────────────────

def test_T10_corpus_index_unique_cr_ids(corpus_index: dict) -> None:
    cr_ids = [e["corpus_id"] for e in corpus_index["entries"]]
    assert len(cr_ids) == len(set(cr_ids)), "CR-IDs dupliqués dans corpus_index"


# ─── T11 : tous les RT-* du registre sont mappés dans corpus_index ───────────

def test_T11_corpus_index_all_registry_rt_mapped(
    registry: dict, corpus_index: dict
) -> None:
    registry_rt_ids = {r["rule_id"] for r in registry.get("rules", []) if r.get("rule_id")}
    mapped_rt_ids = {
        e["rt_rule_id"]
        for e in corpus_index["entries"]
        if e.get("rt_rule_id") is not None
    }
    missing = registry_rt_ids - mapped_rt_ids
    assert not missing, (
        f"RT-IDs dans registry mais absent du corpus_index mapping : {sorted(missing)}"
    )


# ─── T12 : CERTIFIED_100 = False ─────────────────────────────────────────────

def test_T12_corpus_index_certified_false(corpus_index: dict) -> None:
    assert corpus_index["certified_100"] is False


# ─── T13 : rule_coverage.json référence corpus_index_path ────────────────────

def test_T13_coverage_references_corpus_index(coverage: dict) -> None:
    path = coverage["registry_coverage"].get("corpus_index_path")
    assert path == "rules/rule_corpus_index.json", (
        f"corpus_index_path manquant ou incorrect : {path}"
    )


# ─── T14 : rule_coverage.json — certified_100 = False ────────────────────────

def test_T14_coverage_certified_false(coverage: dict) -> None:
    assert coverage["certified_100"] is False


# ─── T15 : rule_coverage.json — registered_rules == 20 ──────────────────────

def test_T15_coverage_registered_rules_20(coverage: dict) -> None:
    assert coverage["registry"]["registered_rules"] == 20


# ─── T16 : ANTI-DIVERGENCE registry ⊆ sources ────────────────────────────────

def test_T16_anti_divergence_registry_in_sources(
    registry: dict, sources: dict
) -> None:
    """Chaque RT-ID du registre doit être détecté dans au moins une source."""
    registry_rt_ids = {r["rule_id"] for r in registry.get("rules", []) if r.get("rule_id")}
    # Collecter tous les RT-IDs détectés dans toutes les sources
    sources_rt_ids: set[str] = set()
    for s in sources["sources"]:
        for rt in (s.get("detections") or {}).get("rt_ids") or []:
            sources_rt_ids.add(rt)
    # RT-LEG est un marqueur textuel non-règle — l'ignorer
    sources_rt_ids.discard("RT-LEG")

    missing = registry_rt_ids - sources_rt_ids
    assert not missing, (
        f"DIVERGENCE CRITIQUE : RT-IDs dans registry non trouvés dans sources : {sorted(missing)}"
    )


# ─── T17 : ANTI-DIVERGENCE corpus_index == registry ──────────────────────────

def test_T17_anti_divergence_corpus_maps_all_registry(
    registry: dict, corpus_index: dict
) -> None:
    """Le corpus_index doit mapper tous les RT-IDs du registre."""
    registry_rt_ids = {r["rule_id"] for r in registry.get("rules", []) if r.get("rule_id")}
    mapped = {
        e["rt_rule_id"]
        for e in corpus_index["entries"]
        if e.get("rt_rule_id") is not None
    }
    missing = registry_rt_ids - mapped
    assert not missing, (
        f"RT-IDs registre non mappés dans corpus_index : {sorted(missing)}"
    )


# ─── T18 : R374 présent dans corpus_index ────────────────────────────────────

def test_T18_corpus_index_has_r374(corpus_index: dict) -> None:
    refs = {e["ref"] for e in corpus_index["entries"]}
    assert "R374" in refs, "R374 (BCH ECC) absent du corpus_index"


# ─── T19 : D-045 présent dans corpus_index ───────────────────────────────────

def test_T19_corpus_index_has_d045(corpus_index: dict) -> None:
    refs = {e["ref"] for e in corpus_index["entries"]}
    assert "D-045" in refs, "D-045 (dernière décision utilisateur connue) absent du corpus_index"


# ─── T20 : auto_prompt rxxx_ids inclut R371→R374 ─────────────────────────────

def test_T20_sources_auto_prompt_has_r371_to_r374(sources: dict) -> None:
    ap = next(
        (s for s in sources["sources"] if s["source_id"] == "auto_prompt"), None
    )
    assert ap is not None, "source auto_prompt manquante dans rule_sources"
    rxxx = set(ap.get("detections", {}).get("rxxx_ids") or [])
    for r in ["R371", "R372", "R373", "R374"]:
        assert r in rxxx, (
            f"{r} absent des rxxx_ids de auto_prompt — "
            f"rule_sources.json doit être régénéré avec R375"
        )
