"""TestChainManager — isolated TEST ledger (test_chain.jsonl).

Architecture (rapport 356 §12 / rapport audit session 2026-09-16):
  - test_chain.jsonl is PHYSICALLY SEPARATE from chain.jsonl (MAINNET).
  - No path can cross the TEST→MAINNET or MAINNET→TEST frontier.
  - A real Genesis block (index=0) is produced deterministically from
    TEST_GENESIS_HASH so that subsequent blocks have a valid prev_hash chain.
  - TestChainManager accepts ONLY blocks signed with a TEST-domain key
    (network_id == TEST_NETWORK_ID in the block's domain_id field).
  - Balance queries operate exclusively on test_chain.jsonl.
  - TEST asset unit = tARTCB (TEST_ASSET_NAME).

This module is purely Python (no C FFI dependency) so it can be used in
unit tests without the native extension.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artcb.testdomain.policy import (
    TEST_ASSET_NAME,
    TEST_GENESIS_HASH,
    TEST_NETWORK_ID,
    TEST_PROTOCOL_VERSION,
    domain_of_address,
    reject_cross_domain_transfer,
)

logger = logging.getLogger("artcb.testdomain.chain")

# ──────────────────────────────────────────────────────────────────────────────
# Pure-Python block hash (mirrors C ffi.build_block_hash without the extension)
# ──────────────────────────────────────────────────────────────────────────────

def _build_test_block_hash(
    index: int,
    timestamp: str,
    prev_hash: str,
    graph_root: str,
    merkle_root: str,
    pol_score: float,
    network_id: str = TEST_NETWORK_ID,
) -> str:
    """Deterministic SHA-256 block hash including network_id for domain separation.

    MAINNET blocks use C ffi.build_block_hash (no network_id in digest).
    TEST blocks add network_id so that a TEST block hash is never equal to
    a MAINNET block hash for identical payload — cross-chain replay impossible.
    """
    material = (
        f"{index}|{timestamp}|{prev_hash}|{graph_root}|{merkle_root}"
        f"|{pol_score:.6f}|{network_id}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Genesis block
# ──────────────────────────────────────────────────────────────────────────────

_GENESIS_PREV_HASH = "0" * 64
_GENESIS_GRAPH_ROOT = hashlib.sha256(b"ARTCB/TEST/GENESIS/V1").hexdigest()
_GENESIS_TIMESTAMP = "2026-09-16T00:00:00Z"


def _make_genesis_block() -> dict:
    """Produce the TEST Genesis block (index=0).

    The genesis_hash stored in the block equals TEST_GENESIS_HASH (the declared
    protocol identifier). The block's own ``hash`` field is computed by
    _build_test_block_hash so it is deterministic and verifiable.
    """
    gh = _build_test_block_hash(
        index=0,
        timestamp=_GENESIS_TIMESTAMP,
        prev_hash=_GENESIS_PREV_HASH,
        graph_root=_GENESIS_GRAPH_ROOT,
        merkle_root=_GENESIS_GRAPH_ROOT,
        pol_score=0.0,
        network_id=TEST_NETWORK_ID,
    )
    return {
        "index": 0,
        "timestamp": _GENESIS_TIMESTAMP,
        "prev_hash": _GENESIS_PREV_HASH,
        "graph_root": _GENESIS_GRAPH_ROOT,
        "merkle_root": _GENESIS_GRAPH_ROOT,
        "pol_score": 0.0,
        "hash": gh,
        "signature": "",
        "graph_id": "test-genesis",
        "visibility": "public",
        "group_id": None,
        "block_reward": 0,
        "contributors": [],
        "network_id": TEST_NETWORK_ID,
        "protocol_version": TEST_PROTOCOL_VERSION,
        "genesis_hash": TEST_GENESIS_HASH,
        "domain": "TEST",
        "asset": TEST_ASSET_NAME,
    }


# ──────────────────────────────────────────────────────────────────────────────
# TestChainManager
# ──────────────────────────────────────────────────────────────────────────────

class TestChainError(Exception):
    """Raised when a TEST chain invariant is violated."""


class TestChainManager:
    """Manages the TEST domain blockchain (test_chain.jsonl).

    Rules:
      1. The file is ALWAYS separate from MAINNET chain.jsonl.
      2. The first call to ensure_genesis() writes block 0 if absent.
      3. append_block() rejects any block missing network_id == TEST_NETWORK_ID.
      4. get_balance() returns tARTCB, never ARTCB.
      5. Cross-domain transfers are rejected at append time.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        from src.artcb.config import load_settings

        settings = load_settings()
        root = data_dir or settings.data_dir
        # INVARIANT: test chain file must not be chain.jsonl
        self.blocks_path: Path = root / "test_chain.jsonl"
        assert self.blocks_path.name != "chain.jsonl", (
            "TEST chain must not overwrite MAINNET chain.jsonl"
        )
        self.blocks_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._genesis_hash: str = ""  # populated by ensure_genesis()

    # ── Genesis ───────────────────────────────────────────────────────────────

    def ensure_genesis(self) -> dict:
        """Write Genesis block if test_chain.jsonl is empty/absent.

        Returns the Genesis block dict (either read or freshly written).
        Safe to call multiple times (idempotent).
        """
        with self._lock:
            if self.blocks_path.exists():
                with self.blocks_path.open(encoding="utf-8") as fh:
                    first = fh.readline().strip()
                if first:
                    blk = json.loads(first)
                    if blk.get("index") == 0:
                        self._genesis_hash = str(blk.get("hash", ""))
                        return blk

            genesis = _make_genesis_block()
            line = json.dumps(genesis, ensure_ascii=False, separators=(",", ":"))
            with self.blocks_path.open("w", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._genesis_hash = genesis["hash"]
            logger.info(
                "TEST Genesis written hash=%s path=%s",
                self._genesis_hash[:16],
                self.blocks_path,
            )
            return genesis

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _read_all(self) -> list[dict]:
        if not self.blocks_path.exists():
            return []
        blocks: list[dict] = []
        with self.blocks_path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    blocks.append(json.loads(raw))
        return blocks

    def height(self) -> int:
        """Number of blocks in test_chain.jsonl (including Genesis)."""
        if not self.blocks_path.exists():
            return 0
        count = 0
        with self.blocks_path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    count += 1
        return count

    def last_hash(self) -> str:
        """Hash of the last block, or GENESIS_PREV_HASH if chain is empty."""
        if not self.blocks_path.exists():
            return _GENESIS_PREV_HASH
        last_line = ""
        with self.blocks_path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last_line = line.strip()
        if not last_line:
            return _GENESIS_PREV_HASH
        try:
            return str(json.loads(last_line).get("hash") or _GENESIS_PREV_HASH)
        except (json.JSONDecodeError, KeyError):
            return _GENESIS_PREV_HASH

    def get_block(self, index: int) -> dict | None:
        for blk in self._read_all():
            if blk.get("index") == index:
                return blk
        return None

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_block(self, block: dict) -> None:
        """Enforce TEST domain invariants before appending.

        Raises TestChainError with a descriptive reason on any violation.
        """
        # 1. network_id must be TEST
        nid = block.get("network_id", "")
        if nid != TEST_NETWORK_ID:
            raise TestChainError(
                f"reject_wrong_network_id: got '{nid}', want '{TEST_NETWORK_ID}'"
            )
        # 2. genesis_hash must match TEST
        gh = block.get("genesis_hash", "")
        if gh and gh != TEST_GENESIS_HASH:
            raise TestChainError(
                f"reject_wrong_genesis_hash: got '{gh}', want '{TEST_GENESIS_HASH}'"
            )
        # 3. domain must not be MAINNET
        domain = block.get("domain", "")
        if domain == "MAINNET":
            raise TestChainError("reject_mainnet_block_in_test_chain")
        # 4. Cross-domain address check on contributors
        for contrib in block.get("contributors") or []:
            addr = contrib.get("address") or contrib.get("wallet_address") or ""
            if not addr:
                continue
            if domain_of_address(addr) == "MAINNET":
                raise TestChainError(
                    f"reject_mainnet_contributor_in_test_block: {addr}"
                )
        # 5. Asset must not be ARTCB (production) — tARTCB or empty allowed
        asset = block.get("asset", "")
        if asset and asset != TEST_ASSET_NAME:
            raise TestChainError(
                f"reject_wrong_asset: got '{asset}', want '{TEST_ASSET_NAME}' or empty"
            )

    # ── Append ────────────────────────────────────────────────────────────────

    def append_block(self, block: dict) -> dict:
        """Validate and append a new TEST block.

        The block must include at minimum:
          network_id, prev_hash, graph_root, merkle_root, pol_score,
          contributors (list of {address, reward_satoshi}).

        Returns the completed block dict with index, timestamp, hash filled in.
        Raises TestChainError on any invariant violation.
        """
        self.ensure_genesis()
        with self._lock:
            self._validate_block(block)

            h = self.height()
            prev = self.last_hash()

            # Check prev_hash linkage (if caller supplied one)
            supplied_prev = block.get("prev_hash")
            if supplied_prev and supplied_prev != prev:
                raise TestChainError(
                    f"reject_prev_hash_mismatch: got '{supplied_prev[:16]}…', "
                    f"want '{prev[:16]}…'"
                )

            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            graph_root = block.get("graph_root") or hashlib.sha256(
                f"test-block-{h}".encode()
            ).hexdigest()
            merkle_root = block.get("merkle_root") or graph_root
            pol_score = float(block.get("pol_score", 1.0))

            bh = _build_test_block_hash(
                index=h,
                timestamp=ts,
                prev_hash=prev,
                graph_root=graph_root,
                merkle_root=merkle_root,
                pol_score=pol_score,
            )

            completed: dict[str, Any] = {
                **block,
                "index": h,
                "timestamp": ts,
                "prev_hash": prev,
                "graph_root": graph_root,
                "merkle_root": merkle_root,
                "pol_score": pol_score,
                "hash": bh,
                "network_id": TEST_NETWORK_ID,
                "protocol_version": TEST_PROTOCOL_VERSION,
                "genesis_hash": TEST_GENESIS_HASH,
                "domain": "TEST",
                "asset": TEST_ASSET_NAME,
            }

            line = json.dumps(completed, ensure_ascii=False, separators=(",", ":"))
            with self.blocks_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

            logger.info(
                "TEST block appended index=%d hash=%s contributors=%d",
                h,
                bh[:16],
                len(completed.get("contributors") or []),
            )
            return completed

    # ── Balance ───────────────────────────────────────────────────────────────

    def get_balance(self, address: str) -> dict:
        """Calculate tARTCB balance for a TEST wallet address.

        INVARIANT: only TEST-domain addresses are accepted.
        Returns {"address": …, "balance_satoshi": int, "asset": "tARTCB", …}.
        """
        if domain_of_address(address) == "MAINNET":
            raise TestChainError(
                f"reject_mainnet_address_in_test_balance_query: {address}"
            )

        total_satoshi = 0
        tx_count = 0
        for blk in self._read_all():
            for contrib in blk.get("contributors") or []:
                addr = contrib.get("address") or contrib.get("wallet_address") or ""
                if addr == address:
                    total_satoshi += int(contrib.get("reward_satoshi", 0))
                    tx_count += 1

        return {
            "address": address,
            "balance_satoshi": total_satoshi,
            "balance_tartcb": total_satoshi / 1e8,
            "asset": TEST_ASSET_NAME,
            "tx_count": tx_count,
            "domain": "TEST",
            "mainnet_balance": None,  # explicit: TEST balance ≠ MAINNET balance
        }

    # ── Summary ───────────────────────────────────────────────────────────────

    def chain_info(self) -> dict:
        """Return chain metadata without reading all blocks."""
        h = self.height()
        lh = self.last_hash()
        return {
            "network_id": TEST_NETWORK_ID,
            "protocol_version": TEST_PROTOCOL_VERSION,
            "genesis_hash": TEST_GENESIS_HASH,
            "domain": "TEST",
            "asset": TEST_ASSET_NAME,
            "height": h,
            "last_hash": lh,
            "blocks_path": str(self.blocks_path),
            "mainnet_chain_isolated": True,
        }
