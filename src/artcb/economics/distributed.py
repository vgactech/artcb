"""Four-node concurrent network for Simulation 167 — not a production P2P stack.

Topology (audit §31)::

    A  normal
    B  normal
    C  artificial latency
    D  controlled adversarial (double-settle, partition)

Canonical tip: longest valid chain; tie → lexicographically smaller tip hash.
Finality V-05 B: N confirmations (default 2). Pending user lock.
"""

from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.artcb.chain.manager import ChainManager
from src.artcb.economics.economic_snapshot import (
    DEFAULT_FINALITY_CONFIRMATIONS,
    AlreadySettled,
    EconomicStateSnapshot,
    EpochCoordinator,
    SettlementLedger,
    settlement_id,
)
from src.artcb.mining.protocol import ProtocolEngine, ProtocolReject
from src.artcb.wallet.manager import WalletManager

logger = logging.getLogger("artcb.economics.distributed")


@dataclass
class SimNode:
    node_id: str
    role: str
    latency_ms: int
    engine: ProtocolEngine
    coordinator: EpochCoordinator
    clock_skew_seconds: int = 0
    adversarial: bool = False
    partition_group: str = "G1"
    events: list[dict[str, Any]] = field(default_factory=list)

    def tip_hash(self) -> str:
        return self.engine.chain.last_hash() or ("0" * 64)

    def height(self) -> int:
        blocks = self.engine.chain.list_blocks()
        return len(blocks)

    def record(self, kind: str, **payload: Any) -> None:
        self.events.append({"node": self.node_id, "kind": kind, **payload})


