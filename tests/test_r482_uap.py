"""Tests R482 — Universal Audit Preflight (UAP).

Suite de tests pour src/artcb/audit/uap.py.
Couvre : toutes les sections du UAP, findings, invariants, sérialisation.

Architecture tests :
    T01–T03 : Section GIT
    T04–T06 : Section LEDGER
    T07–T08 : Section STANDARD_NAMES
    T09–T10 : Section REPO
    T11–T12 : Section LANGUAGE
    T13      : Section CERTIFIED invariants
    T14–T17  : run_uap() intégration + preflight_ok
    T18–T20  : UapReport.to_dict() + save_uap_report()

CERTIFIED_100=false — invariant absolu dans tous les tests.
unique_human_proven=false — invariant absolu dans tous les tests.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.artcb.audit.uap import (
    UapFinding,
    UapReport,
    UapSection,
    _collect_certified_invariant,
    _collect_git,
    _collect_language_baseline,
    _collect_ledger,
    _collect_repo_map,
    _collect_standard_names,
    run_uap,
    save_uap_report,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def repo_root() -> Path:
    """Racine réelle du dépôt ARTCB."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Répertoire temporaire simulant un dépôt minimal."""
    # STANDARD_NAMES_ARTCB minimal
    (tmp_path / "STANDARD_NAMES_ARTCB").write_text(
        "# STANDARD DE NOMMAGE — ARTCB\n"
        "## 1. Fichiers documentation\n"
        "## 2. Code Python\n"
        "## 3. Code C\n"
        "## 4. Frontend (TypeScript/React)\n"
        "## 5. API REST\n"
        "## 6. IR / Langage ARTCB\n"
        "## 7. Types de nœuds (NodeType)\n"
        "## 8. Types de liens (EdgeType)\n"
        "## 9. Rapports (PROTOCOLE)\n"
        "## 10. Logs (mode DEBUG)\n",
        encoding="utf-8",
    )
    # Ledger minimal
    artcb_dir = tmp_path / ".artcb"
    artcb_dir.mkdir()
    (artcb_dir / "task_ledger.yaml").write_text(
        "meta:\n"
        "  version: '1.0'\n"
        "  head_sha: 'abc1234'\n"
        "  certified_100: false\n"
        "  mode: DEBUG\n"
        "tasks: []\n",
        encoding="utf-8",
    )
    # src/artcb minimal
    src_artcb = tmp_path / "src" / "artcb"
    src_artcb.mkdir(parents=True)
    (src_artcb / "__init__.py").write_text("")
    (src_artcb / "identity").mkdir()
    (src_artcb / "identity" / "__init__.py").write_text("")
    (src_artcb / "identity" / "biometric_onchain.py").write_text("# stub")
    (src_artcb / "crypto").mkdir()
    (src_artcb / "crypto" / "__init__.py").write_text("")
    (src_artcb / "crypto" / "homomorphic.py").write_text("# stub")
    (src_artcb / "identity" / "human_identity_policy.py").write_text("# stub")
    (src_artcb / "audit").mkdir()
    (src_artcb / "audit" / "__init__.py").write_text("")
    (src_artcb / "audit" / "uap.py").write_text("# stub")
    # logs R471
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "R471_mapping_stats.json").write_text(
        json.dumps({
            "git_sha": "abc1234",
            "total_entries": 21484106,
            "resolved_total": 13779,
            "closure_all_ok": True,
        }),
        encoding="utf-8",
    )
    return tmp_path


# ─── T01–T03 : Section GIT ────────────────────────────────────────────────────

def test_T01_git_section_real_repo(repo_root: Path) -> None:
    """T01 — _collect_git() sur le vrai dépôt retourne sha non vide."""
    section = _collect_git(repo_root)
    assert section.name == "GIT"
    sha = section.data.get("sha", "")
    assert len(sha) >= 7, f"SHA trop court : {sha!r}"
    # Pas de finding CRITICAL si git est disponible
    critical = [f for f in section.findings if f.severity == "CRITICAL"]
    assert not critical, f"CRITICAL inattendu : {critical}"


def test_T02_git_section_returns_branch(repo_root: Path) -> None:
    """T02 — _collect_git() retourne une branche connue (main ou autre)."""
    section = _collect_git(repo_root)
    branch = section.data.get("branch", "")
    assert branch != "", "Branche vide"
    assert branch != "UNKNOWN", f"Branche UNKNOWN inattendue : {branch!r}"


def test_T03_git_section_modified_files_count(repo_root: Path) -> None:
    """T03 — _collect_git() expose un compteur de fichiers modifiés (entier ≥ 0)."""
    section = _collect_git(repo_root)
    count = section.data.get("modified_files_count")
    assert isinstance(count, int) and count >= 0, f"modified_files_count invalide : {count!r}"


# ─── T04–T06 : Section LEDGER ─────────────────────────────────────────────────

