"""R327 — public append_block uses public tip, not private suffix height."""

from __future__ import annotations

import json
from pathlib import Path

from artcb.chain.manager import ChainManager


def test_public_dry_run_extends_public_tip_not_private_suffix(tmp_path: Path) -> None:
    blocks = tmp_path / "blocks.jsonl"
    rows = [
        {
            "index": 0,
            "timestamp": "2026-09-12T00:00:00Z",
            "prev_hash": "0" * 64,
            "hash": "a" * 64,
            "visibility": "public",
            "signature": "test",
            "graph_root": "g0",
            "merkle_root": "g0",
            "pol_score": 0.1,
            "graph_id": "g0",
        },
        {
            "index": 1,
            "timestamp": "2026-09-12T00:00:01Z",
            "prev_hash": "a" * 64,
            "hash": "b" * 64,
            "visibility": "public",
            "signature": "test",
            "graph_root": "g1",
            "merkle_root": "g1",
            "pol_score": 0.1,
            "graph_id": "g1",
        },
        {
            "index": 2,
            "timestamp": "2026-09-12T00:00:02Z",
            "prev_hash": "b" * 64,
            "hash": "c" * 64,
            "visibility": "private",
            "signature": "test",
            "graph_root": "g2",
            "merkle_root": "g2",
            "pol_score": 0.1,
            "graph_id": "g2",
        },
    ]
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    assert mgr.height() == 3
    constructed = mgr.append_block(
        graph_id="pub_next",
        graph_root="d" * 64,
        pol_score=0.1,
        visibility="public",
        dry_run=True,
    )
    assert constructed.index == 2  # public_last_index 1 + 1
    assert constructed.prev_hash == "b" * 64
    assert constructed.visibility == "public"
