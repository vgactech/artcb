"""PBFT block finality (Castro-Liskov) on the public append/import path.

N=4 F=1 Q=3. Sequence = block index. Digest = block hash.
PRE-PREPARE → PREPARE → COMMIT → commit certificate → write the same
block on honest replicas. Finalized indices cannot be replaced by
longest-chain import.

R264 view-change (settlement) is the shared view counter. This module
adds the log, P-set, and certificates. Nanosecond traces on every phase.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from src.artcb.consensus.live_bft import n_f_q
from src.artcb.consensus.pbft_view import primary_of
from src.artcb.consensus.tip_attest import producer_key_b64, sign_message, verify_chain_signature
from src.artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS
from src.artcb.trace.ns import emit_pbft, now_mono_ns, now_wall_ns

logger = logging.getLogger("artcb.consensus.pbft_finality")

PBFT_FINALITY_PROTOCOL = "265-pbft-block-finality"
STATE_REL = Path("consensus") / "pbft_finality.json"
MSG_REL = Path("consensus") / "pbft_finality.jsonl"
# First live certified seq (R265 TEST A). Public writes at or after this
# index require a commit certificate. History before it stays longest-chain.
FIRST_LIVE_CERTIFIED_SEQ = 1087


def _iint(row: dict[str, Any], key: str, default: int = -1) -> int:
    if key not in row or row[key] is None or row[key] == "":
        return default
    return int(row[key])


def _n_f_q() -> tuple[int, int, int]:
    n, f, q = n_f_q(4)
    return n, int(f or 1), int(q)


def block_digest(block: dict[str, Any]) -> str:
    return str(block.get("hash") or "").strip()


def pp_message(*, view: int, seq: int, digest: str, replica_id: str) -> str:
    return f"PP|{int(view)}|{int(seq)}|{digest}|{replica_id}"


def prepare_message(*, view: int, seq: int, digest: str, replica_id: str) -> str:
    return f"P|{int(view)}|{int(seq)}|{digest}|{replica_id}"


def commit_message(*, view: int, seq: int, digest: str, replica_id: str) -> str:
    return f"C|{int(view)}|{int(seq)}|{digest}|{replica_id}"


def vc265_message(*, view: int, from_view: int, replica_id: str, pset_digest: str) -> str:
    return f"VC265|{int(view)}|{int(from_view)}|{replica_id}|{pset_digest}"


def pset_digest(prepared: list[dict[str, Any]]) -> str:
    material = json.dumps(prepared, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _sign_row(chain: Any, *, kind: str, message: str, replica_id: str, extra: dict[str, Any]) -> dict[str, Any]:
    ed, pqc = producer_key_b64(chain)
    row = {
        "kind": kind,
        "protocol": PBFT_FINALITY_PROTOCOL,
        "message": message,
        "replica_id": replica_id,
        "signature": sign_message(chain, message),
        "producer_ed25519_b64": ed,
        "producer_pqc_b64": pqc,
        "ts_ns": now_wall_ns(),
        **extra,
    }
    return row


def verify_signed(row: dict[str, Any], expected_message: str) -> bool:
    if str(row.get("message") or "") != expected_message:
        return False
    if str(row.get("replica_id") or "") not in OFFICIAL_COMPUTE_NODE_IDS:
        return False
    if str(row.get("protocol") or "") not in ("", PBFT_FINALITY_PROTOCOL) and row.get("protocol") != PBFT_FINALITY_PROTOCOL:
        return False
    return verify_chain_signature(
        message=expected_message,
        signature=str(row.get("signature") or ""),
        producer_ed25519_b64=str(row.get("producer_ed25519_b64") or ""),
        producer_pqc_b64=str(row.get("producer_pqc_b64") or ""),
    )


def exclusive_public_from(data_dir: Path) -> int:
    """Lowest public seq that must carry a PBFT commit certificate."""
    import os

    env = (os.getenv("ARTCB_PBFT_EXCLUSIVE_FROM") or "").strip()
    if env != "":
        return int(env)
    path = Path(data_dir) / STATE_REL
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict) and parsed.get("exclusive_public_from_seq") is not None:
            return int(parsed["exclusive_public_from_seq"])
    return FIRST_LIVE_CERTIFIED_SEQ


def sign_preprepare(chain: Any, *, view: int, replica_id: str, block: dict[str, Any]) -> dict[str, Any]:
    """Sign a PRE-PREPARE. Does not consult the replica lock (Byzantine primary can sign two)."""
    seq = _iint(block, "index")
    digest = block_digest(block)
    msg = pp_message(view=int(view), seq=seq, digest=digest, replica_id=replica_id)
    return _sign_row(
        chain,
        kind="pre-prepare",
        message=msg,
        replica_id=replica_id,
        extra={"view": int(view), "seq": seq, "digest": digest, "block": block},
    )


def verify_preprepare(row: dict[str, Any]) -> bool:
    view = _iint(row, "view", 0)
    replica = str(row.get("replica_id") or "")
    if replica != primary_of(view):
        return False
    seq = _iint(row, "seq")
    digest = str(row.get("digest") or "")
    msg = pp_message(view=view, seq=seq, digest=digest, replica_id=replica)
    if not verify_signed(row, msg):
        return False
    block = row.get("block") if isinstance(row.get("block"), dict) else {}
    return block_digest(block) == digest and _iint(block, "index") == seq


def verify_prepare(row: dict[str, Any]) -> bool:
    msg = prepare_message(
        view=_iint(row, "view", 0),
        seq=_iint(row, "seq"),
        digest=str(row.get("digest") or ""),
        replica_id=str(row.get("replica_id") or ""),
    )
    return verify_signed(row, msg)


def verify_commit(row: dict[str, Any]) -> bool:
    msg = commit_message(
        view=_iint(row, "view", 0),
        seq=_iint(row, "seq"),
        digest=str(row.get("digest") or ""),
        replica_id=str(row.get("replica_id") or ""),
    )
    return verify_signed(row, msg)


def verify_certificate(cert: dict[str, Any] | None) -> bool:
    if not isinstance(cert, dict):
        return False
    view = _iint(cert, "view")
    seq = _iint(cert, "seq")
    digest = str(cert.get("digest") or "")
    commits = [c for c in (cert.get("commits") or []) if isinstance(c, dict) and verify_commit(c)]
    ids = {str(c.get("replica_id") or "") for c in commits}
    _n, _f, q = _n_f_q()
    if len(ids) < q:
        return False
    for c in commits:
        if _iint(c, "view") != view or _iint(c, "seq") != seq or str(c.get("digest") or "") != digest:
            return False
    return str(cert.get("digest") or "") == digest


class PbftFinalityStore:
    def __init__(self, data_dir: Path, *, replica_id: str, view_store: Any = None) -> None:
        self.data_dir = Path(data_dir)
        self.replica_id = replica_id
        self.view_store = view_store
        self.path = self.data_dir / STATE_REL
        self.msg_path = self.data_dir / MSG_REL
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "protocol": PBFT_FINALITY_PROTOCOL,
                "exclusive_public_from_seq": FIRST_LIVE_CERTIFIED_SEQ,
                "accepted": {},
                "prepared": {},
                "committed": {},
                "certificates": {},
                "seen": [],
            }
        try:
            parsed = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        parsed.setdefault("protocol", PBFT_FINALITY_PROTOCOL)
        parsed.setdefault("exclusive_public_from_seq", FIRST_LIVE_CERTIFIED_SEQ)
        parsed.setdefault("accepted", {})
        parsed.setdefault("prepared", {})
        parsed.setdefault("committed", {})
        parsed.setdefault("certificates", {})
        parsed.setdefault("seen", [])
        return parsed

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _append_msg(self, row: dict[str, Any]) -> None:
        with self.msg_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    def _trace(self, phase: str, *, ok: bool, t0: int, **fields: Any) -> None:
        emit_pbft(
            self.data_dir,
            phase=phase,
            replica_id=self.replica_id,
            ok=ok,
            dur_ns=now_mono_ns() - t0,
            view=self.view,
            **fields,
        )

    @property
    def view(self) -> int:
        if self.view_store is not None:
            return int(getattr(self.view_store, "view", 0) or 0)
        return 0

    def snapshot(self) -> dict[str, Any]:
        n, f, q = _n_f_q()
        return {
            "protocol": PBFT_FINALITY_PROTOCOL,
            "replica_id": self.replica_id,
            "view": self.view,
            "primary": primary_of(self.view),
            "n": n,
            "f": f,
            "q": q,
            "prepared_count": len(self._state.get("prepared") or {}),
            "committed_count": len(self._state.get("committed") or {}),
            "certificate_count": len(self._state.get("certificates") or {}),
            "finality_on_append_path": True,
            "not_longest_chain_after_cert": True,
            "r264_is_baseline": True,
            "exclusive_public_from_seq": exclusive_public_from(self.data_dir),
            "public_append_exclusive_pbft": True,
        }

    def finalized_digest(self, seq: int) -> str | None:
        cert = (self._state.get("certificates") or {}).get(str(int(seq)))
        if isinstance(cert, dict) and verify_certificate(cert):
            return str(cert.get("digest") or "") or None
        return None

    def certificate(self, seq: int) -> dict[str, Any] | None:
        cert = (self._state.get("certificates") or {}).get(str(int(seq)))
        return cert if isinstance(cert, dict) else None

    def prepared_set(self) -> list[dict[str, Any]]:
        out = []
        for key, row in (self._state.get("prepared") or {}).items():
            if isinstance(row, dict) and row.get("digest"):
                out.append({"seq": int(row.get("seq") or key.split(":")[-1]), "digest": row["digest"], "view": int(row.get("view") or 0)})
        return out

    def emit_preprepare(self, chain: Any, *, block: dict[str, Any]) -> dict[str, Any]:
        t0 = now_mono_ns()
        view = self.view
        if self.replica_id != primary_of(view):
            self._trace("preprepare", ok=False, t0=t0, reason="not_primary")
            raise ValueError("not_primary")
        seq = _iint(block, "index")
        digest = block_digest(block)
        if not digest:
            raise ValueError("empty_digest")
        locked = (self._state.get("accepted") or {}).get(f"{view}:{seq}")
        if locked and locked != digest:
            self._trace("preprepare", ok=False, t0=t0, reason="equivocation", seq=seq)
            raise ValueError("equivocation")
        row = sign_preprepare(chain, view=view, replica_id=self.replica_id, block=block)
        if not verify_preprepare(row):
            raise ValueError("preprepare_self_check_failed")
        self._accept(row)
        self._trace("preprepare", ok=True, t0=t0, seq=seq, digest=digest[:16])
        return row

    def accept_preprepare(self, row: dict[str, Any]) -> dict[str, Any]:
        t0 = now_mono_ns()
        if not verify_preprepare(row):
            self._trace("preprepare_recv", ok=False, t0=t0, reason="invalid")
            return {"ok": False, "reason": "invalid_preprepare"}
        view = int(row["view"])
        if view != self.view:
            self._trace("preprepare_recv", ok=False, t0=t0, reason="wrong_view")
            return {"ok": False, "reason": "wrong_view"}
        seq = int(row["seq"])
        digest = str(row["digest"])
        locked = (self._state.get("accepted") or {}).get(f"{view}:{seq}")
        if locked and locked != digest:
            self._trace("preprepare_recv", ok=False, t0=t0, reason="equivocation", seq=seq)
            return {"ok": False, "reason": "equivocation"}
        self._accept(row)
        self._trace("preprepare_recv", ok=True, t0=t0, seq=seq, digest=digest[:16])
        return {"ok": True, "view": view, "seq": seq, "digest": digest}

    def emit_prepare(self, chain: Any, *, view: int, seq: int, digest: str) -> dict[str, Any]:
        t0 = now_mono_ns()
        if int(view) != self.view:
            self._trace("prepare", ok=False, t0=t0, reason="wrong_view")
            raise ValueError("wrong_view")
        accepted = (self._state.get("accepted") or {}).get(f"{int(view)}:{int(seq)}")
        if accepted != digest:
            self._trace("prepare", ok=False, t0=t0, reason="not_accepted")
            raise ValueError("not_accepted")
        msg = prepare_message(view=int(view), seq=int(seq), digest=digest, replica_id=self.replica_id)
        row = _sign_row(chain, kind="prepare", message=msg, replica_id=self.replica_id, extra={"view": int(view), "seq": int(seq), "digest": digest})
        self._store_prepare(row)
        self._trace("prepare", ok=True, t0=t0, seq=seq, digest=digest[:16])
        return row

    def accept_prepare(self, row: dict[str, Any]) -> dict[str, Any]:
        t0 = now_mono_ns()
        if not verify_prepare(row):
            self._trace("prepare_recv", ok=False, t0=t0, reason="invalid")
            return {"ok": False, "reason": "invalid_prepare"}
        if _iint(row, "view") != self.view:
            self._trace("prepare_recv", ok=False, t0=t0, reason="wrong_view")
            return {"ok": False, "reason": "wrong_view"}
        self._store_prepare(row)
        prepared = self._maybe_mark_prepared(int(row["view"]), int(row["seq"]), str(row["digest"]))
        self._trace("prepare_recv", ok=True, t0=t0, seq=int(row["seq"]), prepared=prepared)
        return {"ok": True, "prepared": prepared}

    def emit_commit(self, chain: Any, *, view: int, seq: int, digest: str) -> dict[str, Any]:
        t0 = now_mono_ns()
        key = f"{int(view)}:{int(seq)}"
        prep = (self._state.get("prepared") or {}).get(key) or {}
        if str(prep.get("digest") or "") != digest:
            self._trace("commit", ok=False, t0=t0, reason="not_prepared")
            raise ValueError("not_prepared")
        msg = commit_message(view=int(view), seq=int(seq), digest=digest, replica_id=self.replica_id)
        row = _sign_row(chain, kind="commit", message=msg, replica_id=self.replica_id, extra={"view": int(view), "seq": int(seq), "digest": digest})
        cert = self._store_commit(row)
        self._trace("commit", ok=True, t0=t0, seq=seq, certified=bool(cert))
        return {"commit": row, "certificate": cert}

    def accept_commit(self, row: dict[str, Any]) -> dict[str, Any]:
        t0 = now_mono_ns()
        if not verify_commit(row):
            self._trace("commit_recv", ok=False, t0=t0, reason="invalid")
            return {"ok": False, "reason": "invalid_commit"}
        if _iint(row, "view") != self.view:
            self._trace("commit_recv", ok=False, t0=t0, reason="wrong_view")
            return {"ok": False, "reason": "wrong_view"}
        cert = self._store_commit(row)
        self._trace("commit_recv", ok=True, t0=t0, seq=int(row["seq"]), certified=bool(cert))
        return {"ok": True, "certificate": cert}

    def install_certificate(self, cert: dict[str, Any]) -> dict[str, Any]:
        t0 = now_mono_ns()
        if not verify_certificate(cert):
            self._trace("certificate", ok=False, t0=t0, reason="invalid")
            return {"ok": False, "reason": "invalid_certificate"}
        seq = int(cert["seq"])
        digest = str(cert["digest"])
        held = self.finalized_digest(seq)
        if held and held != digest:
            self._trace("certificate", ok=False, t0=t0, reason="conflict", seq=seq)
            return {"ok": False, "reason": "certificate_conflict"}
        with self._lock:
            self._state.setdefault("certificates", {})[str(seq)] = cert
            self._state.setdefault("committed", {})[f"{int(cert['view'])}:{seq}"] = {"view": int(cert["view"]), "seq": seq, "digest": digest}
            self._save()
            self._append_msg({"kind": "certificate", "seq": seq, "digest": digest, "ts_ns": now_wall_ns()})
        self._trace("certificate", ok=True, t0=t0, seq=seq, digest=digest[:16])
        return {"ok": True, "seq": seq, "digest": digest}

    def emit_view_change_265(self, chain: Any, *, view: int) -> dict[str, Any]:
        t0 = now_mono_ns()
        from_view = self.view
        if int(view) <= from_view:
            raise ValueError("view_not_greater")
        prepared = self.prepared_set()
        digest = pset_digest(prepared)
        msg = vc265_message(view=int(view), from_view=from_view, replica_id=self.replica_id, pset_digest=digest)
        row = _sign_row(
            chain,
            kind="view-change-265",
            message=msg,
            replica_id=self.replica_id,
            extra={"view": int(view), "from_view": from_view, "prepared": prepared, "pset_digest": digest},
        )
        self._append_msg(row)
        self._trace("view_change", ok=True, t0=t0, to_view=int(view), prepared=len(prepared))
        return row

    def verify_view_change_265(self, row: dict[str, Any]) -> bool:
        prepared = row.get("prepared") if isinstance(row.get("prepared"), list) else []
        digest = pset_digest(prepared)
        if str(row.get("pset_digest") or "") != digest:
            return False
        msg = vc265_message(
            view=int(row.get("view") or 0),
            from_view=int(row.get("from_view") or 0),
            replica_id=str(row.get("replica_id") or ""),
            pset_digest=digest,
        )
        return verify_signed(row, msg)

    def select_new_view_value(self, view_changes: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Highest seq prepared in any valid VC. Safety: re-propose that digest."""
        best: dict[str, Any] | None = None
        for vc in view_changes:
            if not self.verify_view_change_265(vc):
                continue
            for item in vc.get("prepared") or []:
                if not isinstance(item, dict):
                    continue
                seq = _iint(item, "seq")
                digest = str(item.get("digest") or "")
                if seq < 0 or not digest:
                    continue
                if best is None or seq > int(best["seq"]):
                    best = {"seq": seq, "digest": digest}
        return best

    def _accept(self, row: dict[str, Any]) -> None:
        view = int(row["view"])
        seq = int(row["seq"])
        digest = str(row["digest"])
        with self._lock:
            self._state.setdefault("accepted", {})[f"{view}:{seq}"] = digest
            seen = list(self._state.get("seen") or [])
            sig = str(row.get("signature") or "")[:80]
            if sig and sig not in seen:
                seen.append(sig)
                self._state["seen"] = seen[-400:]
            self._save()
            self._append_msg(row)

    def _store_prepare(self, row: dict[str, Any]) -> None:
        with self._lock:
            key = f"prepare:{row.get('view')}:{row.get('seq')}:{row.get('replica_id')}"
            self._state.setdefault("prepare_msgs", {})[key] = row
            self._save()
            self._append_msg(row)
        self._maybe_mark_prepared(int(row["view"]), int(row["seq"]), str(row["digest"]))

    def _maybe_mark_prepared(self, view: int, seq: int, digest: str) -> bool:
        accepted = (self._state.get("accepted") or {}).get(f"{view}:{seq}")
        if accepted != digest:
            return False
        msgs = [m for m in (self._state.get("prepare_msgs") or {}).values() if isinstance(m, dict)]
        matching = [
            m
            for m in msgs
            if _iint(m, "view") == view and _iint(m, "seq") == seq and str(m.get("digest") or "") == digest and verify_prepare(m)
        ]
        ids = {str(m.get("replica_id") or "") for m in matching}
        _n, _f, q = _n_f_q()
        if len(ids) < q:
            return False
        with self._lock:
            self._state.setdefault("prepared", {})[f"{view}:{seq}"] = {"view": view, "seq": seq, "digest": digest, "q": len(ids)}
            self._save()
        return True

    def _store_commit(self, row: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            key = f"commit:{row.get('view')}:{row.get('seq')}:{row.get('replica_id')}"
            self._state.setdefault("commit_msgs", {})[key] = row
            self._save()
            self._append_msg(row)
        view = int(row["view"])
        seq = int(row["seq"])
        digest = str(row["digest"])
        held = self.finalized_digest(seq)
        if held and held != digest:
            return None
        prep = (self._state.get("prepared") or {}).get(f"{view}:{seq}") or {}
        if str(prep.get("digest") or "") != digest:
            return None
        msgs = [m for m in (self._state.get("commit_msgs") or {}).values() if isinstance(m, dict)]
        matching = [
            m
            for m in msgs
            if _iint(m, "view") == view and _iint(m, "seq") == seq and str(m.get("digest") or "") == digest and verify_commit(m)
        ]
        ids = {str(m.get("replica_id") or "") for m in matching}
        _n, _f, q = _n_f_q()
        if len(ids) < q:
            return None
        cert = {
            "protocol": PBFT_FINALITY_PROTOCOL,
            "kind": "commit-certificate",
            "view": view,
            "seq": seq,
            "digest": digest,
            "q": q,
            "replica_ids": sorted(ids),
            "commits": matching,
            "ts_ns": now_wall_ns(),
        }
        with self._lock:
            self._state.setdefault("certificates", {})[str(seq)] = cert
            self._state.setdefault("committed", {})[f"{view}:{seq}"] = {"view": view, "seq": seq, "digest": digest}
            self._save()
        return cert


def finalized_digest_for(data_dir: Path, seq: int) -> str | None:
    path = Path(data_dir) / STATE_REL
    if not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cert = (parsed.get("certificates") or {}).get(str(int(seq)))
    if isinstance(cert, dict) and verify_certificate(cert):
        return str(cert.get("digest") or "") or None
    return None
