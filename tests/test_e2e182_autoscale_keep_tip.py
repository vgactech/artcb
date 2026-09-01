"""Phase 182 — Autoscale must keep the branch tip, never rewind to an old PIN."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "replit_git_sync.sh"
AUTOSCALE = ROOT / "scripts" / "replit_autoscale.sh"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "artcb-test",
    "GIT_AUTHOR_EMAIL": "artcb-test@example.invalid",
    "GIT_COMMITTER_NAME": "artcb-test",
    "GIT_COMMITTER_EMAIL": "artcb-test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=check,
    )
    return (proc.stdout or "").strip()


def _shallow_clone(origin: Path, dest: Path) -> None:
    """HTTPS Autoscale clones do not share object alternates; local clones do."""
    _git(
        origin.parent,
        "clone",
        "--depth",
        "1",
        "--no-local",
        "--branch",
        "cursor/replit-sync-ready-16d8",
        f"file://{origin}",
        str(dest),
    )


def test_autoscale_never_checkouts_pin_fallback() -> None:
    auto = AUTOSCALE.read_text(encoding="utf-8")
    sync = SYNC.read_text(encoding="utf-8")
    live_lines = "\n".join(
        line for line in (auto + "\n" + sync).splitlines() if not line.lstrip().startswith("#")
    )
    assert "replit_git_sync.sh" in auto
    assert "fetch --unshallow" in sync
    assert "merge-base --is-ancestor" in sync
    assert "checkout tip=" in sync
    assert "keep_tip" in sync
    assert 'checkout --detach "$ARTCB_REPLIT_PIN_SHA"' not in live_lines
    assert "python3 -m venv" not in live_lines


def test_181_script_would_have_rewound_pin_string_gone() -> None:
    """The deadly 181 else-branch logged checkout pin= and detached the PIN."""
    auto = AUTOSCALE.read_text(encoding="utf-8")
    assert "checkout pin=" not in auto
    assert 'checkout --detach "$ARTCB_REPLIT_PIN_SHA"' not in auto


def _make_origin(tmp_path: Path) -> tuple[Path, str, str]:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "-b", "cursor/replit-sync-ready-16d8")
    _git(origin, "config", "user.email", "artcb-test@example.invalid")
    _git(origin, "config", "user.name", "artcb-test")
    (origin / "marker.txt").write_text("pin-178\n", encoding="utf-8")
    _git(origin, "add", "marker.txt")
    _git(origin, "commit", "-m", "audit(178): old pin")
    pin = _git(origin, "rev-parse", "HEAD")
    (origin / "marker.txt").write_text("tip-182\n", encoding="utf-8")
    _git(origin, "add", "marker.txt")
    _git(origin, "commit", "-m", "fix(182): keep tip")
    tip = _git(origin, "rev-parse", "HEAD")
    return origin, pin, tip


def _run_sync(dest: Path, origin: Path, pin: str) -> subprocess.CompletedProcess[str]:
    env = {
        **GIT_ENV,
        "ARTCB_REPLIT_PIN_SHA": pin,
        "ARTCB_REPLIT_BRANCH": "cursor/replit-sync-ready-16d8",
        "ARTCB_REPLIT_REMOTE": str(origin),
        "REPL_DIR": str(dest),
        "HOME": str(dest / "_home"),
    }
    (dest / "_home").mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(SYNC)],
        cwd=dest,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def test_shallow_clone_old_pin_keeps_tip_not_pin(tmp_path: Path) -> None:
    origin, pin, tip = _make_origin(tmp_path)
    dest = tmp_path / "dest"
    _shallow_clone(origin, dest)
    head_before = _git(dest, "rev-parse", "HEAD")
    assert head_before == tip
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", pin, tip],
        cwd=dest,
        env=GIT_ENV,
        capture_output=True,
    )
    assert ancestor.returncode != 0, "shallow clone must hide the old PIN"

    result = _run_sync(dest, origin, pin)
    log = (result.stdout or "") + (result.stderr or "")
    head_after = _git(dest, "rev-parse", "HEAD")
    assert head_after == tip
    assert head_after != pin
    assert f"checkout tip={tip}" in log
    assert f"checkout pin={pin}" not in log
    assert (dest / "marker.txt").read_text(encoding="utf-8") == "tip-182\n"


def test_exact_pin_equals_tip_checkouts_tip(tmp_path: Path) -> None:
    origin, _pin, tip = _make_origin(tmp_path)
    dest = tmp_path / "dest"
    _shallow_clone(origin, dest)
    result = _run_sync(dest, origin, tip)
    log = (result.stdout or "") + (result.stderr or "")
    assert _git(dest, "rev-parse", "HEAD") == tip
    assert f"checkout tip={tip}" in log
    assert "keep_tip" not in log


def test_helper_is_executable() -> None:
    mode = SYNC.stat().st_mode
    assert mode & stat.S_IXUSR