def canonical_tip(nodes: list[SimNode]) -> tuple[str, int, str]:
    """Return (node_id, height, tip_hash) of the canonical chain."""
    ranked = sorted(
        ((n.height(), n.tip_hash(), n.node_id) for n in nodes),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    height, tip, nid = ranked[0]
    logger.debug("canonical tip node=%s height=%s hash=%s", nid, height, tip[:16])
    return nid, height, tip


def is_final(*, height: int, tip_height: int, confirmations: int = DEFAULT_FINALITY_CONFIRMATIONS) -> bool:
    return (tip_height - height) >= confirmations


def _people(engine: ProtocolEngine) -> None:
    engine.humans.bootstrap_creator(human_id="H-A", address="A")
    for hid, addr in (("H-B", "B"), ("H-C", "C"), ("H-D", "D"), ("H-E", "E")):
        engine.humans.register_candidate(human_id=hid, address=addr)
        engine.humans.creator_direct_validate(hid, creator_id="H-A")
    engine.machines.register(machine_id="M1", owner_address="A")
    engine.machines.register(machine_id="M2", owner_address="A", bound_human_address="B")
    engine.machines.register(machine_id="M3", owner_address="A", bound_human_address="C")
    engine.machines.register(machine_id="M4", owner_address="A", bound_human_address="D")
    # B already has M1-equivalent so a later transfer of A's extra is not B's first machine
    engine.machines.register(machine_id="MB1", owner_address="B")


def build_nodes(root: Path, *, ledger: SettlementLedger) -> list[SimNode]:
    del ledger  # shared at call site of execute
    specs = (
        ("A", "normal", 5, 0, False, "G1"),
        ("B", "normal", 12, 0, False, "G1"),
        ("C", "latency", 80, 7, False, "G2"),
        ("D", "adversarial", 20, 0, True, "G2"),
    )
    nodes: list[SimNode] = []
    for nid, role, lat, skew, adv, group in specs:
        ndir = root / f"node_{nid}"
        ndir.mkdir(parents=True, exist_ok=True)
        chain = ChainManager(
            ndir / "blocks.jsonl",
            key_path=ndir / "chain.key",
            enable_security=True,
        )
        engine = ProtocolEngine(
            ndir,
            chain=chain,
            wallet_manager=WalletManager(ndir / "wallets"),
        )
        _people(engine)
        nodes.append(
            SimNode(
                node_id=nid,
                role=role,
                latency_ms=lat,
                engine=engine,
                coordinator=EpochCoordinator(grace_seconds=1),  # sim: 1s not 24h
                clock_skew_seconds=skew,
                adversarial=adv,
                partition_group=group,
            )
        )
    return nodes


def begin_aligned_epoch(nodes: list[SimNode], *, parent_root: str) -> dict[str, EconomicStateSnapshot]:
    from datetime import UTC, datetime

    shared_now = datetime.now(UTC)
    snaps: dict[str, EconomicStateSnapshot] = {}
    for node in nodes:
        snap = node.coordinator.begin_epoch(
            machines=node.engine.machines,
            humans=node.engine.humans,
            parent_root=parent_root,
            work_ids_open=[],
            demographic_digest=node.engine.demographic.digest(),
            now=shared_now,
        )
        snaps[node.node_id] = snap
        node.record("epoch_start", epoch=snap.epoch, digest=snap.digest())
    return snaps


def execute_on_node(
    node: SimNode,
    *,
    snap: EconomicStateSnapshot,
    ledger: SettlementLedger,
    work_id: str,
    machine_ids: list[str],
    graph_suffix: str,
    provider_scores: dict[str, float] | None = None,
    job_payment: dict | None = None,
    interval_seconds: float = 600.0,
) -> dict[str, Any]:
    if node.latency_ms:
        time.sleep(min(node.latency_ms, 80) / 1000.0)
    try:
        result = node.engine.execute_block(
            graph_id=f"g-{node.node_id}-{graph_suffix}",
            graph_root=hashlib.sha256(f"{node.node_id}:{work_id}:{graph_suffix}".encode()).hexdigest(),
            pol_score=0.85,
            work_id=work_id,
            machine_ids=machine_ids,
            provider_scores=provider_scores,
            interval_seconds=interval_seconds,
            epoch_snapshot=snap,
            settlement_ledger=ledger,
            node_id=node.node_id,
            job_payment=job_payment,
        )
        payload = {
            "ok": True,
            "node": node.node_id,
            "work_id": work_id,
            "block_index": result.block_index,
            "block_hash": result.block_hash,
            "economic_root": result.economic_root,
            "paid": result.total_paid_satoshi,
            "r_block": result.r_block_satoshi,
            "supply": result.supply_satoshi,
            "settlement_id": (result.phases.get("snapshot") or {}).get("settlement_id"),
            "h_adult": result.h_adult,
        }
        node.record("block", **payload)
        return payload
    except (ProtocolReject, AlreadySettled) as exc:
        payload = {
            "ok": False,
            "node": node.node_id,
            "work_id": work_id,
            "error": type(exc).__name__,
            "detail": str(exc)[:240],
        }
        node.record("reject", **payload)
        return payload


def concurrent_settle(
    nodes: list[SimNode],
    snaps: dict[str, EconomicStateSnapshot],
    ledger: SettlementLedger,
    *,
    work_id: str,
    machine_ids: list[str],
    graph_suffix: str,
    provider_scores: dict[str, float] | None = None,
    job_payment: dict | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(nodes)) as pool:
        futs = {
            pool.submit(
                execute_on_node,
                node,
                snap=snaps[node.node_id],
                ledger=ledger,
                work_id=work_id,
                machine_ids=machine_ids,
                graph_suffix=graph_suffix,
                provider_scores=provider_scores,
                job_payment=job_payment,
            ): node.node_id
            for node in nodes
        }
        for fut in as_completed(futs):
            out.append(fut.result())
    return out


def gossip_after_heal(nodes: list[SimNode]) -> dict[str, Any]:
    nid, height, tip = canonical_tip(nodes)
    return {
        "canonical_node": nid,
        "canonical_height": height,
        "canonical_tip": tip,
        "heights": {n.node_id: n.height() for n in nodes},
        "tips": {n.node_id: n.tip_hash() for n in nodes},
        "rule": "longest valid chain; tie = smaller tip hash",
        "finality": {
            "model": "N_confirmations",
            "n": DEFAULT_FINALITY_CONFIRMATIONS,
            "pending_validation": "V-05",
        },
    }


def sid_for(work_id: str, snap: EconomicStateSnapshot) -> str:
    return settlement_id(
        work_id=work_id,
        snapshot_digest=snap.digest(),
        protocol_version=snap.protocol_version,
    )
