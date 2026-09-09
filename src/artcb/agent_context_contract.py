"""Context Contract: what an agent received — not private thinking.

R296 honesty + R297 Mac replica membership.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.artcb.agent_runtime import PROTOCOL_VERSION
from src.artcb.node_registry import (
    MAC_NODE_ID,
    NODES,
    official_pbft_n_f_q,
    official_pbft_replica_ids,
    official_replica_id,
    mac_has_registered_replica_key,
)
from src.artcb.release import release_identity

CONTRACT_VERSION = "297.1"
SNIPPET_MEMO_LIMIT = 5
SNIPPET_MEMO_CHARS = 80


def _sha256_json(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _memo_rows(chain: Any, *, limit: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        blocks = list(reversed(chain.list_blocks()))
    except Exception:
        return rows
    for b in blocks:
        if not isinstance(b, dict):
            continue
        ps = b.get("public_symbols") or {}
        src = str(ps.get("learning_source") or "")
        gid = str(b.get("graph_id") or "")
        if not src.startswith("ai:") and not gid.startswith("ai_memo_") and not gid.startswith("ai_think_"):
            continue
        rows.append(
            {
                "index": b.get("index"),
                "hash_prefix": str(b.get("hash") or "")[:16],
                "type": ps.get("memo_type") or "",
                "agent_id": ps.get("agent_id") or "",
                "session_id": ps.get("session_id") or "",
                "parent": ps.get("parent_block_index"),
                "visibility": b.get("visibility") or ps.get("visibility") or "",
            }
        )
        if len(rows) >= limit:
            break
    return rows


def classify_decision_lifecycle(_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """No supersedes/revoked fields exist on memos yet. Do not invent them."""
    return {
        "implemented": False,
        "active_decisions": [r for r in _rows if r.get("type") == "decision"][:8],
        "revoked_decisions": [],
        "note": "memo_type=decision has no supersedes/revoked/effective_until. Last-N is not a lifecycle.",
    }


def build_context_contract(
    *,
    chain: Any | None = None,
    key_record: dict[str, Any] | None = None,
    parent_agent_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    rec = key_record or {}
    ident = release_identity()
    height = None
    tip = None
    if chain is not None:
        try:
            height = chain.height() if hasattr(chain, "height") else len(chain.list_blocks())
        except Exception:
            height = None
        try:
            tip = chain.last_hash() if hasattr(chain, "last_hash") else None
        except Exception:
            tip = None
    rows = _memo_rows(chain, limit=200) if chain is not None else []
    bugs = [r for r in rows if r.get("type") == "bug"]
    fixed_parents = {r.get("parent") for r in rows if r.get("type") == "fix" and r.get("parent") is not None}
    open_bugs = [r for r in bugs if r.get("index") not in fixed_parents][:8]
    life = classify_decision_lifecycle(rows)
    n, f, q = official_pbft_n_f_q()
    replicas = list(official_pbft_replica_ids())
    local_id = official_replica_id() or None
    mac = NODES[MAC_NODE_ID]
    spec = NODES.get(local_id) if local_id else None
    if spec is not None and spec.pbft_replica:
        role = "pbft_replica"
    elif local_id == MAC_NODE_ID:
        role = "pbft_replica"
    else:
        role = "unbound_agent"
    body = {
        "version": CONTRACT_VERSION,
        "protocol": PROTOCOL_VERSION,
        "project": "artcb",
        "network": "live",
        "chain_height": height,
        "chain_tip": tip,
        "code_sha": ident.get("git_sha"),
        "code_branch": ident.get("git_branch"),
        "release_integrity": ident.get("release_integrity"),
        "agent_id": rec.get("agent_id") or rec.get("label") or "agent_anonymous",
        "provider": (spec.provider if spec is not None else rec.get("provider") or rec.get("kind") or None),
        "owner_address": rec.get("address") or rec.get("owner_address"),
        "parent_agent_id": parent_agent_id,
        "task_id": task_id,
        "node_id": local_id,
        "role": role,
        "pbft": {
            "replicas": replicas,
            "n": n,
            "f": f,
            "quorum": q,
            "mac_node_id": MAC_NODE_ID,
            "mac_pbft_replica_role": bool(mac.pbft_replica),
            "mac_in_membership": MAC_NODE_ID in replicas,
            "mac_registered_key": mac_has_registered_replica_key(),
            "mac_follow_main": bool(mac.follow_main),
            "mac_tpm_required": bool(mac.tpm_required),
            "tunnel_is_not_role": True,
        },
        "scope": {
            "path_classifier": "src/artcb/memory/repo_scope.py",
            "public": True,
            "organization": "classified_not_acl",
            "groups": "classified_not_acl",
            "private": "classified_not_resolved",
            "acl_resolved": False,
            "note": "classify_path ≠ PRIVATE-of-whom. Multi-tenant ACL NOT_PROVEN.",
        },
        "active_decisions": life["active_decisions"],
        "revoked_decisions": life["revoked_decisions"],
        "decision_lifecycle": life["note"],
        "open_bugs": open_bugs,
        "validated_facts": [],
        "not_proven": [
            "context_inheritance_parent_child",
            "cross_provider_equivalent_contract",
            "decision_revoke_supersede",
            "scope_acl_resolution",
            "agent_used_received_context",
            "mac_live_pbft_participation",
            "mac_crypto_node_identity",
            "thinking_recorded_on_artcb",
        ],
        "constraints": [
            "CERTIFIED_100=false unless measured",
            "Cursor_is_not_the_node",
            "HTTPS_is_not_P2P",
            "thinking_visible_is_not_thinking_recorded",
            "do_not_merge_PR84_as_certification",
            "N04_FAIL_is_independent_of_mac",
            "new_pbft_replica_grows_n_via_node_spec",
        ],
        "snippet_is_not_contract": True,
        "snippet_limits": {"memos": SNIPPET_MEMO_LIMIT, "chars_per_memo": SNIPPET_MEMO_CHARS},
        "includes_thinking": False,
        "includes_system_prompt": False,
        "certified_100": False,
    }
    hashed = {k: v for k, v in body.items()}
    body["context_hash"] = _sha256_json(hashed)
    return body
