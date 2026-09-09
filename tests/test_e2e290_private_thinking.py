"""R290 — thinking goes to ARTCB visibility=private, lossless, not summarized."""

from __future__ import annotations

from artcb.live import MEMO_CONTENT_MAX, split_lossless_chunks
from artcb.memory.repo_scope import chain_visibility, classify_path


def test_four_visibilities_exist_and_private_is_not_public() -> None:
    assert classify_path("src/artcb/node_registry.py") in {"public", "organization", "group", "private"}
    assert classify_path("logs/289_aep_live.json") == "private"
    assert classify_path("AUTO_PROMPT_ARTCB") == "group"
    assert chain_visibility("private") == "private"
    assert chain_visibility("organization") == "private"
    assert chain_visibility("group") == "private"
    assert chain_visibility("public") == "public"


def test_thinking_chunks_are_lossless_not_a_summary() -> None:
    raw = "α" * (MEMO_CONTENT_MAX + 50)
    chunks = split_lossless_chunks(raw)
    assert len(chunks) == 2
    assert "".join(chunks) == raw
    assert all(len(c) <= MEMO_CONTENT_MAX for c in chunks)
    small = "hello thinking"
    assert split_lossless_chunks(small) == [small]
