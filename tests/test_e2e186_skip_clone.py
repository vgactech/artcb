"""Phase 186 — Autoscale must not git-clone on every boot (SIGTERM at ~16s)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "replit_git_sync.sh"
AUTOSCALE = ROOT / "scripts" / "replit_autoscale.sh"


def test_autoscale_skips_clone_without_force_flag() -> None:
    sync = SYNC.read_text(encoding="utf-8")
    auto = AUTOSCALE.read_text(encoding="utf-8")
    assert "keep snapshot no_clone" in sync
    assert "ARTCB_REPLIT_FORCE_CLONE" in sync
    assert "ARTCB_REPLIT_PIN_SHA" in auto
    live = "\n".join(
        line for line in sync.splitlines() if not line.lstrip().startswith("#")
    )
    assert "fetch --unshallow" not in live


def test_no_git_keeps_snapshot_and_does_not_clone(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    (dest / "scripts").mkdir(parents=True)
    (dest / "scripts" / "replit_autoscale.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (dest / "marker.txt").write_text("published-snapshot\n", encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(dest / "_home"),
        "REPL_DIR": str(dest),
        "ARTCB_REPLIT_REMOTE": str(tmp_path / "does-not-exist.git"),
        "ARTCB_REPLIT_PIN_SHA": "99e83b9996aee66666d2c45107aaae8e78339c6b",
    }
    (dest / "_home").mkdir()
    result = subprocess.run(
        ["bash", str(SYNC)],
        cwd=dest,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    log = (result.stdout or "") + (result.stderr or "")
    assert "keep snapshot no_clone" in log
    assert "Cloning into" not in log
    assert (dest / "marker.txt").read_text(encoding="utf-8") == "published-snapshot\n"
