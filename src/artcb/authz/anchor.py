"""Anchor a public domain commitment in blocks.jsonl (rapport 219 / P-218-2).

The block is visibility=public so P2P may carry it. It contains only
identity + hash + relation. Never Genesis body, members, or documents.
Reward is forced to 0 — this is not a mining event.
"""

from __future__ import annotations

import logging
from typing import Any

from src.artcb.authz.domains import public_commitment

logger = logging.getLogger("artcb.authz.anchor")


PUBLIC_EVENT = "DOMAIN_COMMITMENT"


def commitment_public_symbols(
    *,
    kind: str,
    domain_id: str,
    content_hash: str,
    parent_id: str | None,
    issuer: str,
    issued_at: str,
    event: str = PUBLIC_EVENT,
) -> dict[str, str]:
    row = public_commitment(
        kind=kind,  # type: ignore[arg-type]
        domain_id=domain_id,
        content_hash=content_hash,
        parent_id=parent_id,
        issuer=issuer,
        issued_at=issued_at,
    )
    symbols = {
        "artcb_event": event,
        "kind": str(row["kind"]),
        "domain_id": str(row["domain_id"]),
        "content_hash": str(row["content_hash"]),
        "parent_id": str(row.get("parent_id") or ""),
        "issuer": str(row["issuer"]),
        "issued_at": str(row["issued_at"]),
        "contains_private_data": "false",
        "unique_human_proven": "false",
    }
    forbidden = ("members", "join_code", "genesis_body", "allowed_actions", "document")
    blob = " ".join(symbols.values()).lower()
    for word in forbidden:
        if word in blob and word != "false":
            raise ValueError(f"private_field_in_public_commitment:{word}")
    return symbols


def anchor_public_commitment(chain, *, symbols: dict[str, str]) -> dict[str, Any]:
    """Append a public zero-reward block. Returns a safe summary, never a token."""
    graph_id = f"commit:{symbols['kind']}:{symbols['domain_id']}"
    block = chain.append_block(
        graph_id=graph_id,
        graph_root=symbols["content_hash"],
        pol_score=0.0,
        visibility="public",
        public_symbols=symbols,
        block_reward=0,
        source="authz_commitment",
    )
    logger.info(
        "anchored public commitment kind=%s domain=%s index=%s",
        symbols["kind"],
        symbols["domain_id"],
        getattr(block, "index", None),
    )
    return {
        "anchored": True,
        "block_index": getattr(block, "index", None),
        "block_hash": getattr(block, "hash", None),
        "visibility": "public",
        "block_reward": 0,
        "contains_private_data": False,
        "unique_human_proven": False,
    }


TRANSFER_EVENT = "ORG_CONTROL_TRANSFER"


def transfer_public_symbols(tx) -> dict[str, str]:
    """Public audit of a finalized control transfer. No Genesis, no members."""
    symbols = {
        "artcb_event": TRANSFER_EVENT,
        "subject_type": str(tx.subject_type),
        "subject_id": str(tx.subject_id),
        "domain_id": str(tx.domain_id),
        "reason": str(tx.reason),
        "old_controller": str(tx.old_controller),
        "new_controller": str(tx.new_controller),
        "legal_owner_after": str(tx.legal_owner_after),
        "org_id_unchanged": "true",
        "contains_private_data": "false",
        "unique_human_proven": "false",
    }
    blob = " ".join(symbols.values()).lower()
    for word in ("members", "join_code", "genesis_body", "document"):
        if word in blob:
            raise ValueError(f"private_field_in_public_transfer:{word}")
    return symbols


def anchor_control_transfer(chain, *, tx) -> dict[str, Any]:
    symbols = transfer_public_symbols(tx)
    block = chain.append_block(
        graph_id=f"xfer:{tx.subject_type}:{tx.subject_id}:{tx.tx_id}",
        graph_root=symbols["subject_id"],
        pol_score=0.0,
        visibility="public",
        public_symbols=symbols,
        block_reward=0,
        source="authz_transfer",
    )
    return {
        "anchored": True,
        "artcb_event": TRANSFER_EVENT,
        "block_index": getattr(block, "index", None),
        "block_hash": getattr(block, "hash", None),
        "visibility": "public",
        "block_reward": 0,
        "contains_private_data": False,
        "unique_human_proven": False,
    }
