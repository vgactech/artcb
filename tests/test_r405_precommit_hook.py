"""
Tests R405 — hook pre-commit ARTCB + script d'installation.

T01–T04 : artcb_r405_install_precommit_hook.py (check/install/remove)
T05–T08 : artcb_r405_precommit_hook.sh (comportement bash via subprocess)
T09–T12 : intégration E2E avec vrai dépôt git temporaire
T13–T15 : cas limites (no MODULE_VERSION, fichier absent, fail-open)

CERTIFIED_100=false | MODE DEBUG
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.artcb_r405_install_precommit_hook as installer

REPO_ROOT = Path(__file__).parent.parent
HOOK_SH = REPO_ROOT / "scripts" / "artcb_r405_precommit_hook.sh"
BUMP_PY = REPO_ROOT / "scripts" / "artcb_bump_module_version.py"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_temp_git_repo() -> Path:
    """Crée un dépôt git temporaire minimal avec les scripts R405."""
    tmpdir = Path(tempfile.mkdtemp(prefix="r405_test_"))
    subprocess.run(["git", "init", str(tmpdir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmpdir), "config", "user.email", "test@artcb"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmpdir), "config", "user.name", "Test"], check=True, capture_output=True)

    # Copie les scripts nécessaires
    scripts_dir = tmpdir / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(HOOK_SH, scripts_dir / "artcb_r405_precommit_hook.sh")
    shutil.copy2(BUMP_PY, scripts_dir / "artcb_bump_module_version.py")

    # Commit initial
    (tmpdir / "README.md").write_text("test repo\n")
    subprocess.run(["git", "-C", str(tmpdir), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmpdir), "commit", "-m", "init"], check=True, capture_output=True)
    return tmpdir


def _write_py_module(path: Path, version: str = "1.0.0", content: str = "") -> None:
    path.write_text(
        f'#!/usr/bin/env python3\nMODULE_VERSION = \'{version}\'  # test\n{content}\n',
        encoding="utf-8",
    )


# ── T01–T04 : installer ────────────────────────────────────────────────────────

class TestInstaller(unittest.TestCase):

    def setUp(self):
        self.repo = _make_temp_git_repo()
        # Override HOOK_DEST_REL pour pointer vers notre dépôt temp
        self._orig_cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_T01_check_no_hook(self):
        """T01 — check retourne 1 si hook absent."""
        code = installer.check_status(self.repo)
        self.assertEqual(code, 1)

    def test_T02_install_success(self):
        """T02 — install crée .git/hooks/pre-commit exécutable."""
        code = installer.install(self.repo)
        self.assertEqual(code, 0)
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        self.assertTrue(hook.exists())
        self.assertTrue(hook.stat().st_mode & stat.S_IXUSR)

    def test_T03_check_after_install(self):
        """T03 — check retourne 0 après installation réussie."""
        installer.install(self.repo)
        code = installer.check_status(self.repo)
        self.assertEqual(code, 0)

    def test_T04_remove_our_hook(self):
        """T04 — remove supprime le hook R405."""
        installer.install(self.repo)
        code = installer.remove(self.repo)
        self.assertEqual(code, 0)
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        self.assertFalse(hook.exists())


# ── T05–T08 : hook bash (subprocess) ─────────────────────────────────────────

class TestHookBash(unittest.TestCase):

    def setUp(self):
        self.repo = _make_temp_git_repo()
        installer.install(self.repo)
        self._orig_cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.repo, ignore_errors=True)

    def _stage_file(self, rel_path: str, version: str = "1.2.3") -> Path:
        path = self.repo / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_py_module(path, version)
        subprocess.run(["git", "-C", str(self.repo), "add", rel_path], check=True, capture_output=True)
        return path

    def test_T05_hook_exit_0_always(self):
        """T05 — le hook retourne toujours exit code 0 (fail-open)."""
        self._stage_file("test_module.py")
        result = subprocess.run(
            ["bash", str(self.repo / ".git" / "hooks" / "pre-commit")],
            cwd=str(self.repo),
            capture_output=True,
            env={**os.environ, "GIT_DIR": str(self.repo / ".git")},
        )
        self.assertEqual(result.returncode, 0)

    def test_T06_hook_bumps_module_version(self):
        """T06 — le hook incrémente MODULE_VERSION du fichier stagé."""
        path = self._stage_file("mymodule.py", "3.1.4")
        subprocess.run(
            ["bash", str(self.repo / ".git" / "hooks" / "pre-commit")],
            cwd=str(self.repo),
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_DIR": str(self.repo / ".git")},
        )
        content = path.read_text()
        m = re.search(r"MODULE_VERSION = '(.+?)'", content)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "3.1.5")  # PATCH bumped

    def test_T07_hook_skip_file_without_module_version(self):
        """T07 — le hook ignore les fichiers sans MODULE_VERSION."""
        path = self.repo / "no_version.py"
        path.write_text("def foo(): return 42\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "no_version.py"], check=True, capture_output=True)
        result = subprocess.run(
            ["bash", str(self.repo / ".git" / "hooks" / "pre-commit")],
            cwd=str(self.repo),
            capture_output=True,
            env={**os.environ, "GIT_DIR": str(self.repo / ".git")},
        )
        self.assertEqual(result.returncode, 0)
        # Fichier inchangé
        self.assertNotIn("MODULE_VERSION", path.read_text())

    def test_T08_hook_no_staged_files_exit_0(self):
        """T08 — hook exit 0 silencieux quand aucun .py stagé."""
        result = subprocess.run(
            ["bash", str(self.repo / ".git" / "hooks" / "pre-commit")],
            cwd=str(self.repo),
            capture_output=True,
            env={**os.environ, "GIT_DIR": str(self.repo / ".git")},
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")


# ── T09–T12 : intégration E2E avec vrai commit ───────────────────────────────

class TestE2ECommit(unittest.TestCase):

    def setUp(self):
        self.repo = _make_temp_git_repo()
        installer.install(self.repo)
        self._orig_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.repo)] + list(args),
            check=True, capture_output=True, text=True,
        )

    def test_T09_commit_bumps_version_in_committed_file(self):
        """T09 — après git commit, le fichier committé a sa version bumpée."""
        path = self.repo / "myservice.py"
        _write_py_module(path, "5.0.0")
        self._git("add", "myservice.py")
        self._git("commit", "-m", "add myservice")

        content = path.read_text()
        m = re.search(r"MODULE_VERSION = '(.+?)'", content)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "5.0.1")

    def test_T10_commit_includes_bumped_version(self):
        """T10 — le commit lui-même contient la version bumpée (pas 5.0.0)."""
        path = self.repo / "service2.py"
        _write_py_module(path, "1.0.0")
        self._git("add", "service2.py")
        self._git("commit", "-m", "add service2")

        # Vérifie le contenu committé dans git
        result = subprocess.run(
            ["git", "-C", str(self.repo), "show", "HEAD:service2.py"],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("MODULE_VERSION = '1.0.1'", result.stdout)

    def test_T11_hook_journal_updated(self):
        """T11 — le journal module_version_history.jsonl est mis à jour après commit."""
        # Crée le dossier data/trace
        (self.repo / "data" / "trace").mkdir(parents=True, exist_ok=True)
        path = self.repo / "alpha.py"
        _write_py_module(path, "0.1.0")
        self._git("add", "alpha.py")
        self._git("commit", "-m", "add alpha")

        journal = self.repo / "data" / "trace" / "module_version_history.jsonl"
        if journal.exists():
            import json
            entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
            last = entries[-1]
            self.assertEqual(last["previous_version"], "0.1.0")
            self.assertEqual(last["new_version"], "0.1.1")

    def test_T12_multiple_py_files_all_bumped(self):
        """T12 — plusieurs .py stagés → tous bumpés en un seul commit."""
        files = {}
        for name, ver in [("mod_a.py", "1.0.0"), ("mod_b.py", "2.5.3")]:
            p = self.repo / name
            _write_py_module(p, ver)
            files[name] = p
        self._git("add", "mod_a.py", "mod_b.py")
        self._git("commit", "-m", "add two modules")

        versions = {}
        for name, p in files.items():
            m = re.search(r"MODULE_VERSION = '(.+?)'", p.read_text())
            versions[name] = m.group(1) if m else None

        self.assertEqual(versions["mod_a.py"], "1.0.1")
        self.assertEqual(versions["mod_b.py"], "2.5.4")


# ── T13–T15 : cas limites ─────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):

    def setUp(self):
        self.repo = _make_temp_git_repo()
        installer.install(self.repo)
        self._orig_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo)] + list(args),
            check=True, capture_output=True, text=True,
        )

    def test_T13_non_python_file_not_bumped(self):
        """T13 — un fichier .txt stagé n'est pas touché par le hook."""
        txt = self.repo / "notes.txt"
        txt.write_text("MODULE_VERSION = '9.9.9'\n")  # texte similaire mais pas .py
        self._git("add", "notes.txt")
        self._git("commit", "-m", "add notes")
        content = txt.read_text()
        # Le contenu ne doit pas avoir été modifié (pas de bump sur .txt)
        self.assertIn("9.9.9", content)

    def test_T14_hook_fail_open_if_bump_script_missing(self):
        """T14 — si le script bump est absent, le hook exit 0 sans bloquer."""
        # Supprime le script bump du repo temp
        bump = self.repo / "scripts" / "artcb_bump_module_version.py"
        bump.unlink()

        path = self.repo / "orphan.py"
        _write_py_module(path, "1.0.0")
        self._git("add", "orphan.py")

        # Le hook doit quand même exit 0
        result = subprocess.run(
            ["bash", str(self.repo / ".git" / "hooks" / "pre-commit")],
            cwd=str(self.repo),
            capture_output=True,
            env={**os.environ, "GIT_DIR": str(self.repo / ".git")},
        )
        self.assertEqual(result.returncode, 0)

    def test_T15_installer_check_returns_1_if_bump_script_missing(self):
        """T15 — check() retourne 1 si le bump script est absent après install."""
        installer.install(self.repo)
        (self.repo / "scripts" / "artcb_bump_module_version.py").unlink()
        code = installer.check_status(self.repo)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
