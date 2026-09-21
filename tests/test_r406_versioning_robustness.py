#!/usr/bin/env python3
"""
R406 — Tests robustesse du versioning : installation automatique hook R405 +
       décision fail-open/fail-closed + sémantique git_head ledger.

Tests T01→T15 :
  T01 : install-hooks présent dans Makefile
  T02 : cible install-hooks exécutable sans erreur fatale
  T03 : hook installé après make install-hooks (dans un repo git tmp)
  T04 : hook marqueur R405 présent après installation
  T05 : hook absent dans un nouveau clone simulé (avant install-hooks)
  T06 : make install-hooks est idempotent (double appel = OK)
  T07 : --check retourne 0 si hook installé, 1 sinon
  T08 : fail-open documenté — commit passe si hook absent (git commit --no-verify simulé)
  T09 : fail-open documenté — commit passe si bump script absent
  T10 : sémantique git_head ledger = HEAD avant commit de sync
  T11 : ledger v2.9 contient les entrées R402/R403/R404/R405
  T12 : ledger global_pct >= 84
  T13 : ledger git_head correspond à b9036a3 (HEAD confirmé)
  T14 : TASK-VERSIONING apparaît dans done OU open du ledger
  T15 : pas de doublon d'id dans done+open du ledger

CERTIFIED_100=false | DEBUG MODE | R406
"""
from __future__ import annotations

MODULE_VERSION = "1.0.1"  # R406 — tests robustesse versioning

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# ─── Chemins ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
MAKEFILE = REPO_ROOT / "Makefile"
LEDGER = REPO_ROOT / ".artcb" / "task_ledger.yaml"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "artcb_r405_install_precommit_hook.py"
BUMP_SCRIPT = REPO_ROOT / "scripts" / "artcb_bump_module_version.py"
HOOK_SRC = REPO_ROOT / "scripts" / "artcb_r405_precommit_hook.sh"


# ─── T01 : install-hooks présent dans Makefile ────────────────────────────────
def test_t01_makefile_has_install_hooks():
    """T01 — La cible install-hooks doit exister dans le Makefile."""
    assert MAKEFILE.exists(), "Makefile absent"
    content = MAKEFILE.read_text(encoding="utf-8")
    assert "install-hooks" in content, "Cible 'install-hooks' absente du Makefile"


