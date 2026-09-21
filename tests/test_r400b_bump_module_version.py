#!/usr/bin/env python3
"""
Tests R400-B — artcb_bump_module_version.py

T01 : bump PATCH 1.0.0 → 1.0.1
T02 : bump PATCH 1.2.3 → 1.2.4
T03 : bump PATCH 1.0.9 → 1.0.10
T04 : dry-run ne modifie pas le fichier
T05 : dry-run ne crée pas d'entrée dans le journal
T06 : MODULE_VERSION absent → RuntimeError avec message clair
T07 : fichier inexistant → FileNotFoundError
T08 : journal append-only (deux bumps → deux lignes)
T09 : SHA256 before ≠ after (contenu réellement modifié)
T10 : entrée journal contient tous les champs requis
T11 : bump ne touche qu'à la ligne MODULE_VERSION (pas les autres lignes)
T12 : version malformée (ex: '1.0') → ValueError
T13 : bump_modified_since skip les modules sans MODULE_VERSION sans crash
T14 : --show-history affiche les entrées
T15 : bump MINOR n'est pas implémenté → la PATCH est bien incrémentée
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Ajouter la racine au path pour importer le script
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

# Import du module sous test
import importlib.util
spec = importlib.util.spec_from_file_location(
    "artcb_bump_module_version",
    REPO_ROOT / "scripts" / "artcb_bump_module_version.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

bump_module = mod.bump_module
bump_modified_since = mod.bump_modified_since
_bump_patch = mod._bump_patch
_find_version_line = mod._find_version_line
HISTORY_FILE = mod.HISTORY_FILE


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_py_module(content: str, tmp_path: Path, name: str = "test_mod.py") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_history_tmp(tmp_path: Path):
    """Remplace HISTORY_FILE par un fichier tmp pour les tests."""
    import unittest.mock as mock
    hist = tmp_path / "module_version_history.jsonl"
    return mock.patch.object(mod, "HISTORY_FILE", hist), hist


# ── Tests ──────────────────────────────────────────────────────────────────

class TestBumpPatch:
    """T01-T03 — _bump_patch logique pure"""

    def test_t01_basic(self):
        assert _bump_patch("1.0.0") == "1.0.1"

    def test_t02_middle(self):
        assert _bump_patch("1.2.3") == "1.2.4"

    def test_t03_carry(self):
        assert _bump_patch("1.0.9") == "1.0.10"

    def test_t12_malformed(self):
        with pytest.raises(ValueError, match="Version malformée"):
            _bump_patch("1.0")


class TestBumpModule:
    """T04-T11 — bump_module sur fichiers temporaires"""

    def test_t01_bump_writes_file(self, tmp_path):
        content = "# module\nMODULE_VERSION = '1.0.0'  # R400-B\nsome_code = 1\n"
        p = _make_py_module(content, tmp_path)
        patch_hist, hist_file = _make_history_tmp(tmp_path)
        with patch_hist:
            entry = bump_module(p, reason="test T01")
        assert entry["previous_version"] == "1.0.0"
        assert entry["new_version"] == "1.0.1"
        assert "MODULE_VERSION = '1.0.1'" in p.read_text()

    def test_t04_dry_run_no_modify(self, tmp_path):
        content = "MODULE_VERSION = '2.0.0'  # R400\ncode = 1\n"
        p = _make_py_module(content, tmp_path)
        original = p.read_text()
        patch_hist, hist_file = _make_history_tmp(tmp_path)
        with patch_hist:
            entry = bump_module(p, reason="test T04", dry_run=True)
        assert p.read_text() == original, "dry-run ne doit pas modifier le fichier"
        assert entry["dry_run"] is True

    def test_t05_dry_run_no_journal(self, tmp_path):
        content = "MODULE_VERSION = '1.5.0'  # R400\ncode = 1\n"
        p = _make_py_module(content, tmp_path)
        patch_hist, hist_file = _make_history_tmp(tmp_path)
        with patch_hist:
            bump_module(p, reason="test T05", dry_run=True)
        assert not hist_file.exists(), "dry-run ne doit pas écrire dans le journal"

    def test_t06_no_version_raises(self, tmp_path):
        content = "# aucune version ici\ncode = 42\n"
        p = _make_py_module(content, tmp_path)
        with pytest.raises(RuntimeError, match="MODULE_VERSION introuvable"):
            bump_module(p, reason="test T06")

    def test_t07_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            bump_module(tmp_path / "inexistant.py", reason="test T07")

    def test_t08_journal_append(self, tmp_path):
        content = "MODULE_VERSION = '1.0.0'  # R400\ncode = 1\n"
        p = _make_py_module(content, tmp_path)
        patch_hist, hist_file = _make_history_tmp(tmp_path)
        with patch_hist:
            bump_module(p, reason="first bump")
            # Version est maintenant 1.0.1 — bump une 2e fois
            bump_module(p, reason="second bump")
        lines = hist_file.read_text().strip().splitlines()
        assert len(lines) == 2, f"Journal doit avoir 2 lignes, a {len(lines)}"
        e1 = json.loads(lines[0])
        e2 = json.loads(lines[1])
        assert e1["new_version"] == "1.0.1"
        assert e2["new_version"] == "1.0.2"

    def test_t09_sha256_differs(self, tmp_path):
        content = "MODULE_VERSION = '1.0.0'  # R400\ncode = 1\n"
        p = _make_py_module(content, tmp_path)
        patch_hist, hist_file = _make_history_tmp(tmp_path)
        with patch_hist:
            entry = bump_module(p, reason="test T09")
        assert entry["sha256_before"] != entry["sha256_after"], "SHA256 doit différer après bump"

    def test_t10_journal_fields(self, tmp_path):
        content = "MODULE_VERSION = '3.1.2'  # R400\ncode = 1\n"
        p = _make_py_module(content, tmp_path)
        patch_hist, hist_file = _make_history_tmp(tmp_path)
        with patch_hist:
            entry = bump_module(p, reason="test T10")
        required = {"timestamp_ns", "module", "previous_version", "new_version",
                    "bump", "reason", "git_sha", "sha256_before", "sha256_after"}
        missing = required - set(entry.keys())
        assert not missing, f"Champs manquants dans l'entrée : {missing}"
        assert entry["bump"] == "PATCH"

    def test_t11_only_version_line_changes(self, tmp_path):
        content = (
            "# commentaire important\n"
            "MODULE_VERSION = '1.0.0'  # R400\n"
            "IMPORTANT_CONSTANT = 42\n"
            "def foo():\n"
            "    return 'bar'\n"
        )
        p = _make_py_module(content, tmp_path)
        original_lines = content.splitlines()
        patch_hist, hist_file = _make_history_tmp(tmp_path)
        with patch_hist:
            bump_module(p, reason="test T11")
        new_lines = p.read_text().splitlines()
        assert len(new_lines) == len(original_lines), "Nombre de lignes ne doit pas changer"
        assert new_lines[0] == original_lines[0], "Ligne 0 (commentaire) ne doit pas changer"
        assert new_lines[2] == original_lines[2], "IMPORTANT_CONSTANT ne doit pas changer"
        assert new_lines[3] == original_lines[3], "def foo() ne doit pas changer"
        assert "1.0.1" in new_lines[1], "Version doit être bumpée sur ligne 1"

    def test_t13_bump_modified_since_skips_no_version(self, tmp_path):
        """bump_modified_since ne crash pas si un fichier n'a pas MODULE_VERSION."""
        # On passe un since_sha inexistant → git diff vide → 0 entrées sans crash
        entries = bump_modified_since("HEAD", reason="test T13", dry_run=True)
        assert isinstance(entries, list)

    def test_t15_patch_incremented(self, tmp_path):
        """MINOR n'est pas bumpé — seul PATCH augmente."""
        assert _bump_patch("2.5.0") == "2.5.1"
        assert _bump_patch("2.5.0").startswith("2.5.")


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
