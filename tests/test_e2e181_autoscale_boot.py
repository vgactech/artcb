"""Phase 181 — Autoscale must not create a venv or wait on npm before uvicorn."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_autoscale_script_never_creates_venv() -> None:
    body = (ROOT / "scripts" / "replit_autoscale.sh").read_text(encoding="utf-8")
    assert "python3 -m venv" not in "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    assert "pip install" not in body
    assert "npm " not in body
    assert "uvicorn src.api.main:app" in body
    assert "replit_live_shim.py" in body
    assert "replit_git_sync.sh" in body
    sync = (ROOT / "scripts" / "replit_git_sync.sh").read_text(encoding="utf-8")
    assert "origin/$ARTCB_REPLIT_BRANCH" in sync or 'origin/"$ARTCB_REPLIT_BRANCH"' in sync


def test_replit_config_runs_autoscale_script() -> None:
    cfg = (ROOT / ".replit").read_text(encoding="utf-8")
    assert "scripts/replit_autoscale.sh" in cfg
    start = (ROOT / "scripts" / "replit_start.sh").read_text(encoding="utf-8")
    assert "exec bash \"$REPL_DIR/scripts/replit_autoscale.sh\"" in start
    assert "ARTCB_FULL_START" in start