def test_T04_ledger_absent_no_critical(tmp_path: Path) -> None:
    """T04 — Ledger absent → WARNING (pas CRITICAL) — fail-open."""
    section = _collect_ledger(tmp_path / ".artcb" / "task_ledger.yaml", "abc1234")
    assert section.name == "LEDGER"
    critical = [f for f in section.findings if f.severity == "CRITICAL"]
    assert not critical, "Ledger absent ne doit pas être CRITICAL"
    warnings = [f for f in section.findings if f.severity == "WARNING"]
    assert warnings, "Ledger absent doit produire WARNING"


def test_T05_ledger_sha_divergence_produces_warning(tmp_path: Path) -> None:
    """T05 — SHA ledger ≠ SHA HEAD → WARNING LEDGER_DIVERGENCE."""
    artcb_dir = tmp_path / ".artcb"
    artcb_dir.mkdir()
    (artcb_dir / "task_ledger.yaml").write_text(
        "meta:\n  head_sha: 'aaaaaa'\n  certified_100: false\ntasks: []\n"
    )
    section = _collect_ledger(artcb_dir / "task_ledger.yaml", "bbbbbbbbbbbb")
    warnings = [f for f in section.findings if "DIVERGENCE" in f.message]
    assert warnings, "Divergence SHA doit produire un WARNING LEDGER_DIVERGENCE"


def test_T06_ledger_certified_true_produces_critical(tmp_path: Path) -> None:
    """T06 — certified_100=true dans le ledger → CRITICAL (invariant violated)."""
    artcb_dir = tmp_path / ".artcb"
    artcb_dir.mkdir()
    (artcb_dir / "task_ledger.yaml").write_text(
        "meta:\n  head_sha: 'abc1234'\n  certified_100: true\ntasks: []\n"
    )
    section = _collect_ledger(artcb_dir / "task_ledger.yaml", "abc1234")
    critical = [f for f in section.findings if f.severity == "CRITICAL"]
    assert critical, "certified_100=true doit produire un finding CRITICAL"
    assert any("CERTIFIED_100" in f.message for f in critical)


# ─── T07–T08 : Section STANDARD_NAMES ────────────────────────────────────────

def test_T07_standard_names_absent_produces_critical(tmp_path: Path) -> None:
    """T07 — STANDARD_NAMES_ARTCB absent → CRITICAL."""
    section = _collect_standard_names(tmp_path / "STANDARD_NAMES_ARTCB")
    assert not section.ok
    critical = [f for f in section.findings if f.severity == "CRITICAL"]
    assert critical, "Fichier absent → CRITICAL"


def test_T08_standard_names_present_complete(tmp_repo: Path) -> None:
    """T08 — STANDARD_NAMES_ARTCB présent et complet → ok=True, zéro CRITICAL."""
    section = _collect_standard_names(tmp_repo / "STANDARD_NAMES_ARTCB")
    assert section.ok
    assert section.data.get("size_chars", 0) > 0
    critical = [f for f in section.findings if f.severity == "CRITICAL"]
    assert not critical


# ─── T09–T10 : Section REPO ───────────────────────────────────────────────────

def test_T09_repo_map_real_repo_has_modules(repo_root: Path) -> None:
    """T09 — _collect_repo_map() sur le vrai dépôt trouve ≥ 50 modules Python."""
    section = _collect_repo_map(repo_root)
    assert section.ok
    count = section.data.get("module_count", 0)
    assert count >= 50, f"Moins de 50 modules trouvés : {count}"


def test_T10_repo_map_critical_modules_present(repo_root: Path) -> None:
    """T10 — Les modules critiques TASK-001 sont présents sur HEAD."""
    section = _collect_repo_map(repo_root)
    missing = section.data.get("critical_modules_missing", [])
    assert not missing, f"Modules critiques manquants : {missing}"


# ─── T11–T12 : Section LANGUAGE ───────────────────────────────────────────────

def test_T11_language_baseline_absent_no_critical(tmp_path: Path) -> None:
    """T11 — R471_mapping_stats.json absent → WARNING (pas CRITICAL) — fail-open."""
    section = _collect_language_baseline(tmp_path / "logs" / "R471_mapping_stats.json")
    assert section.ok, "Absence baseline linguistique = WARNING, pas CRITICAL"
    critical = [f for f in section.findings if f.severity == "CRITICAL"]
    assert not critical


def test_T12_language_baseline_closure_ok(tmp_repo: Path) -> None:
    """T12 — R471 closure_ok=True → INFO finding + data correctes."""
    section = _collect_language_baseline(tmp_repo / "logs" / "R471_mapping_stats.json")
    assert section.ok
    assert section.data.get("closure_ok") is True
    assert section.data.get("total_entries", 0) > 0


# ─── T13 : Section CERTIFIED invariants ──────────────────────────────────────

