"""Phase 185 — bind uvicorn in the same process that imported the app."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_autoscale_does_not_reimport_after_killing_shim() -> None:
    auto = (ROOT / "scripts" / "replit_autoscale.sh").read_text(encoding="utf-8")
    serve = (ROOT / "scripts" / "replit_serve.py").read_text(encoding="utf-8")
    live_auto = "\n".join(
        line for line in auto.splitlines() if not line.lstrip().startswith("#")
    )
    assert "replit_serve.py" in auto
    assert "ARTCB_SHIM_PID" in auto
    assert "exec \"$PYTHON\" -m uvicorn" not in live_auto
    assert "from src.api.main import app" in serve
    assert "uvicorn.run(app" in serve
    assert "_stop_shim" in serve
