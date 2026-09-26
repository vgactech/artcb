"""Tests R485 — Canonical Language Registry — résolution divergence 14/16 langues.

≥ 12 tests couvrant :
  - Chargement du registre canonique depuis LANGUAGE_REGISTRY_CANONICAL.json
  - get_supported_isos() : 16 langues attendues
  - get_language_state() : champs clés par langue
  - get_summary() : champs obligatoires + invariants
  - assert_registry_sha() : vérification SHA-256
  - get_divergences() : 8 langues divergentes attendues
  - get_by_lexicon_status() : PARTIAL vs NOT_STARTED
  - get_g10_languages() : langues prioritaires G10
  - get_r471_resolution_table() : tri décroissant
  - Invariants CERTIFIED_100=False + unique_human_proven=False
  - Divergences connues AR/DE/ID/JA/KO/PL/TR/LA

Règles ARTCB :
  - Mode DEBUG
  - CERTIFIED_100 = False — invariant absolu
  - Jamais déclarer 'N langues' sans vérifier le registre canonique
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.artcb.language.canonical_registry import (
    MODULE_VERSION,
    CERTIFIED_100,
    UNIQUE_HUMAN_PROVEN,
    CanonicalLanguageRegistry,
    LanguageState,
    CanonicalRegistrySummary,
    get_registry,
    get_supported_isos,
    get_language_state,
    get_language_registry_sha,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL_FILE = _REPO_ROOT / "rules" / "LANGUAGE_REGISTRY_CANONICAL.json"


# ─── T01 — Module version présent ─────────────────────────────────────────────
def test_T01_module_version():
    """T01 : MODULE_VERSION présent et semver X.Y.Z."""
    assert MODULE_VERSION
    assert len(MODULE_VERSION.split(".")) == 3


# ─── T02 — Invariants immuables au niveau module ─────────────────────────────
def test_T02_module_invariants():
    """T02 : CERTIFIED_100=False et UNIQUE_HUMAN_PROVEN=False au niveau module."""
    assert CERTIFIED_100 is False
    assert UNIQUE_HUMAN_PROVEN is False


# ─── T03 — Fichier canonique présent ─────────────────────────────────────────
def test_T03_canonical_file_exists():
    """T03 : rules/LANGUAGE_REGISTRY_CANONICAL.json existe et est valide JSON."""
    assert _CANONICAL_FILE.exists(), f"Fichier absent: {_CANONICAL_FILE}"
    data = json.loads(_CANONICAL_FILE.read_text(encoding="utf-8"))
    assert "_meta" in data
    assert "languages" in data
    assert "summary" in data


# ─── T04 — Chargement 16 langues ─────────────────────────────────────────────
def test_T04_registry_loads_16_languages():
    """T04 : Le registre charge exactement 16 langues."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    isos = reg.get_supported_isos()
    assert len(isos) == 16, f"Attendu 16 langues, obtenu {len(isos)}: {isos}"


# ─── T05 — get_supported_isos() contient les attendus ─────────────────────────
def test_T05_supported_isos_content():
    """T05 : get_supported_isos() contient les 16 ISO attendus du corpus R471."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    isos = set(reg.get_supported_isos())
    # Les 16 langues R471
    expected = {"fr", "en", "es", "pt", "pt-BR", "it", "ru", "zh",
                "ar", "de", "id", "ja", "ko", "pl", "tr", "la"}
    assert expected == isos, f"Écart: {expected.symmetric_difference(isos)}"


# ─── T06 — get_language_state() fr — langue primaire ─────────────────────────
def test_T06_language_state_fr():
    """T06 : Langue primaire 'fr' — champs clés présents et cohérents."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    state = reg.get_language_state("fr")
    assert state is not None, "Langue 'fr' absente du registre"
    assert state.iso == "fr"
    assert state.concept_lexicon_status == "PARTIAL"
    assert state.r471_resolved == 446
    assert state.r471_entries == 784019
    assert state.g10_target is True
    assert state.has_divergence is False  # fr est cohérente


# ─── T07 — get_language_state() ar — divergence confirmée ────────────────────
def test_T07_language_state_ar_divergence():
    """T07 : Langue 'ar' — divergence registry NOT_STARTED mais R471 resolved>0."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    state = reg.get_language_state("ar")
    assert state is not None, "Langue 'ar' absente du registre"
    assert state.artcd_registry_status == "NOT_STARTED"
    assert state.r471_resolved == 449  # R471 a bien résolu des entrées
    assert state.has_divergence is True, "Divergence ar doit être True"
    assert "NOT_STARTED" in state.divergence_note or "NOT_STARTED" in state.artcd_registry_note or "CONFIRMED" in state.divergence_note


# ─── T08 — get_language_state() la — absent du registre officiel ──────────────
def test_T08_language_state_la_not_in_registry():
    """T08 : Latin 'la' — absent de artcd_language_registry.json mais présent ici."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    state = reg.get_language_state("la")
    assert state is not None, "Latin 'la' absent du registre canonique"
    assert state.artcd_registry_status == "NOT_IN_REGISTRY"
    assert state.r471_resolved == 516
    assert state.has_divergence is True
    assert state.g10_target is False  # philologique, non prioritaire


