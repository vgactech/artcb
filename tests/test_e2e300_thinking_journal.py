"""R300 — local reasoning journal never goes to ARTCB; Mac still replica."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import artcb_reason_log as reason  # noqa: E402
from artcb.node_registry import MAC_NODE_ID, official_pbft_replica_ids  # noqa: E402


def test_reason_log_append_only(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "agent_reasoning.jsonl"
    monkeypatch.setattr(reason, "REASON_PATH", dest)
    monkeypatch.setattr(reason, "TRACE_DIR", tmp_path)
    first = reason.append_reason(kind="process", text="step one", path=dest)
    second = reason.append_reason(kind="process", text="step two", path=dest)
    lines = dest.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert first["text"] == "step one"
    assert second["text"] == "step two"
    assert first["artcb_bound"] is False
    assert "step one" in dest.read_text(encoding="utf-8")


def test_after_thought_hook_writes_without_printing_thought(tmp_path: Path) -> None:
    dest = tmp_path / "agent_thoughts.jsonl"
    hook = ROOT / ".cursor" / "hooks" / "after_agent_thought.py"
    payload = json.dumps({"text": "secret thinking block", "duration_ms": 12})
    env = {**__import__("os").environ, "ARTCB_THOUGHT_LOG": str(dest), "PYTHONPATH": str(ROOT / "scripts")}
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
        env=env,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout.strip() or "{}") == {}
    assert "secret thinking block" not in proc.stdout
    stored = dest.read_text(encoding="utf-8")
    assert "secret thinking block" in stored
    assert '"artcb_bound":false' in stored.replace(" ", "")


def test_mac_still_replica_not_observer() -> None:
    assert MAC_NODE_ID in official_pbft_replica_ids()


def test_hooks_json_has_thought_and_compact() -> None:
    cfg = json.loads((ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
    assert "afterAgentThought" in cfg["hooks"]
    assert "preCompact" in cfg["hooks"]
    assert "sessionStart" in cfg["hooks"]
