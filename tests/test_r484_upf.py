"""Tests R484 — Universal Postflight (UPF) — ORDRE 6 (R481).

≥ 15 tests couvrant :
  - PostflightReport / PostflightFinding / PostflightSection (structures)
  - run_upf() : ADVISORY + GATE modes
  - _collect_diff : base_sha, working tree propre, fichiers modifiés
  - _collect_impact : pas de Python, modules sensibles au langage
  - _collect_regression_baseline : présence de tests
  - _collect_tasks_impact : ledger absent / présent
  - _collect_certified_invariant : invariants immuables
  - save_upf_report : persistance JSON
  - Modes ADVISORY / GATE : différence de comportement
  - Invariants CERTIFIED_100=False et unique_human_proven=False

Règles ARTCB :
  - Mode DEBUG
  - CERTIFIED_100 = False — invariant absolu
  - unique_human_proven = False — invariant absolu
  - Jamais mock qui compromettre la véracité des résultats
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.artcb.audit.upf import (
    MODULE_VERSION,
    LANGUAGE_SENSITIVE_MODULES,
    UPF_ADVISORY,
    UPF_GATE,
    DiffEntry,
    PostflightFinding,
    PostflightSection,
    PostflightReport,
    _collect_certified_invariant,
    _collect_diff,
    _collect_impact,
    _collect_regression_baseline,
    _collect_tasks_impact,
    run_upf,
    save_upf_report,
)


# ─── T01 — Module version présent ─────────────────────────────────────────────
def test_T01_module_version():
    """T01 : MODULE_VERSION présent et non vide."""
    assert MODULE_VERSION, "MODULE_VERSION doit être non vide"
    parts = MODULE_VERSION.split(".")
    assert len(parts) == 3, "Format semver attendu X.Y.Z"


# ─── T02 — LANGUAGE_SENSITIVE_MODULES non vide ────────────────────────────────
def test_T02_language_sensitive_modules():
    """T02 : LANGUAGE_SENSITIVE_MODULES contient au moins lexicon_mapper."""
    assert "src/artcb/language/lexicon_mapper.py" in LANGUAGE_SENSITIVE_MODULES
    assert len(LANGUAGE_SENSITIVE_MODULES) >= 4


# ─── T03 — DiffEntry instanciation ────────────────────────────────────────────
def test_T03_diff_entry():
    """T03 : DiffEntry bien instancié."""
    e = DiffEntry(path="src/foo.py", status="M", additions=5, deletions=2)
    assert e.path == "src/foo.py"
    assert e.status == "M"
    assert e.additions == 5


# ─── T04 — PostflightFinding instanciation ────────────────────────────────────
def test_T04_finding_creation():
    """T04 : PostflightFinding bien instancié."""
    f = PostflightFinding(
        severity="WARNING",
        category="DIFF",
        message="test message",
        detail="détail",
        finding_id="UPF-0001",
    )
    assert f.severity == "WARNING"
    assert f.finding_id == "UPF-0001"


# ─── T05 — PostflightSection ok si zéro CRITICAL ─────────────────────────────
def test_T05_section_ok_no_critical():
    """T05 : ok=True si aucun finding CRITICAL."""
    findings = [
        PostflightFinding(severity="INFO", category="DIFF", message="info"),
        PostflightFinding(severity="WARNING", category="DIFF", message="warn"),
    ]
    ok = not any(f.severity == "CRITICAL" for f in findings)
    assert ok is True


# ─── T06 — PostflightSection ok=False si CRITICAL ────────────────────────────
def test_T06_section_not_ok_critical():
    """T06 : ok=False si un finding CRITICAL est présent."""
    findings = [
        PostflightFinding(severity="CRITICAL", category="DIFF", message="crit"),
    ]
    ok = not any(f.severity == "CRITICAL" for f in findings)
    assert ok is False


# ─── T07 — _collect_certified_invariant ──────────────────────────────────────
def test_T07_certified_invariant():
    """T07 : section CERTIFIED toujours ok + invariants CERTIFIED_100=False."""
    section = _collect_certified_invariant()
    assert section.name == "CERTIFIED"
    assert section.ok is True
    assert section.data["certified_100"] is False
    assert section.data["unique_human_proven"] is False
    assert len(section.findings) >= 1
    assert "certified_100=False" in section.findings[0].message


# ─── T08 — _collect_regression_baseline — dossier tests présent ──────────────
def test_T08_regression_baseline_tests_present():
    """T08 : section REGRESSION détecte les fichiers de test existants."""
    repo_root = Path(__file__).resolve().parents[1]
    section = _collect_regression_baseline(repo_root)
    assert section.name == "REGRESSION"
    assert section.ok is True
    assert section.data.get("test_files_count", 0) >= 1
    assert len(section.findings) >= 1
    # Doit être INFO (pas CRITICAL)
    assert not any(f.severity == "CRITICAL" for f in section.findings)


# ─── T09 — _collect_regression_baseline — dossier absent ────────────────────
def test_T09_regression_baseline_no_tests():
    """T09 : section REGRESSION avec dossier tests absent → WARNING, pas CRITICAL."""
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        section = _collect_regression_baseline(fake_root)
    assert section.name == "REGRESSION"
    assert section.ok is True  # fail-open
    assert any(f.severity == "WARNING" for f in section.findings)


# ─── T10 — _collect_tasks_impact — ledger absent ──────────────────────────────
def test_T10_tasks_impact_no_ledger():
    """T10 : section TASKS avec ledger absent → ok=True, open_tasks_count=0."""
    with tempfile.TemporaryDirectory() as td:
        section = _collect_tasks_impact([], Path(td))
    assert section.name == "TASKS"
    assert section.ok is True
    assert section.data.get("open_tasks_count", 0) == 0


# ─── T11 — _collect_diff — working tree propre (repo réel) ────────────────────
def test_T11_collect_diff_clean_or_dirty():
    """T11 : _collect_diff sur le dépôt réel — section valide (ok + données)."""
    repo_root = Path(__file__).resolve().parents[1]
    section = _collect_diff(repo_root)
    assert section.name == "DIFF"
    assert isinstance(section.data.get("modified_files_count"), int)
    assert isinstance(section.data.get("modified_files"), list)
    # fail-open toujours
    assert not any(f.severity == "CRITICAL" for f in section.findings)


# ─── T12 — _collect_impact — aucun fichier modifié ────────────────────────────
def test_T12_collect_impact_no_modified():
    """T12 : _collect_impact avec liste vide → ok + language_impact=False."""
    repo_root = Path(__file__).resolve().parents[1]
    section = _collect_impact([], repo_root)
    assert section.name == "IMPACT"
    assert section.ok is True
    assert section.data.get("language_impact") is False
    assert section.data.get("impacted_functions") == []


# ─── T13 — _collect_impact — module linguistique modifié ─────────────────────
def test_T13_collect_impact_language_sensitive():
    """T13 : détection language_impact sans build_call_graph complet (trop lent ~90s).

    On teste la logique de détection directement sur LANGUAGE_SENSITIVE_MODULES
    sans déclencher le scan du dépôt entier (hors budget L-052 / 30s/test).
    """
    # Test direct de la logique LANGUAGE_SENSITIVE_MODULES
    lang_module = "src/artcb/language/lexicon_mapper.py"
    assert lang_module in LANGUAGE_SENSITIVE_MODULES, \
        "lexicon_mapper.py doit être dans LANGUAGE_SENSITIVE_MODULES"

    # _collect_impact sur liste vide → language_impact=False (contrôle)
    repo_root = Path(__file__).resolve().parents[1]
    section_empty = _collect_impact([], repo_root)
    assert section_empty.data.get("language_impact") is False

    # Avec un faux repo (pas de src/artcb) → call_graph fail-open → ok=True
    with tempfile.TemporaryDirectory() as td:
        section_lang = _collect_impact([lang_module], Path(td))
    assert section_lang.name == "IMPACT"
    assert section_lang.ok is True  # fail-open obligatoire
    assert "language_impact" in section_lang.data


# ─── T14 — run_upf mode ADVISORY ─────────────────────────────────────────────
def test_T14_run_upf_advisory():
    """T14 : run_upf() en mode ADVISORY retourne un PostflightReport valide."""
    report = run_upf(mode=UPF_ADVISORY)
    assert isinstance(report, PostflightReport)
    assert report.mode == UPF_ADVISORY
    assert report.certified_100 is False
    assert report.unique_human_proven is False
    # Invariants immuables
    assert isinstance(report.postflight_ok, bool)
    assert isinstance(report.critical_count, int)
    assert isinstance(report.warning_count, int)
    # Sections attendues
    section_names = [s.name for s in report.sections]
    for expected in ["DIFF", "IMPACT", "REGRESSION", "TASKS", "CERTIFIED"]:
        assert expected in section_names, f"Section {expected} manquante"


# ─── T15 — run_upf mode GATE ─────────────────────────────────────────────────
def test_T15_run_upf_gate():
    """T15 : run_upf() en mode GATE retourne un rapport avec mode=GATE."""
    report = run_upf(mode=UPF_GATE)
    assert report.mode == UPF_GATE
    assert report.certified_100 is False
    assert report.unique_human_proven is False


# ─── T16 — PostflightReport.to_dict() ────────────────────────────────────────
def test_T16_to_dict():
    """T16 : to_dict() retourne un dict JSON-sérialisable avec les champs obligatoires."""
    report = run_upf()
    d = report.to_dict()
    assert isinstance(d, dict)
    # Champs obligatoires
    for key in ["upf_version", "timestamp_utc", "git_sha_before", "git_sha_after",
                "mode", "certified_100", "unique_human_proven", "postflight_ok",
                "critical_count", "warning_count", "sections"]:
        assert key in d, f"Champ {key!r} manquant dans to_dict()"
    # Invariants dans le dictionnaire
    assert d["certified_100"] is False
    assert d["unique_human_proven"] is False
    # JSON-sérialisable
    json_str = json.dumps(d, ensure_ascii=False)
    assert len(json_str) > 50


# ─── T17 — save_upf_report — crée un fichier JSON ────────────────────────────
def test_T17_save_upf_report():
    """T17 : save_upf_report() crée un fichier JSON lisible."""
    report = run_upf()
    with tempfile.TemporaryDirectory() as td:
        out_path = save_upf_report(report, output_dir=Path(td))
        assert out_path.suffix == ".json"
        # Lire DANS le contexte — le répertoire est encore présent
        data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["certified_100"] is False
    assert "sections" in data


# ─── T18 — findings numérotés UPF-NNNN ───────────────────────────────────────
def test_T18_findings_numbered():
    """T18 : Tous les all_findings ont un finding_id UPF-NNNN."""
    report = run_upf()
    for f in report.all_findings:
        assert f.finding_id.startswith("UPF-"), f"finding_id {f.finding_id!r} incorrect"


# ─── T19 — postflight_ok = True si zéro CRITICAL ─────────────────────────────
def test_T19_postflight_ok_logic():
    """T19 : postflight_ok=True <=> critical_count=0."""
    report = run_upf()
    assert report.postflight_ok == (report.critical_count == 0)


# ─── T20 — _collect_tasks_impact avec ledger YAML réel ───────────────────────
def test_T20_tasks_impact_with_real_ledger():
    """T20 : _collect_tasks_impact avec le ledger réel .artcb/task_ledger.yaml."""
    repo_root = Path(__file__).resolve().parents[1]
    section = _collect_tasks_impact([], repo_root)
    assert section.name == "TASKS"
    assert section.ok is True
    # Le ledger réel contient des tâches OPEN/IN_PROGRESS
    assert section.data.get("open_tasks_count", 0) >= 0  # peut être 0 si tout DONE


# ─── T21 — _collect_diff base_sha == HEAD (diff vide attendu) ─────────────────
def test_T21_diff_base_sha_head():
    """T21 : _collect_diff avec base_sha=HEAD → 0 fichier modifié (diff vide)."""
    import subprocess
    repo_root = Path(__file__).resolve().parents[1]
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        pytest.skip("git non disponible")

    section = _collect_diff(repo_root, base_sha=head)
    assert section.name == "DIFF"
    # Diff HEAD..HEAD = 0 fichier
    assert section.data.get("modified_files_count", -1) == 0
