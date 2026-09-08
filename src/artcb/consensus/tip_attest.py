"""Tip attestation — each node signs height|last_hash|git_sha|node_id.

This is *not* PBFT view-change. It answers: do at least Q=3 honest
nodes currently attest the same tip with a chain-key signature?

Block append remains longest valid public chain. Settlement BFT is 188.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from typing import Any

from src.artcb.consensus.live_bft import n_f_q
from src.artcb.trace.ns import now_wall_ns

TIP_ATTEST_PROTOCOL = "263-tip-attest-q3"


def canonical_message(*, height: int, last_hash: str, git_sha: str, node_id: str) -> str:
    return f"{int(height)}|{(last_hash or '').strip()}|{(git_sha or '').strip()}|{(node_id or '').strip()}"


def producer_key_b64(chain: Any) -> tuple[str, str]:
    ed = str(getattr(chain, "public_key_b64", "") or "")
    pqc_raw = getattr(chain, "_pqc_public_key", None)
    pqc = base64.b64encode(pqc_raw).decode("ascii") if pqc_raw else ""
    return ed, pqc


def sign_message(chain: Any, message: str) -> str:
    return chain._sign_block(message)


def attest_tip(chain: Any, *, git_sha: str, node_id: str) -> dict[str, Any]:
    height = int(chain.height())
    last_hash = str(chain.last_hash() or "")
    message = canonical_message(height=height, last_hash=last_hash, git_sha=git_sha, node_id=node_id)
    signature = sign_message(chain, message)
    ed_b64, pqc_b64 = producer_key_b64(chain)
    return {
        "protocol": TIP_ATTEST_PROTOCOL,
        "node_id": node_id,
        "height": height,
        "last_hash": last_hash,
        "git_sha": git_sha,
        "message": message,
        "signature": signature,
        "producer_ed25519_b64": ed_b64,
        "producer_pqc_b64": pqc_b64,
        "ts_ns": now_wall_ns(),
        "not_pbft_view_change": True,
        "not_block_append_bft": True,
        "scope": "tip_attestation_q3",
    }


def verify_chain_signature(
    *,
    message: str,
    signature: str,
    producer_ed25519_b64: str,
    producer_pqc_b64: str = "",
) -> bool:
    from src.artcb.crypto.hybrid import HybridSignature, is_hybrid_envelope, verify_hybrid_and_or_window
    from src.artcb.crypto.pqc import pqc_available
    from src.artcb.crypto_policy import fallback_still_open

    sig = str(signature or "")
    ed_b64 = str(producer_ed25519_b64 or "")
    if not sig or not ed_b64 or not message:
        return False
    try:
        ed_pk = base64.b64decode(ed_b64, validate=False)
    except Exception:
        return False
    pqc_pk = None
    if producer_pqc_b64:
        try:
            pqc_pk = base64.b64decode(producer_pqc_b64, validate=False)
        except Exception:
            pqc_pk = None
    if is_hybrid_envelope(sig) and not pqc_available():
        if not fallback_still_open():
            return False
        parsed = HybridSignature.parse(sig)
        if parsed is None or not parsed.ed25519_hex:
            return False
        try:
            from nacl.signing import VerifyKey

            VerifyKey(ed_pk).verify(message.encode("utf-8"), bytes.fromhex(parsed.ed25519_hex))
            return True
        except Exception:
            return False
    try:
        return bool(
            verify_hybrid_and_or_window(
                message=message.encode("utf-8"),
                signature_value=sig,
                ed25519_public_key=ed_pk,
                pqc_public_key=pqc_pk,
            )
        )
    except Exception:
        return False


def verify_attest(row: dict[str, Any]) -> bool:
    node_id = str(row.get("node_id") or "")
    message = canonical_message(
        height=int(row.get("height") or 0),
        last_hash=str(row.get("last_hash") or ""),
        git_sha=str(row.get("git_sha") or ""),
        node_id=node_id,
    )
    if str(row.get("message") or "") and str(row.get("message")) != message:
        return False
    from src.artcb.consensus.replica_identity import verify_bound_signature

    ok, _reason = verify_bound_signature(
        replica_id=node_id,
        message=message,
        signature=str(row.get("signature") or ""),
        producer_ed25519_b64=str(row.get("producer_ed25519_b64") or ""),
        producer_pqc_b64=str(row.get("producer_pqc_b64") or ""),
    )
    return ok


def quorum_from_attests(rows: list[dict[str, Any]], *, n: int | None = None) -> dict[str, Any]:
    valid = [r for r in rows if verify_attest(r)]
    groups: dict[tuple[int, str], list[str]] = defaultdict(list)
    for row in valid:
        groups[(int(row.get("height") or 0), str(row.get("last_hash") or ""))].append(
            str(row.get("node_id") or "unknown")
        )
    declared_n = int(n if n is not None else max(len(rows), 4))
    _n, f, q = n_f_q(declared_n)
    best_key = None
    best_nodes: list[str] = []
    for key, nodes in groups.items():
        if len(nodes) > len(best_nodes):
            best_key = key
            best_nodes = nodes
    count = len(best_nodes)
    ok = f is not None and count >= q
    return {
        "ok": ok,
        "protocol": TIP_ATTEST_PROTOCOL,
        "n": declared_n,
        "f": f,
        "q": q,
        "valid_signatures": len(valid),
        "quorum_count": count,
        "height": best_key[0] if best_key else None,
        "last_hash": best_key[1] if best_key else None,
        "node_ids": best_nodes,
        "not_pbft_view_change": True,
        "not_block_append_bft": True,
        "reason": "quorum" if ok else ("n_lt_4_not_bft" if f is None else "no_majority"),
    }
