"""Deterministic partition map — Hash(WorkID, Epoch, ParentRoot) mod N (162)."""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger("artcb.economics.partition_map")


def partition_id(work_id: str, epoch: int, parent_root: str, n_partitions: int) -> int:
    if n_partitions < 1:
        raise ValueError(f"n_partitions must be >= 1, got {n_partitions}")
    if not work_id:
        raise ValueError("work_id is required")
    material = f"{work_id}|{epoch}|{parent_root}".encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    pid = int(digest, 16) % n_partitions
    logger.debug("partition work=%s epoch=%s N=%s -> %s", work_id, epoch, n_partitions, pid)
    return pid


def assign_partitions(
    work_ids: list[str],
    *,
    epoch: int,
    parent_root: str,
    n_partitions: int,
) -> dict[str, int]:
    return {
        wid: partition_id(wid, epoch, parent_root, n_partitions) for wid in work_ids
    }
