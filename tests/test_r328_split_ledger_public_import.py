"""R328 — public certified write despite private suffix; holes/duplicates isolation."""

from __future__ import annotations

import json
from pathlib import Path

from nacl import encoding, signing

from artcb.chain import ffi
from artcb.chain.manager import ChainManager, GENESIS_PREV_HASH
from artcb.chain.split_ledger import ensure_split_ledgers, marker_path, public_blocks_path, private_blocks_path


def _pub_row(index: int, prev: str, h: str) -> dict:
    return {
        "index": index,
        "timestamp": f"2026-09-12T00:00:{index:02d}Z",
        "prev_hash": prev,
        "hash": h,
        "visibility": "public",
        "signature": "ed25519:" + ("ab" * 32),
        "graph_root": "g" * 64,
        "merkle_root": "g" * 64,
        "pol_score": 0.1,
        "graph_id": f"pub{index}",
    }


def _priv_row(index: int, prev: str, h: str) -> dict:
    return {
        "index": index,
        "timestamp": f"2026-09-12T01:00:{index % 60:02d}Z",
        "prev_hash": prev,
        "hash": h,
        "visibility": "private",
        "signature": "ed25519:" + ("cd" * 32),
        "graph_root": "p" * 64,
        "merkle_root": "p" * 64,
        "pol_score": 0.1,
        "graph_id": f"priv{index}",
    }


def test_split_migrate_preserves_legacy(tmp_path: Path) -> None:
    blocks = tmp_path / "blocks.jsonl"
    rows = [
        _pub_row(0, GENESIS_PREV_HASH, "a" * 64),
        _pub_row(1, "a" * 64, "b" * 64),
        _priv_row(2, "b" * 64, "c" * 64),
    ]
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    report = ensure_split_ledgers(blocks)
    assert report["migrated"] is True
    assert report["public_copied"] == 2
    assert report["private_copied"] == 1
    assert blocks.is_file() and blocks.stat().st_size > 0  # no wipe
    assert marker_path(blocks).is_file()
    assert public_blocks_path(blocks).is_file()
    assert private_blocks_path(blocks).is_file()
    # second call is idempotent
    report2 = ensure_split_ledgers(blocks)
    assert report2["already"] is True


def test_write_certified_public_despite_private_suffix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    blocks = tmp_path / "blocks.jsonl"
    # Public tip at 101; then 50 private lines that reuse / collide indices.
    rows = [
        _pub_row(100, GENESIS_PREV_HASH, "a" * 64),
        _pub_row(101, "a" * 64, "b" * 64),
    ]
    prev = "b" * 64
    for i in range(50):
        idx = 102 + i  # overlapping future public index space — legacy bug shape
        h = f"{i:064x}"
        rows.append(_priv_row(idx, prev, h))
        prev = h
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    assert mgr._split_active()
    tip = mgr.tip_public_private()
    assert tip["public_last_index"] == 101
    assert tip["private_suffix_lines"] == 50
    legacy_size = blocks.stat().st_size

    # Build a real hash-consistent public block 102 extending public tip.
    sk = signing.SigningKey.generate()
    index = 102
    prev_hash = "b" * 64
    ts = "2026-09-12T02:00:00Z"
    graph_root = "d" * 64
    merkle = graph_root
    pol = 0.1
    block_hash = ffi.build_block_hash(index, ts, prev_hash, graph_root, merkle, pol)
    sig = sk.sign(block_hash.encode("utf-8")).signature.hex()
    block = {
        "index": index,
        "timestamp": ts,
        "prev_hash": prev_hash,
        "graph_root": graph_root,
        "merkle_root": merkle,
        "pol_score": pol,
        "hash": block_hash,
        "signature": f"ed25519:{sig}",
        "graph_id": "pub102",
        "visibility": "public",
        "producer_public_key_b64": sk.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii"),
    }
    cert = {
        "seq": 102,
        "digest": block_hash,
        "view": 1,
        "q": 3,
        "replica_ids": ["a", "b", "c"],
        "commits": [],
    }
    # Bypass pbft_cert verify by temporarily stubbing — or craft valid cert.
    # import_extending requires verify_certificate for exclusive range.
    # Force exclusive_public_from high so cert check skips for this unit test.
    monkeypatch.setattr(
        "src.artcb.consensus.pbft_finality.exclusive_public_from",
        lambda *_a, **_k: 10_000_000,
    )
    monkeypatch.setattr(
        "artcb.consensus.pbft_finality.exclusive_public_from",
        lambda *_a, **_k: 10_000_000,
    )

    ok = mgr.write_certified_block(block, cert, from_node_id="test")
    assert ok is True
    tip2 = mgr.tip_public_private()
    assert tip2["public_last_index"] == 102
    assert tip2["private_suffix_lines"] == 50  # private preserved
    assert blocks.stat().st_size == legacy_size  # legacy not rewritten / wiped
    assert mgr.public_book().get_by_consensus_index(102) is not None
    assert mgr.private_book().height() == 50


def test_private_holes_and_duplicates_do_not_block_public(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    monkeypatch.setattr(
        "src.artcb.consensus.pbft_finality.exclusive_public_from",
        lambda *_a, **_k: 10_000_000,
    )
    monkeypatch.setattr(
        "artcb.consensus.pbft_finality.exclusive_public_from",
        lambda *_a, **_k: 10_000_000,
    )
    blocks = tmp_path / "blocks.jsonl"
    rows = [
        _pub_row(100, GENESIS_PREV_HASH, "a" * 64),
        _pub_row(101, "a" * 64, "b" * 64),
        # hole: skip 500
        _priv_row(501, "b" * 64, "c" * 64),
        # duplicate index 501
        _priv_row(501, "c" * 64, "d" * 64),
        _priv_row(502, "d" * 64, "e" * 64),
    ]
    blocks.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    assert mgr.tip_public_private()["public_last_index"] == 101

    sk = signing.SigningKey.generate()
    index = 102
    prev_hash = "b" * 64
    ts = "2026-09-12T03:00:00Z"
    graph_root = "f" * 64
    block_hash = ffi.build_block_hash(index, ts, prev_hash, graph_root, graph_root, 0.1)
    sig = sk.sign(block_hash.encode("utf-8")).signature.hex()
    block = {
        "index": index,
        "timestamp": ts,
        "prev_hash": prev_hash,
        "graph_root": graph_root,
        "merkle_root": graph_root,
        "pol_score": 0.1,
        "hash": block_hash,
        "signature": f"ed25519:{sig}",
        "graph_id": "pub102b",
        "visibility": "public",
        "producer_public_key_b64": sk.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii"),
    }
    assert mgr.write_certified_block(block, {"seq": 102, "digest": block_hash}, from_node_id="t")
    assert mgr.tip_public_private()["public_last_index"] == 102
    assert mgr.private_book().height() == 3


def test_watchdog_hypothesis_b_when_no_pending(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARTCB_SPLIT_LEDGER", "1")
    blocks = tmp_path / "blocks.jsonl"
    blocks.write_text(
        json.dumps(_pub_row(0, GENESIS_PREV_HASH, "a" * 64)) + "\n",
        encoding="utf-8",
    )
    mgr = ChainManager(blocks, key_path=tmp_path / "k", enable_security=False)
    from artcb.consensus.public_tip_watchdog import diagnose

    class _EmptyLog:
        def prepared_set(self):
            return []

    d = diagnose(mgr, pbft_log=_EmptyLog())
    assert d["pending_prepares"] == 0
    # age may be large → hypothesis b
    if d.get("age_sec") and d["age_sec"] > 60:
        assert d["hypothesis"] == "b_no_pending_pre_prepare_entry_path"
