"""R328 — split public/private ledgers without wiping the mixed book.

Legacy ``chain/blocks.jsonl`` is retained as forensic archive (never deleted).
After migration, consensus public appends go to ``chain/public/blocks.jsonl`` and
private appends to ``chain/private/blocks.jsonl``.

2026-09-12T19:00:00Z
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
from pathlib import Path
from typing import Any

from src.artcb.chain.book_index import BookIndex

logger = logging.getLogger(__name__)

MARKER_NAME = ".artcb_split_ledger_v1"
GENESIS_PREV = "0" * 64


def chain_dir_from_blocks(blocks_path: Path) -> Path:
    return Path(blocks_path).parent


def public_blocks_path(blocks_path: Path) -> Path:
    return chain_dir_from_blocks(blocks_path) / "public" / "blocks.jsonl"


def private_blocks_path(blocks_path: Path) -> Path:
    return chain_dir_from_blocks(blocks_path) / "private" / "blocks.jsonl"


def marker_path(blocks_path: Path) -> Path:
    return chain_dir_from_blocks(blocks_path) / MARKER_NAME


def is_public_block(block: dict[str, Any]) -> bool:
    vis = str(block.get("visibility") or "").lower()
    if vis == "public":
        return True
    if isinstance(block.get("pbft_cert"), dict):
        return True
    return False


def ensure_split_ledgers(legacy_blocks_path: Path) -> dict[str, Any]:
    """Migrate mixed jsonl → public/ + private/ once. Never deletes legacy."""
    legacy = Path(legacy_blocks_path)
    cdir = chain_dir_from_blocks(legacy)
    pub_path = public_blocks_path(legacy)
    priv_path = private_blocks_path(legacy)
    mark = marker_path(legacy)
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    priv_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "marker": str(mark),
        "legacy": str(legacy),
        "public": str(pub_path),
        "private": str(priv_path),
        "migrated": False,
        "already": False,
        "public_copied": 0,
        "private_copied": 0,
        "legacy_lines": 0,
    }
    if mark.is_file():
        report["already"] = True
        return report

    pub_empty = (not pub_path.is_file()) or pub_path.stat().st_size == 0
    if not legacy.is_file() or legacy.stat().st_size == 0:
        mark.write_text(
            json.dumps({"ts": "empty_legacy", "version": 1}) + "\n", encoding="utf-8"
        )
        report["migrated"] = True
        return report

    if not pub_empty:
        # Public ledger already populated — just mark.
        mark.write_text(
            json.dumps({"ts": "public_preexisting", "version": 1}) + "\n", encoding="utf-8"
        )
        report["already"] = True
        return report

    seen_pub: set[str] = set()
    seen_priv: set[str] = set()
    with legacy.open(encoding="utf-8") as src:
        for line in src:
            raw = line.strip()
            if not raw:
                continue
            report["legacy_lines"] += 1
            try:
                blk = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(blk, dict):
                continue
            h = str(blk.get("hash") or "")
            if is_public_block(blk):
                if h and h in seen_pub:
                    continue
                if h:
                    seen_pub.add(h)
                with pub_path.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(blk, ensure_ascii=False, separators=(",", ":")) + "\n")
                report["public_copied"] += 1
            else:
                if h and h in seen_priv:
                    continue
                if h:
                    seen_priv.add(h)
                with priv_path.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(blk, ensure_ascii=False, separators=(",", ":")) + "\n")
                report["private_copied"] += 1

    mark.write_text(
        json.dumps(
            {
                "version": 1,
                "public_copied": report["public_copied"],
                "private_copied": report["private_copied"],
                "legacy_lines": report["legacy_lines"],
                "legacy_preserved": True,
                "wipe": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report["migrated"] = True
    logger.info(
        "R328 split ledger migrated public=%s private=%s legacy_kept=%s",
        report["public_copied"],
        report["private_copied"],
        legacy,
    )
    return report


def open_split_books(legacy_blocks_path: Path) -> tuple[BookIndex, BookIndex, dict[str, Any]]:
    report = ensure_split_ledgers(legacy_blocks_path)
    pub = BookIndex(public_blocks_path(legacy_blocks_path))
    priv = BookIndex(private_blocks_path(legacy_blocks_path))
    return pub, priv, report