# ─── T09 — get_summary() invariants ──────────────────────────────────────────
def test_T09_summary_invariants():
    """T09 : CanonicalRegistrySummary — invariants certified_100=False."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    summary = reg.get_summary()
    assert isinstance(summary, CanonicalRegistrySummary)
    assert summary.certified_100 is False
    assert summary.unique_human_proven is False
    assert summary.total_declared == 16
    assert summary.r471_total_entries == 21484106
    assert summary.r471_total_resolved == 13779
    assert summary.r471_global_resolution_rate_pct == pytest.approx(0.064136, abs=0.001)


# ─── T10 — get_summary() sha présent ─────────────────────────────────────────
def test_T10_summary_sha():
    """T10 : summary contient un SHA-256 non vide de 64 hex."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    summary = reg.get_summary()
    assert len(summary.registry_sha) == 64
    assert all(c in "0123456789abcdef" for c in summary.registry_sha)


# ─── T11 — assert_registry_sha() — SHA valide ────────────────────────────────
def test_T11_assert_registry_sha_valid():
    """T11 : assert_registry_sha() retourne True pour le SHA réel du fichier."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    real_sha = hashlib.sha256(_CANONICAL_FILE.read_bytes()).hexdigest()
    assert reg.assert_registry_sha(real_sha) is True


# ─── T12 — assert_registry_sha() — SHA invalide ──────────────────────────────
def test_T12_assert_registry_sha_invalid():
    """T12 : assert_registry_sha() retourne False pour un SHA incorrect."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    assert reg.assert_registry_sha("a" * 64) is False


# ─── T13 — get_divergences() — 8 langues divergentes ────────────────────────
def test_T13_divergences_count():
    """T13 : 8 divergences confirmées (AR/DE/ID/JA/KO/PL/TR/LA)."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    divs = reg.get_divergences()
    div_isos = {d.iso for d in divs}
    expected_divergent = {"ar", "de", "id", "ja", "ko", "pl", "tr", "la"}
    assert expected_divergent == div_isos, f"Divergences attendues: {expected_divergent}, obtenues: {div_isos}"


# ─── T14 — get_by_lexicon_status() PARTIAL ────────────────────────────────────
def test_T14_by_lexicon_status_partial():
    """T14 : get_by_lexicon_status('PARTIAL') retourne les 7 langues PARTIAL."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    partial = reg.get_by_lexicon_status("PARTIAL")
    partial_isos = {lang.iso for lang in partial}
    # fr, en, es, pt, pt-BR, it, ru, zh, ar, de, id, ja, ko, pl, tr, la
    # Tous ont concept_lexicon_status=PARTIAL dans le registre
    assert len(partial) >= 7, f"Au moins 7 langues PARTIAL attendues, obtenu {len(partial)}"
    assert "fr" in partial_isos
    assert "en" in partial_isos


# ─── T15 — get_g10_languages() ────────────────────────────────────────────────
def test_T15_g10_languages():
    """T15 : get_g10_languages() retourne au moins 10 langues G10."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    g10 = reg.get_g10_languages()
    g10_isos = {lang.iso for lang in g10}
    assert len(g10) >= 10, f"Au moins 10 langues G10, obtenu {len(g10)}"
    # la et pt-BR ne sont PAS G10
    assert "la" not in g10_isos
    assert "pt-BR" not in g10_isos
    # fr, en, es, ar, de, id, ja, ko, pl, tr, ru, zh, it, pt sont G10
    for iso in ["fr", "en", "es", "ar", "de", "ja"]:
        assert iso in g10_isos, f"{iso} doit être G10"


# ─── T16 — get_r471_resolution_table() trié ───────────────────────────────────
def test_T16_r471_resolution_table_sorted():
    """T16 : get_r471_resolution_table() est trié par taux décroissant."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    table = reg.get_r471_resolution_table()
    assert len(table) == 16
    rates = [row["r471_resolution_rate_pct"] for row in table]
    assert rates == sorted(rates, reverse=True), "Table non triée par taux décroissant"
    # tr doit être premier (0.2205%)
    assert table[0]["iso"] == "tr"


# ─── T17 — get_language_registry_sha() cohérent ───────────────────────────────
def test_T17_get_language_registry_sha():
    """T17 : get_language_registry_sha() retourne le SHA du fichier canonique."""
    sha = get_language_registry_sha()
    expected = hashlib.sha256(_CANONICAL_FILE.read_bytes()).hexdigest()
    assert sha == expected


# ─── T18 — Fonctions de commodité cohérentes ──────────────────────────────────
def test_T18_convenience_functions():
    """T18 : get_supported_isos() et get_language_state() = raccourcis cohérents."""
    isos_direct = get_supported_isos()
    isos_via_reg = get_registry().get_supported_isos()
    assert set(isos_direct) == set(isos_via_reg)

    state_fr = get_language_state("fr")
    assert state_fr is not None
    assert state_fr.iso == "fr"


# ─── T19 — to_dict R471 resolution cohérence ──────────────────────────────────
def test_T19_r471_total_coherence():
    """T19 : somme des r471_resolved par langue == r471_total_resolved du summary."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    total_from_langs = sum(
        reg.get_language_state(iso).r471_resolved
        for iso in reg.get_supported_isos()
    )
    summary = reg.get_summary()
    assert total_from_langs == summary.r471_total_resolved, (
        f"Incohérence: somme par langue {total_from_langs} != total {summary.r471_total_resolved}"
    )


# ─── T20 — Absences dans l'ancien registre documentées ───────────────────────
def test_T20_old_registry_divergences_documented():
    """T20 : les 8 langues divergentes ont toutes un r471_resolved > 0."""
    reg = CanonicalLanguageRegistry(_CANONICAL_FILE)
    for div in reg.get_divergences():
        assert div.r471_resolved > 0, (
            f"Langue {div.iso} marquée divergente mais r471_resolved=0 — incohérence"
        )
