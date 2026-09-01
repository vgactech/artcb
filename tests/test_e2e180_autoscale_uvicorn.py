"""Phase 180 — Autoscale must bind FastAPI, not die after killing the shim."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_start_script_prefers_pythonlibs_over_empty_venv() -> None:
    body = (ROOT / "scripts" / "replit_start.sh").read_text(encoding="utf-8")
    assert "skip empty venv" in body
    assert "_python_serves" in body
    assert "python3 -m venv \"$VENV\"" not in body or "--system-site-packages" in body
    assert "keeping shim, not launching uvicorn" in body
    assert "preflight import src.api.main" in body
    assert "uvicorn died immediately — restarting live_shim" in body


def test_pin_fast_forward_stays_on_named_branch() -> None:
    body = (ROOT / "scripts" / "replit_start.sh").read_text(encoding="utf-8")
    assert "ff_from_pin" in body
    assert "merge-base --is-ancestor" in body
    assert "origin/main" not in body.split("ff_from_pin")[1][:400]
    assert 'reset --hard "origin/' not in body
