"""R299 — never-delete archive + Mac remains an official replica."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import artcb_live_bootstrap as boot  # noqa: E402
from artcb.node_registry import MAC_NODE_ID, official_pbft_replica_ids  # noqa: E402


def test_archive_keeps_previous_prompt_text(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "artcb_turn_prompt.txt"
    archive = tmp_path / "turn_prompts.jsonl"
    monkeypatch.setattr(boot, "TURN_PROMPT_ARCHIVE", archive)
    src.write_text("first prompt raw", encoding="utf-8")
    first = boot.archive_turn_prompt(src)
    src.write_text("second prompt raw full user_query", encoding="utf-8")
    second = boot.archive_turn_prompt(src)
    lines = archive.read_text(encoding="utf-8").splitlines()
    assert first["archived"] is True
    assert second["archived"] is True
    assert first["text"] == "first prompt raw"
    assert second["text"] == "second prompt raw full user_query"
    assert len(lines) == 2
    assert "first prompt raw" in archive.read_text(encoding="utf-8")
    assert "second prompt raw full user_query" in archive.read_text(encoding="utf-8")


def test_mac_still_official_replica() -> None:
    ids = official_pbft_replica_ids()
    assert MAC_NODE_ID in ids
    assert "ovh-node-1" in ids
    assert len(ids) >= 5
