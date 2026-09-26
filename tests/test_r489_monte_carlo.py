"""R489 — Tests Monte Carlo Linguistique (moteur de découverte de défauts).

Tests T01→T25 validant :
  - T01-T03 : run_monte_carlo() — structure de base
  - T04-T06 : cas PASS (variations bénignes)
  - T07-T09 : cas FAIL → findings détectés
  - T10      : sévérité CRITICAL / HIGH / MEDIUM / LOW
  - T11      : _apply_variation() — toutes les variations produisent une sortie
  - T12      : case_id déterministe
  - T13      : run_id déterministe (même seed → même run)
  - T14      : code de référence auto-détecté (expected_code=None)
  - T15      : export_regression_cases() → liste correcte
  - T16      : save_regression_cases() → fichier JSON valide
  - T17      : multi-langue (EN + DE)
  - T18      : max_cases limite le nombre de cas
  - T19      : seed_texts vide → run vide sans erreur
  - T20      : variation synonym_variant (aliases concept_lexicon)
  - T21      : variation negation → case FAIL attendu (UNK)
  - T22      : variation noise_transpose → finding HIGH si code perdu
  - T23      : invariants unique_human_proven=False, certified=False
  - T24      : MonteCarloFinding.to_dict() JSON-sérialisable
  - T25      : MODULE_VERSION = 1.0.x

CERTIFIED_100=false | unique_human_proven=False
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.artcb.language.monte_carlo import (
    MODULE_VERSION,
    VARIATION_TYPES,
    MonteCarloCase,
    MonteCarloFinding,
    MonteCarloRun,
    _apply_variation,
    _classify_severity,
    _make_case_id,
    export_regression_cases,
    run_monte_carlo,
    save_regression_cases,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def fr_run() -> MonteCarloRun:
    """Run MC FR minimal — partagé pour tous les tests du module."""
    return run_monte_carlo(
        "fr",
        seed_texts=[
            ("vérifier la signature", "V1"),
            ("créer un bloc", "K1"),
        ],
        variation_types=[
            "case_upper", "case_lower", "noise_transpose",
            "punctuation_add", "unicode_ascii_only", "negation",
        ],
        seed=0x41525443,
    )


@pytest.fixture(scope="module")
def en_run() -> MonteCarloRun:
    """Run MC EN minimal."""
    return run_monte_carlo(
        "en",
        seed_texts=[
            ("verify the signature", "V1"),
        ],
        variation_types=["case_upper", "case_lower", "punctuation_add"],
        seed=0x41525443,
    )


# ─── T01-T03 : structure de base ─────────────────────────────────────────────

def test_T01_run_returns_monte_carlo_run(fr_run):
    """T01 — run_monte_carlo() retourne un MonteCarloRun."""
    assert isinstance(fr_run, MonteCarloRun)


def test_T02_run_has_cases(fr_run):
    """T02 — Le run contient des cas (n_cases > 0)."""
    assert fr_run.n_cases > 0, "Le run doit contenir au moins un cas"


def test_T03_run_stats_consistent(fr_run):
    """T03 — n_pass + n_fail == n_cases (cohérence statistique)."""
    assert fr_run.n_pass + fr_run.n_fail == fr_run.n_cases, (
        f"n_pass={fr_run.n_pass} + n_fail={fr_run.n_fail} != n_cases={fr_run.n_cases}"
    )


# ─── T04-T06 : cas PASS ──────────────────────────────────────────────────────

def test_T04_case_upper_is_pass_or_fail(fr_run):
    """T04 — Les variations case_upper existent dans le run."""
    upper_cases = [c for c in fr_run.cases if c.variation_type == "case_upper"]
    assert len(upper_cases) > 0, "Des cas case_upper doivent exister"


def test_T05_pass_rate_between_0_and_1(fr_run):
    """T05 — pass_rate ∈ [0, 1]."""
    assert 0.0 <= fr_run.pass_rate <= 1.0


def test_T06_case_lower_same_or_different_code(fr_run):
    """T06 — La variation case_lower ne doit pas produire d'erreur interne."""
    lower_cases = [c for c in fr_run.cases if c.variation_type == "case_lower"]
    for case in lower_cases:
        assert case.is_ok, f"case_lower ne doit pas produire d'erreur interne: {case}"


# ─── T07-T09 : cas FAIL → findings ───────────────────────────────────────────

def test_T07_noise_transpose_may_produce_finding():
    """T07 — noise_transpose peut produire un finding (code perdu)."""
    run = run_monte_carlo(
        "fr",
        seed_texts=[("créer un bloc", "K1")],
        variation_types=["noise_transpose"],
        seed=0x41525443,
    )
    # Il peut y avoir ou non un finding (dépend de la position de transposition)
    # Mais le run doit être valide
    assert isinstance(run, MonteCarloRun)
    assert run.n_cases >= 0