def test_T13_certified_invariants_always_false() -> None:
    """T13 — Section CERTIFIED : certified_100=False et unique_human_proven=False invariants."""
    section = _collect_certified_invariant()
    assert section.ok
    assert section.data["certified_100"] is False, "CERTIFIED_100 doit être False"
    assert section.data["unique_human_proven"] is False, "unique_human_proven doit être False"
    critical = [f for f in section.findings if f.severity == "CRITICAL"]
    assert not critical


# ─── T14–T17 : run_uap() intégration ─────────────────────────────────────────

def test_T14_run_uap_returns_report(repo_root: Path) -> None:
    """T14 — run_uap() retourne un UapReport valide sur le vrai dépôt."""
    report = run_uap(repo_root)
    assert isinstance(report, UapReport)
    assert report.git_sha != "UNKNOWN"
    assert len(report.sections) >= 6


def test_T15_run_uap_certified_invariants(repo_root: Path) -> None:
    """T15 — run_uap() : certified_100=False et unique_human_proven=False invariants absolus."""
    report = run_uap(repo_root)
    assert report.certified_100 is False, "CERTIFIED_100 doit être False"
    assert report.unique_human_proven is False, "unique_human_proven doit être False"


def test_T16_run_uap_preflight_ok_on_clean_repo(tmp_repo: Path) -> None:
    """T16 — run_uap() sur un tmp_repo avec git init : 0 CRITICAL non-GIT."""
    import subprocess as _sp
    # Initialise un vrai dépôt git pour que la section GIT ne soit pas CRITICAL
    _sp.run(["git", "init"], cwd=tmp_repo, check=True, capture_output=True)
    _sp.run(["git", "config", "user.email", "test@artcb"], cwd=tmp_repo, check=True, capture_output=True)
    _sp.run(["git", "config", "user.name", "test"], cwd=tmp_repo, check=True, capture_output=True)
    (tmp_repo / "README.md").write_text("test")
    _sp.run(["git", "add", "."], cwd=tmp_repo, check=True, capture_output=True)
    _sp.run(["git", "commit", "-m", "init"], cwd=tmp_repo, check=True, capture_output=True)
    report = run_uap(tmp_repo)
    assert report.critical_count == 0, (
        f"CRITICAL inattendu(s) sur tmp_repo : "
        + str([f.message for f in report.all_findings if f.severity == "CRITICAL"])
    )
    assert report.preflight_ok is True


def test_T17_run_uap_finds_certified_violation() -> None:
    """T17 — run_uap() détecte un ledger avec certified_100=true → CRITICAL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # Créer un ledger avec certified_100=true
        artcb_dir = tmp / ".artcb"
        artcb_dir.mkdir()
        (artcb_dir / "task_ledger.yaml").write_text(
            "meta:\n  head_sha: 'xxx'\n  certified_100: true\ntasks: []\n"
        )
        (tmp / "STANDARD_NAMES_ARTCB").write_text(
            "# STANDARD DE NOMMAGE\n"
            "## 1. Fichiers documentation\n## 2. Code Python\n## 3. Code C\n"
            "## 4. Frontend (TypeScript/React)\n## 5. API REST\n"
            "## 6. IR / Langage ARTCB\n## 7. Types de nœuds (NodeType)\n"
            "## 8. Types de liens (EdgeType)\n## 9. Rapports (PROTOCOLE)\n"
        )
        (tmp / "src" / "artcb").mkdir(parents=True)
        report = run_uap(tmp)
        assert report.critical_count > 0, "Doit détecter certified_100=true comme CRITICAL"
        assert report.preflight_ok is False


# ─── T18–T20 : UapReport.to_dict() + save_uap_report() ──────────────────────

def test_T18_report_to_dict_structure(repo_root: Path) -> None:
    """T18 — to_dict() produit un dict JSON-sérialisable avec les clés obligatoires."""
    report = run_uap(repo_root)
    d = report.to_dict()
    required_keys = {
        "uap_version", "timestamp_utc", "git_sha",
        "certified_100", "unique_human_proven",
        "preflight_ok", "critical_count", "warning_count", "sections",
    }
    assert required_keys <= d.keys(), f"Clés manquantes : {required_keys - d.keys()}"
    # Doit être JSON-sérialisable sans erreur
    json_str = json.dumps(d)
    assert len(json_str) > 100


def test_T19_save_uap_report_creates_file(tmp_path: Path, repo_root: Path) -> None:
    """T19 — save_uap_report() crée un fichier JSON lisible."""
    report = run_uap(repo_root)
    out = save_uap_report(report, output_dir=tmp_path)
    assert out.exists(), f"Fichier rapport non créé : {out}"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["certified_100"] is False
    assert data["unique_human_proven"] is False


def test_T20_finding_ids_unique(repo_root: Path) -> None:
    """T20 — Tous les finding_id dans UapReport sont uniques."""
    report = run_uap(repo_root)
    ids = [f.finding_id for f in report.all_findings]
    assert len(ids) == len(set(ids)), f"Finding IDs dupliqués : {ids}"
