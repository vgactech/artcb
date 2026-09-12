"""R326 — chain status exposes public tip vs private suffix."""

from __future__ import annotations

import json
from pathlib import Path

from artcb.chain.manager import ChainManager


def test_tip_public_private_finds_public_before_private_suffix(tmp_path: Path) -> None:
    blocks = tmp_path / "blocks.jsonl"
    rows = [
        {
            "index": 0,
            "timestamp": "2026-09-12T00:00:00Z",
            "prev_hash": "0" * 64,
            "hash": "a" * 64,
            "visibility": "public",
            "signature": "test",
        },
        {
            "index": 1,
            "timestamp": "2026-09-12T00:00:01Z",
            "prev_hash": "a" * 64,
            "hash": "b" * 64,
            "visibility": "public",
            "signature": "test",
        },
        {
            "index": 2,
            "timestamp": "2026-09-12T00:00:02Z",
            "prev_hash": "b" * 64,
            "hash": "c" * 64,
            "visibility": "private",
            "signature": "test",
        },
        {
            "index": 3,
            "timestamp": "2026-09-12T00:00:03Z",
            "prev_hash": "c" * 64,
            "hash": "d" * 64,
            "visibility": "private",
            "signature": "test",
        },
    ]
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    split = mgr.tip_public_private()
    assert split["height_total"] == 4
    assert split["public_found"] is True
    assert split["public_last_index"] == 1
    assert split["private_suffix_lines"] == 2