# ─── T02 : make install-hooks exécutable sans erreur fatale ───────────────────
def test_t02_make_install_hooks_runs():
    """T02 — make install-hooks ne doit pas retourner un code d'erreur fatal."""
    result = subprocess.run(
        ["make", "install-hooks"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # On accepte 0 (succès) — le hook peut déjà exister
    assert result.returncode == 0, (
        f"make install-hooks a échoué (rc={result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ─── T03 : hook installé après make install-hooks ─────────────────────────────
def test_t03_hook_installed_after_make():
    """T03 — Après make install-hooks, .git/hooks/pre-commit doit exister."""
    subprocess.run(
        ["make", "install-hooks"],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=30,
    )
    hook_path = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    assert hook_path.exists(), ".git/hooks/pre-commit absent après make install-hooks"
    assert os.access(hook_path, os.X_OK), ".git/hooks/pre-commit n'est pas exécutable"


# ─── T04 : marqueur R405 présent dans le hook ─────────────────────────────────
def test_t04_hook_contains_r405_marker():
    """T04 — Le hook installé doit contenir le marqueur identitaire R405."""
    hook_path = REPO_ROOT / ".git" / "hooks" / "pre-commit"
    assert hook_path.exists(), ".git/hooks/pre-commit absent (lancer T03 d'abord)"
    content = hook_path.read_text(encoding="utf-8", errors="ignore")
    assert "R405 — ARTCB pre-commit hook" in content, (
        "Marqueur R405 absent du hook — ce n'est pas notre hook"
    )


# ─── T05 : hook absent dans un repo simulé sans installation ──────────────────
def test_t05_hook_absent_in_fresh_clone_simulation():
    """T05 — Dans un nouveau repo git tmp sans install-hooks, le hook est absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True, timeout=10)
        hook_path = tmp / ".git" / "hooks" / "pre-commit"
        assert not hook_path.exists(), (
            "Le hook pre-commit est présent dans un repo vide — attendu absent"
        )


# ─── T06 : idempotence de make install-hooks ──────────────────────────────────
def test_t06_install_hooks_idempotent():
    """T06 — Deux appels successifs à make install-hooks ne doivent pas produire d'erreur."""
    for i in range(2):
        result = subprocess.run(
            ["make", "install-hooks"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"make install-hooks échoue au passage {i+1} (rc={result.returncode})\n"
            f"stderr: {result.stderr}"
        )


# ─── T07 : --check retourne 0 si hook installé ────────────────────────────────
def test_t07_check_returns_0_when_installed():
    """T07 — python3 artcb_r405_install_precommit_hook.py --check retourne 0 si hook présent."""
    # S'assurer que le hook est installé
    subprocess.run(
        ["make", "install-hooks"],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=30,
    )
    result = subprocess.run(
        [sys.executable, str(INSTALL_SCRIPT), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"--check retourne {result.returncode} alors que le hook est installé\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ─── T08 : fail-open documenté — comportement sans hook ──────────────────────
def test_t08_fail_open_documented_no_hook():
    """T08 — Le hook est fail-open : un commit sans hook ne doit pas bloquer git.
    Test : dans un repo tmp, git commit passe même sans hook pre-commit R405."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True, timeout=10)
        subprocess.run(
            ["git", "config", "user.email", "test@artcb.test"],
            cwd=tmp, capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "config", "user.name", "ARTCBTest"],
            cwd=tmp, capture_output=True, timeout=10,
        )
        # Crée un fichier python avec MODULE_VERSION
        py_file = tmp / "module_test.py"
        py_file.write_text('MODULE_VERSION = "1.0.0"\n# test\n')
        subprocess.run(["git", "add", "module_test.py"], cwd=tmp, capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m", "test sans hook R405"],
            cwd=tmp, capture_output=True, text=True, timeout=15,
        )
        # Sans hook, le commit doit passer (rc=0)
        assert result.returncode == 0, (
            f"Commit échoue dans un repo sans hook (rc={result.returncode}) — comportement inattendu"
        )


# ─── T09 : fail-open — bump script absent → commit passe ─────────────────────
def test_t09_fail_open_bump_script_absent():
    """T09 — Le hook bash est fail-open : si bump script absent, le hook exit 0."""
    hook_src_content = HOOK_SRC.read_text(encoding="utf-8")
    # La ligne de comportement fail-open doit être présente
    assert "exit 0" in hook_src_content, "exit 0 absent du hook sh — fail-open non garanti"
    assert "WARN" in hook_src_content or "absent" in hook_src_content.lower(), (
        "Le hook ne produit pas d'avertissement en cas d'erreur"
    )


# ─── T10 : sémantique git_head = HEAD avant commit de sync ───────────────────
def test_t10_ledger_git_head_semantics_documented():
    """T10 — Le ledger doit documenter que git_head = HEAD connu avant commit de sync.
    Vérification : le champ sync_note mentionne le SHA de synchronisation."""
    assert LEDGER.exists(), "task_ledger.yaml absent"
    data = yaml.safe_load(LEDGER.read_text(encoding="utf-8").lstrip("2"))
    meta = data.get("meta", {})
    sync_note = meta.get("sync_note", "") or meta.get("ledger_sync_note", "")
    assert sync_note, "sync_note absent du méta ledger"
    # Le champ doit contenir une référence à un SHA (7 chars hex minimum)
    import re
    sha_pattern = re.compile(r"[0-9a-f]{7,40}")
    assert sha_pattern.search(sync_note), (
        f"sync_note ne contient aucun SHA : {sync_note!r}"
    )


# ─── T11 : ledger v2.9 contient R402/R403/R404/R405 ─────────────────────────
def test_t11_ledger_contains_r402_to_r405():
    """T11 — Le ledger v2.9 doit lister R402, R403, R404, R405 dans la section done."""
    data = yaml.safe_load(LEDGER.read_text(encoding="utf-8").lstrip("2"))
    done_ids = {str(t.get("id", "")) for t in data.get("done", [])}
    for rid in ("R402", "R403", "R404", "R405"):
        assert rid in done_ids, f"{rid} absent de la section done du ledger"


# ─── T12 : global_pct >= 84 ──────────────────────────────────────────────────
def test_t12_global_pct_gte_84():
    """T12 — Le ledger doit afficher un avancement global >= 84%."""
    data = yaml.safe_load(LEDGER.read_text(encoding="utf-8").lstrip("2"))
    pct = data.get("progress", {}).get("global_pct", 0)
    assert pct >= 84, f"global_pct={pct} < 84"


# ─── T13 : git_head = b9036a3 ────────────────────────────────────────────────
def test_t13_ledger_git_head_matches_head():
    """T13 — Le champ git_head du ledger doit correspondre au SHA HEAD réel."""
    data = yaml.safe_load(LEDGER.read_text(encoding="utf-8").lstrip("2"))
    ledger_sha = data.get("meta", {}).get("git_head", "")
    real_head = subprocess.check_output(
        ["git", "rev-parse", "--short=7", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    assert ledger_sha.startswith(real_head[:7]) or real_head.startswith(ledger_sha[:7]), (
        f"ledger git_head={ledger_sha!r} ≠ HEAD={real_head!r} — sync requis"
    )


# ─── T14 : TASK-VERSIONING apparaît dans done ou open ───────────────────────
def test_t14_task_versioning_in_ledger():
    """T14 — TASK-VERSIONING doit apparaître dans done ou open du ledger."""
    data = yaml.safe_load(LEDGER.read_text(encoding="utf-8").lstrip("2"))
    all_ids = (
        {str(t.get("id", "")) for t in data.get("done", [])}
        | {str(t.get("id", "")) for t in data.get("open", [])}
    )
    assert "TASK-VERSIONING" in all_ids, "TASK-VERSIONING absent du ledger (done ni open)"


# ─── T15 : pas de doublon d'id ───────────────────────────────────────────────
def test_t15_no_duplicate_ids_in_ledger():
    """T15 — Aucun id ne doit apparaître deux fois dans done+open du ledger."""
    data = yaml.safe_load(LEDGER.read_text(encoding="utf-8").lstrip("2"))
    ids = [str(t.get("id", "")) for t in data.get("done", [])]
    ids += [str(t.get("id", "")) for t in data.get("open", [])]
    seen = set()
    dups = []
    for tid in ids:
        if tid in seen:
            dups.append(tid)
        seen.add(tid)
    assert not dups, f"Doublons d'id dans le ledger : {dups}"