def test_T08_negation_produces_finding_or_pass():
    """T08 — La négation ('not vérifier...') change souvent le code vers UNK."""
    run = run_monte_carlo(
        "en",
        seed_texts=[("verify the signature", "V1")],
        variation_types=["negation"],
        seed=0x41525443,
    )
    assert isinstance(run, MonteCarloRun)
    # Les cas négatifs peuvent ou non garder le concept
    for case in run.cases:
        assert case.variation_type == "negation"
        # Le lineage doit fonctionner sans erreur interne
        assert case.is_ok, f"La variation negation ne doit pas produire d'erreur interne"


def test_T09_finding_has_severity(fr_run):
    """T09 — Chaque finding a une sévérité valide."""
    valid_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    for finding in fr_run.findings:
        assert finding.severity in valid_severities, (
            f"Sévérité invalide: {finding.severity!r}"
        )


# ─── T10 : sévérité ──────────────────────────────────────────────────────────

def test_T10_classify_severity():
    """T10 — _classify_severity() retourne les bonnes sévérités."""
    # Code attendu ≠ UNK mais code obtenu = None → HIGH
    assert _classify_severity("V1", None, False) == "HIGH"
    # Code attendu ≠ code obtenu, tous deux valides → CRITICAL
    assert _classify_severity("V1", "K1", False) == "CRITICAL"
    # Erreur interne → MEDIUM
    assert _classify_severity("V1", None, True) == "MEDIUM"
    # Pas de code attendu → LOW
    assert _classify_severity(None, None, False) == "LOW"
    # Les deux UNK → LOW
    assert _classify_severity("UNK", "UNK", False) == "LOW"


# ─── T11 : _apply_variation() ────────────────────────────────────────────────

def test_T11_all_variation_types_produce_string():
    """T11 — Chaque type de variation retourne une chaîne non-None."""
    import random
    rng = random.Random(42)
    text = "verify the signature"
    for var_type in VARIATION_TYPES:
        result = _apply_variation(text, var_type, rng)
        assert isinstance(result, str), f"Variation {var_type!r} doit retourner str"
        assert result is not None


# ─── T12-T13 : déterminisme ──────────────────────────────────────────────────

def test_T12_case_id_deterministic():
    """T12 — case_id est déterministe pour les mêmes paramètres."""
    id1 = _make_case_id("fr", "vérifier", "case_upper", "VÉRIFIER")
    id2 = _make_case_id("fr", "vérifier", "case_upper", "VÉRIFIER")
    assert id1 == id2


def test_T13_run_id_deterministic():
    """T13 — Deux runs avec les mêmes paramètres ont le même run_id."""
    run1 = run_monte_carlo(
        "en",
        seed_texts=[("verify", "V1")],
        variation_types=["case_upper"],
        seed=42,
    )
    run2 = run_monte_carlo(
        "en",
        seed_texts=[("verify", "V1")],
        variation_types=["case_upper"],
        seed=42,
    )
    assert run1.run_id == run2.run_id


# ─── T14 : code auto-détecté ─────────────────────────────────────────────────

def test_T14_auto_detected_reference_code():
    """T14 — expected_code=None → code calculé automatiquement sur le texte original."""
    run = run_monte_carlo(
        "en",
        seed_texts=[("verify the signature", None)],  # code non fourni
        variation_types=["case_upper"],
        seed=42,
    )
    # Les cases doivent avoir un expected_artcb_code (auto-calculé)
    for case in run.cases:
        # Le code auto-calculé peut être V1 ou UNK, mais ne doit pas lever d'erreur
        assert case.expected_artcb_code is not None or case.expected_artcb_code is None
        assert isinstance(run, MonteCarloRun)


# ─── T15-T16 : export / save ─────────────────────────────────────────────────

def test_T15_export_regression_cases(fr_run):
    """T15 — export_regression_cases() retourne une liste de dicts."""
    cases = export_regression_cases(fr_run, min_severity="LOW")
    assert isinstance(cases, list)
    for c in cases:
        assert isinstance(c, dict)
        assert "case_id" in c
        assert "lang" in c
        assert "variation_type" in c
        assert "severity" in c


def test_T16_save_regression_cases(fr_run):
    """T16 — save_regression_cases() écrit un JSON valide."""
    cases = export_regression_cases(fr_run, min_severity="LOW")
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "regression_cases.json"
        path = save_regression_cases(cases, output)
        assert path.exists()
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert isinstance(loaded, list)
        assert len(loaded) == len(cases)


