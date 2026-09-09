# ~~2026-09-08 original module contract — conservé 2026-09-10T23:12:00Z~~
# """PBFT view-change for official replicas (default N=4, F=1, Q=3).
# The replica set is OFFICIAL_COMPUTE_NODE_IDS (exactly 4 cloud VMs)."""
# Barré 2026-09-09T21:55:00Z : membership = official_pbft_replica_ids() (N adaptatif).
"""PBFT view-change for official replicas (default N=4, F=1, Q=3).

Castro-Liskov: VIEW-CHANGE from 2F+1 replicas elects a new primary via
NEW-VIEW. The replica set is official_pbft_replica_ids() (4 cloud VMs,
or 5 after Mac live enrollment). OFFICIAL_COMPUTE_NODE_IDS stays the
follow-main / public-IPv4 set.

This gates settlement prepare/commit (188) on the current view.
Block append remains longest valid public chain. Processes stay up:
view-change is triggered by unreachability of the primary, not by kill.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from src.artcb.consensus.tip_attest import producer_key_b64, sign_message
from src.artcb.node_registry import official_pbft_n_f_q, official_pbft_replica_ids, official_replica_id
from src.artcb.trace.ns import now_wall_ns

logger = logging.getLogger("artcb.consensus.pbft_view")

PBFT_VIEW_PROTOCOL = "264-pbft-view-change"
VIEW_REL = Path("consensus") / "pbft_view.json"
VC_REL = Path("consensus") / "pbft_view_change.jsonl"


def primary_of(view: int) -> str:
    ids = official_pbft_replica_ids()
    return ids[int(view) % len(ids)]


def vc_message(*, view: int, from_view: int, height: int, last_hash: str, replica_id: str, reason: str) -> str:
    return (
        f"VC|{int(view)}|{int(from_view)}|{int(height)}|"
        f"{(last_hash or '').strip()}|{(replica_id or '').strip()}|{(reason or '').strip()}"
    )


def nv_message(*, view: int, primary: str, vc_digest: str, replica_id: str) -> str:
    return f"NV|{int(view)}|{(primary or '').strip()}|{(vc_digest or '').strip()}|{(replica_id or '').strip()}"


def vc_digest(rows: list[dict[str, Any]]) -> str:
    import hashlib

    material = "|".join(sorted(str(r.get("message") or "") for r in rows))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def verify_view_change(row: dict[str, Any]) -> bool:
    message = vc_message(
        view=int(row.get("view") or 0),
        from_view=int(row.get("from_view") or 0),
        height=int(row.get("height") or 0),
        last_hash=str(row.get("last_hash") or ""),
        replica_id=str(row.get("replica_id") or ""),
        reason=str(row.get("reason") or ""),
    )
    if str(row.get("message") or "") != message:
        return False
    if str(row.get("replica_id") or "") not in official_pbft_replica_ids():
        return False
    from src.artcb.consensus.replica_identity import verify_bound_signature

    ok, _reason = verify_bound_signature(
        replica_id=str(row.get("replica_id") or ""),
        message=message,
        signature=str(row.get("signature") or ""),
        producer_ed25519_b64=str(row.get("producer_ed25519_b64") or ""),
        producer_pqc_b64=str(row.get("producer_pqc_b64") or ""),
    )
    return ok


def verify_new_view(row: dict[str, Any], view_changes: list[dict[str, Any]]) -> bool:
    view = int(row.get("view") or 0)
    primary = str(row.get("primary") or "")
    if primary != primary_of(view):
        return False
    if str(row.get("replica_id") or "") != primary:
        return False
    valid = [vc for vc in view_changes if verify_view_change(vc) and int(vc.get("view") or 0) == view]
    ids = {str(vc.get("replica_id") or "") for vc in valid}
    _n, f, q = official_pbft_n_f_q()
    if f is None or len(ids) < q:
        return False
    digest = vc_digest(valid)
    if str(row.get("vc_digest") or "") != digest:
        return False
    message = nv_message(view=view, primary=primary, vc_digest=digest, replica_id=primary)
    if str(row.get("message") or "") != message:
        return False
    from src.artcb.consensus.replica_identity import verify_bound_signature

    ok, _reason = verify_bound_signature(
        replica_id=primary,
        message=message,
        signature=str(row.get("signature") or ""),
        producer_ed25519_b64=str(row.get("producer_ed25519_b64") or ""),
        producer_pqc_b64=str(row.get("producer_pqc_b64") or ""),
    )
    return ok


class PbftViewStore:
    def __init__(self, data_dir: Path, *, replica_id: str = "") -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / VIEW_REL
        self.vc_path = self.data_dir / VC_REL
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from src.artcb.consensus.replica_identity import official_consensus_node_id

            claimed = official_consensus_node_id()
        except Exception:
            claimed = official_replica_id()
        self.replica_id = replica_id or claimed or official_replica_id() or "unknown"
        self._lock = threading.Lock()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "protocol": PBFT_VIEW_PROTOCOL,
                "view": 0,
                "primary": primary_of(0),
                "new_view": None,
            }
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        view = int(parsed.get("view") or 0)
        return {
            "protocol": PBFT_VIEW_PROTOCOL,
            "view": view,
            "primary": str(parsed.get("primary") or primary_of(view)),
            "new_view": parsed.get("new_view"),
        }

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @property
    def view(self) -> int:
        return int(self._state.get("view") or 0)

    @property
    def primary(self) -> str:
        return str(self._state.get("primary") or primary_of(self.view))

    def snapshot(self) -> dict[str, Any]:
        n, f, q = official_pbft_n_f_q()
        return {
            "protocol": PBFT_VIEW_PROTOCOL,
            "replica_id": self.replica_id,
            "view": self.view,
            "primary": self.primary,
            "n": n,
            "f": f,
            "q": q,
            "replicas": list(official_pbft_replica_ids()),
            "processes_stay_up": True,
            "scope": "pbft_view_change_settlement",
            "not_block_append_bft": True,
        }

    def emit_view_change(self, chain: Any, *, view: int, height: int, last_hash: str, reason: str) -> dict[str, Any]:
        replica = self.replica_id
        if replica not in official_pbft_replica_ids():
            replica = official_replica_id() or replica
            self.replica_id = replica
        from_view = self.view
        if int(view) <= from_view:
            raise ValueError("view_not_greater")
        message = vc_message(
            view=int(view),
            from_view=from_view,
            height=int(height),
            last_hash=str(last_hash or ""),
            replica_id=replica,
            reason=reason or "primary_unreachable",
        )
        ed, pqc = producer_key_b64(chain)
        row = {
            "kind": "view-change",
            "protocol": PBFT_VIEW_PROTOCOL,
            "view": int(view),
            "from_view": from_view,
            "height": int(height),
            "last_hash": str(last_hash or ""),
            "replica_id": replica,
            "reason": reason or "primary_unreachable",
            "message": message,
            "signature": sign_message(chain, message),
            "producer_ed25519_b64": ed,
            "producer_pqc_b64": pqc,
            "ts_ns": now_wall_ns(),
        }
        self._append_vc(row)
        try:
            from src.artcb.trace.ns import emit

            emit(
                self.data_dir,
                {
                    "kind": "pbft_view_change_264",
                    "phase": "view-change",
                    "view": int(view),
                    "replica_id": replica,
                    "ok": True,
                    "ts_ns": row["ts_ns"],
                },
            )
        except Exception:
            pass
        return row

    def accept_view_change(self, row: dict[str, Any]) -> dict[str, Any]:
        if not verify_view_change(row):
            return {"ok": False, "reason": "invalid_view_change"}
        if int(row.get("view") or 0) <= self.view:
            return {"ok": False, "reason": "stale_view"}
        self._append_vc(row)
        return {"ok": True, "stored": True, "view": int(row["view"]), "replica_id": row.get("replica_id")}

    def view_changes(self, view: int) -> list[dict[str, Any]]:
        if not self.vc_path.is_file():
            return []
        out: dict[str, dict[str, Any]] = {}
        for line in self.vc_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            if int(parsed.get("view") or -1) != int(view):
                continue
            if not verify_view_change(parsed):
                continue
            rid = str(parsed.get("replica_id") or "")
            out[rid] = parsed
        return list(out.values())

    def quorum_for(self, view: int) -> dict[str, Any]:
        rows = self.view_changes(view)
        ids = [str(r.get("replica_id") or "") for r in rows]
        _n, f, q = official_pbft_n_f_q()
        return {
            "ok": f is not None and len(ids) >= q,
            "view": int(view),
            "q": q,
            "count": len(ids),
            "replica_ids": ids,
            "view_changes": rows,
            "vc_digest": vc_digest(rows) if rows else "",
            "protocol": PBFT_VIEW_PROTOCOL,
        }

    def emit_new_view(self, chain: Any, *, view: int, view_changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if self.replica_id not in official_pbft_replica_ids():
            self.replica_id = official_replica_id() or self.replica_id
        rows = view_changes if view_changes is not None else self.view_changes(view)
        valid = [r for r in rows if verify_view_change(r) and int(r.get("view") or 0) == int(view)]
        ids = {str(r.get("replica_id") or "") for r in valid}
        _n, f, q = official_pbft_n_f_q()
        if f is None or len(ids) < q:
            raise ValueError("no_view_change_quorum")
        primary = primary_of(int(view))
        if self.replica_id != primary:
            raise ValueError("not_new_primary")
        digest = vc_digest(valid)
        message = nv_message(view=int(view), primary=primary, vc_digest=digest, replica_id=primary)
        ed, pqc = producer_key_b64(chain)
        nv = {
            "kind": "new-view",
            "protocol": PBFT_VIEW_PROTOCOL,
            "view": int(view),
            "primary": primary,
            "replica_id": primary,
            "vc_digest": digest,
            "message": message,
            "signature": sign_message(chain, message),
            "producer_ed25519_b64": ed,
            "producer_pqc_b64": pqc,
            "ts_ns": now_wall_ns(),
        }
        if not verify_new_view(nv, valid):
            raise ValueError("new_view_self_check_failed")
        self.install_new_view(nv, valid)
        return {"new_view": nv, "view_changes": valid, "ok": True}

    def install_new_view(self, nv: dict[str, Any], view_changes: list[dict[str, Any]]) -> dict[str, Any]:
        if not verify_new_view(nv, view_changes):
            return {"ok": False, "reason": "invalid_new_view"}
        view = int(nv["view"])
        if view <= self.view:
            return {"ok": False, "reason": "stale_new_view", "view": self.view}
        with self._lock:
            self._state = {
                "protocol": PBFT_VIEW_PROTOCOL,
                "view": view,
                "primary": primary_of(view),
                "new_view": {
                    "view": view,
                    "primary": primary_of(view),
                    "vc_digest": nv.get("vc_digest"),
                    "replica_ids": [str(r.get("replica_id") or "") for r in view_changes],
                },
            }
            self._save()
        return {"ok": True, "view": view, "primary": primary_of(view)}

    def _append_vc(self, row: dict[str, Any]) -> None:
        with self._lock:
            self.vc_path.parent.mkdir(parents=True, exist_ok=True)
            with self.vc_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
