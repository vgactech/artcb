"""R290 — thinking goes to ARTCB visibility=private, lossless, not summarized.

R291 — no application character cap on memos / think / agent events.
"""

from __future__ import annotations

import hashlib

import pytest

from api.agent_protocol_routes import EventBody
from api.ai_routes import MemoRequest, ThinkRequest
from artcb.live import ingest_prompt_file, ingest_thinking_file, split_lossless_chunks
from artcb.memory.repo_scope import chain_visibility, classify_path


def test_four_visibilities_exist_and_private_is_not_public() -> None:
    assert classify_path("src/artcb/node_registry.py") in {"public", "organization", "group", "private"}
    assert classify_path("logs/289_aep_live.json") == "private"
    assert classify_path("AUTO_PROMPT_ARTCB") == "group"
    assert chain_visibility("private") == "private"
    assert chain_visibility("organization") == "private"
    assert chain_visibility("group") == "private"
    assert chain_visibility("public") == "public"


def test_memo_content_max_constant_revoked() -> None:
    import artcb.live as live

    assert not hasattr(live, "MEMO_CONTENT_MAX")


def test_optional_split_is_not_a_memo_cap() -> None:
    raw = "α" * 1050
    chunks = split_lossless_chunks(raw, max_chars=1000)
    assert len(chunks) == 2
    assert "".join(chunks) == raw
    small = "hello thinking"
    assert split_lossless_chunks(small, max_chars=1000) == [small]


def test_memo_think_event_accept_over_32000_chars() -> None:
    big = "β" * 50_000
    memo = MemoRequest(content=big)
    think = ThinkRequest(question=big)
    event = EventBody(event_id="evt-no-cap-0001", content=big)
    assert len(memo.content) == 50_000
    assert len(think.question) == 50_000
    assert len(event.content) == 50_000
    for model in (MemoRequest, ThinkRequest, EventBody):
        schema = model.model_json_schema()
        props = schema.get("properties") or {}
        field = "content" if "content" in props else "question"
        assert "maxLength" not in props[field]


def test_ingest_prompt_and_thinking_post_full_text(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def fake_http(method, url, *, api_key=None, body=None, timeout=20):
        captured.append({"method": method, "url": url, "body": body, "timeout": timeout})
        digest = hashlib.sha256((body or {}).get("content", "").encode("utf-8")).hexdigest() if body else ""
        if method == "GET":
            return 200, {"block_index": 9999, "content_sha256": ""}
        return 200, {
            "block_index": 9999,
            "block_hash": "ab" * 32,
            "graph_id": "ai_memo_nocap",
            "content_sha256": digest,
        }

    monkeypatch.setattr("artcb.live.http_json", fake_http)
    raw = "γ" * 50_000
    prompt = tmp_path / "user_query.txt"
    thinking = tmp_path / "thinking.txt"
    prompt.write_text(raw, encoding="utf-8")
    thinking.write_text(raw, encoding="utf-8")
    out_p = ingest_prompt_file(prompt, url="https://152.228.144.34:8443", api_key="artcb_" + ("ab" * 32))
    out_t = ingest_thinking_file(thinking, url="https://152.228.144.34:8443", api_key="artcb_" + ("ab" * 32))
    assert out_p["truncated"] is False
    assert out_t["truncated"] is False
    assert out_p["chars"] == 50_000
    assert out_t["chars"] == 50_000
    assert out_t["n_chunks"] == 1
    posts = [c for c in captured if c["method"] == "POST"]
    assert posts[0]["body"]["content"] == raw
    assert posts[1]["body"]["content"] == raw
    assert posts[1]["body"]["visibility"] == "private"
    assert posts[1]["body"]["inject_context"] is False
    assert out_t["thinking_received"] is True
    assert out_t["thinking_integrity_verified"] is False
    assert out_t["thinking_recorded"] is False
