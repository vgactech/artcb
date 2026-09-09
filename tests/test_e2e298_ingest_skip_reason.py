"""R298 — ingest skip reason must not lie when the file is set."""

from __future__ import annotations

from artcb.live import prompt_file_skipped_reason


def test_unset_only_when_path_empty() -> None:
    assert "unset" in prompt_file_skipped_reason("")
    assert prompt_file_skipped_reason("   ") == prompt_file_skipped_reason("")
    assert prompt_file_skipped_reason("/tmp/artcb_turn_prompt.txt") == "file_missing"