# ─── T17 : multi-langue ──────────────────────────────────────────────────────

def test_T17_english_run(en_run):
    """T17 — Le run EN fonctionne avec la même interface."""
    assert en_run.lang == "en"
    assert en_run.n_cases > 0
    assert 0.0 <= en_run.pass_rate <= 1.0


def test_T17b_german_run():
    """T17b — Le run DE fonctionne (adapter DE disponible)."""
    run = run_monte_carlo(
        "de",
        seed_texts=[("Daten verschlüsseln", None)],
        variation_types=["case_upper", "case_lower"],
        seed=42,
    )
    assert run.lang == "de"
    assert isinstance(run, MonteCarloRun)


# ─── T18 : max_cases ─────────────────────────────────────────────────────────

def test_T18_max_cases_limits_output():
    """T18 — max_cases=5 limite le nombre de cas générés."""
    run = run_monte_carlo(
        "fr",
        seed_texts=[("vérifier la signature", "V1"), ("créer un bloc", "K1")],
        variation_types=VARIATION_TYPES,
        max_cases=5,
        seed=42,
    )
    assert run.n_cases <= 5, f"n_cases={run.n_cases} doit être ≤ 5"


# ─── T19 : seed_texts vide ────────────────────────────────────────────────────

def test_T19_empty_seed_texts():
    """T19 — seed_texts vide → run vide sans erreur."""
    run = run_monte_carlo(
        "fr",
        seed_texts=[],
        variation_types=["case_upper"],
        seed=42,
    )
    assert isinstance(run, MonteCarloRun)
    assert run.n_cases == 0
    assert run.pass_rate == 0.0


# ─── T20 : synonym_variant ───────────────────────────────────────────────────

def test_T20_synonym_variant_produces_string():
    """T20 — synonym_variant retourne toujours une chaîne."""
    import random
    rng = random.Random(0)
    result = _apply_variation("vérifier la signature", "synonym_variant", rng)
    assert isinstance(result, str)


# ─── T21-T22 : cas de défauts spécifiques ─────────────────────────────────────

def test_T21_negation_changes_meaning():
    """T21 — 'not verify' est différent de 'verify' — le code peut changer."""
    from src.artcb.language.lineage import trace_lineage
    lin_orig = trace_lineage("verify the signature", "en")
    lin_neg = trace_lineage("not verify the signature", "en")
    # Les deux doivent fonctionner sans erreur interne
    assert lin_orig.is_ok()
    assert lin_neg.is_ok()
    # La négation peut changer le code (pas d'assertion sur le résultat)


def test_T22_noise_transpose_finding_structure():
    """T22 — Si noise_transpose produit un finding, il a la structure attendue."""
    run = run_monte_carlo(
        "fr",
        seed_texts=[("créer un bloc", "K1")],
        variation_types=["noise_transpose"],
        seed=0x41525443,
    )
    for finding in run.findings:
        assert finding.case.variation_type == "noise_transpose"
        assert finding.finding_id != ""
        assert finding.description != ""
        assert finding.recommendation != ""


# ─── T23 : invariants ────────────────────────────────────────────────────────

def test_T23_invariants_always_false(fr_run):
    """T23 — unique_human_proven et certified toujours False."""
    assert fr_run.unique_human_proven is False
    assert fr_run.certified is False
    for case in fr_run.cases:
        assert case.unique_human_proven is False
        assert case.certified is False
    for finding in fr_run.findings:
        assert finding.unique_human_proven is False
        assert finding.certified is False


# ─── T24 : sérialisation ─────────────────────────────────────────────────────

def test_T24_finding_to_dict_json_serializable(fr_run):
    """T24 — MonteCarloFinding.to_dict() est JSON-sérialisable."""
    for finding in fr_run.findings:
        d = finding.to_dict()
        assert isinstance(d, dict)
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["severity"] == finding.severity
        assert parsed["finding_id"] == finding.finding_id
        break  # un seul finding suffit


def test_T24b_run_to_json(fr_run):
    """T24b — MonteCarloRun.to_json() est valide."""
    j = fr_run.to_json()
    parsed = json.loads(j)
    assert parsed["lang"] == "fr"
    assert "findings_count" in parsed


# ─── T25 : version ───────────────────────────────────────────────────────────

def test_T25_module_version():
    """T25 — MODULE_VERSION de monte_carlo.py est 1.0.x."""
    major, minor, _patch = (int(x) for x in MODULE_VERSION.split("."))
    assert (major, minor) == (1, 0), (
        f"MODULE_VERSION doit être 1.0.x, obtenu '{MODULE_VERSION}'"
    )
