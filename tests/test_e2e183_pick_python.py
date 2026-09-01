"""Phase 183 — Autoscale prefers Replit Python over Nix, never creates a venv."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PICK = ROOT / "scripts" / "replit_pick_python.sh"
AUTOSCALE = ROOT / "scripts" / "replit_autoscale.sh"

FAKE_OK = """#!/bin/sh
if [ \"$1\" = \"-c\" ]; then exit 0; fi
exit 0
"""
FAKE_FAIL = """#!/bin/sh
if [ \"$1\" = \"-c\" ]; then exit 1; fi
exit 1
"""


def _write_py(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_pick(home: Path, repl: Path, extra_path: str = "") -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HOME": str(home),
        "REPL_DIR": str(repl),
        "PATH": f"{extra_path}:{os.environ.get('PATH', '/usr/bin:/bin')}" if extra_path else os.environ.get("PATH", "/usr/bin:/bin"),
    }
    env.pop("ARTCB_PYTHON", None)
    return subprocess.run(
        ["bash", str(PICK)],
        cwd=repl,
        env=env,
        capture_output=True,
        text=True,
    )


def test_autoscale_sources_picker_and_never_creates_venv() -> None:
    auto = AUTOSCALE.read_text(encoding="utf-8")
    pick = PICK.read_text(encoding="utf-8")
    live = "\n".join(
        line
        for line in (auto + "\n" + pick).splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "replit_pick_python.sh" in auto
    assert "${HOME}/venv/bin/python3" in pick
    assert pick.find("${HOME}/venv/bin/python3") < pick.find("command -v python3")
    assert "python3 -m venv" not in live


def test_prefers_replit_venv_over_nix(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repl = tmp_path / "repl"
    repl.mkdir()
    venv_py = home / "venv" / "bin" / "python3"
    nix_py = home / "nix" / "python3"
    _write_py(venv_py, FAKE_OK)
    _write_py(nix_py, FAKE_OK)
    result = _run_pick(home, repl, extra_path=str(home / "nix"))
    assert result.returncode == 0, result.stderr
    out = (result.stdout or "").strip().splitlines()[-1]
    assert out == str(venv_py)


def test_skips_empty_venv_then_uses_nix(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repl = tmp_path / "repl"
    repl.mkdir()
    _write_py(home / "venv" / "bin" / "python3", FAKE_FAIL)
    nix_py = home / "nix" / "python3"
    _write_py(nix_py, FAKE_OK)
    result = _run_pick(home, repl, extra_path=str(home / "nix"))
    assert result.returncode == 0, result.stderr
    out = (result.stdout or "").strip().splitlines()[-1]
    assert out == str(nix_py)


def test_prefers_pythonlibs_bin_over_nix(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repl = tmp_path / "repl"
    libs_py = repl / ".pythonlibs" / "bin" / "python3"
    nix_py = home / "nix" / "python3"
    _write_py(libs_py, FAKE_OK)
    _write_py(nix_py, FAKE_OK)
    result = _run_pick(home, repl, extra_path=str(home / "nix"))
    assert result.returncode == 0, result.stderr
    out = (result.stdout or "").strip().splitlines()[-1]
    assert out == str(libs_py)


def test_picker_is_executable() -> None:
    assert PICK.stat().st_mode & stat.S_IXUSR
