# ~~2026-09-08 original — conservé 2026-09-10T23:12:00Z~~
# N, F, Q = 4, 1, 3  # hardcoded from OFFICIAL_COMPUTE_NODE_IDS
# def _n_f_q() -> tuple[int, int, int]:
#     return 4, 1, 3
# Barré 2026-09-09T21:55:00Z : N/f/Q = official_pbft_n_f_q().
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

from src.artcb.consensus.pbft_view import primary_of
from src.artcb.consensus.tip_attest import producer_key_b64, sign_message
from src.artcb.node_registry import official_pbft_n_f_q, official_pbft_replica_ids
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
    n, f, q = official_pbft_n_f_q()
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


def verify_signed_detailed(row: dict[str, Any], expected_message: str) -> tuple[bool, str]:
    if str(row.get("message") or "") != expected_message:
        return False, "message_mismatch"
    if str(row.get("replica_id") or "") not in official_pbft_replica_ids():
        return False, "unknown_replica_id"
    if str(row.get("protocol") or "") not in ("", PBFT_FINALITY_PROTOCOL) and row.get("protocol") != PBFT_FINALITY_PROTOCOL:
        return False, "protocol_mismatch"
    from src.artcb.consensus.replica_identity import verify_bound_signature

    return verify_bound_signature(
        replica_id=str(row.get("replica_id") or ""),
        message=expected_message,
        signature=str(row.get("signature") or ""),
        producer_ed25519_b64=str(row.get("producer_ed25519_b64") or ""),
        producer_pqc_b64=str(row.get("producer_pqc_b64") or ""),
    )


def verify_signed(row: dict[str, Any], expected_message: str) -> bool:
    ok, _reason = verify_signed_detailed(row, expected_message)
    return ok


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


def verify_prepared_certificate(item: dict[str, Any] | None) -> bool:
    """Strong P-set entry: signed PRE-PREPARE + Q unique signed PREPAREs."""
    if not isinstance(item, dict):
        return False
    view = _iint(item, "view")
    seq = _iint(item, "seq")
    digest = str(item.get("digest") or "")
    if seq < 0 or not digest:
        return False
    pp = item.get("preprepare") if isinstance(item.get("preprepare"), dict) else None
    if pp is None or not verify_preprepare(pp):
        return False
    if _iint(pp, "view") != view or _iint(pp, "seq") != seq or str(pp.get("digest") or "") != digest:
        return False
    prepares = [p for p in (item.get("prepares") or []) if isinstance(p, dict) and verify_prepare(p)]
    ids: set[str] = set()
    for p in prepares:
        if _iint(p, "view") != view or _iint(p, "seq") != seq or str(p.get("digest") or "") != digest:
            return False
        rid = str(p.get("replica_id") or "")
        if not rid or rid in ids:
            continue
        ids.add(rid)
    _n, _f, q = _n_f_q()
    return len(ids) >= q


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
        # P14: never surface unverified proofs after disk corruption / truncation.
        prepared = parsed.get("prepared") if isinstance(parsed.get("prepared"), dict) else {}
        parsed["prepared"] = {
            key: row
            for key, row in prepared.items()
            if isinstance(row, dict) and verify_prepared_certificate(row)
        }
        certs = parsed.get("certificates") if isinstance(parsed.get("certificates"), dict) else {}
        parsed["certificates"] = {
            key: row for key, row in certs.items() if isinstance(row, dict) and verify_certificate(row)
        }
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
            if not isinstance(row, dict) or not row.get("digest"):
                continue
            item = dict(row)
            item.setdefault("seq", int(row.get("seq") or key.split(":")[-1]))
            item.setdefault("view", int(row.get("view") or 0))
            out.append(item)
        return out

    def _uncommitted_prepared_digest(self, seq: int) -> str | None:
        """Authoritative prepared digest for seq until a commit certificate exists."""
        if self.finalized_digest(seq):
            return None
        digests: set[str] = set()
        for row in (self._state.get("prepared") or {}).values():
            if not isinstance(row, dict):
                continue
            if _iint(row, "seq") != int(seq):
                continue
            digest = str(row.get("digest") or "")
            if digest:
                digests.add(digest)
        if len(digests) == 1:
            return next(iter(digests))
        return None

    def _must_digest(self, seq: int) -> str | None:
        constraint = self._state.get("must_repropose") if isinstance(self._state.get("must_repropose"), dict) else {}
        if constraint and _iint(constraint, "seq") == int(seq):
            digest = str(constraint.get("digest") or "")
            if digest:
                return digest
        return self._uncommitted_prepared_digest(seq)

    def remember_view_change_265(self, row: dict[str, Any]) -> bool:
        if not self.verify_view_change_265(row):
            return False
        with self._lock:
            bucket = list(self._state.get("view_changes_265") or [])
            bucket.append(row)
            self._state["view_changes_265"] = bucket[-32:]
            self._save()
        return True

    def enter_view(self, new_view: int, view_changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """NEW-VIEW: drop unprepared PRE-PREPARE locks from older views; bind prepared X.

        Same-view distinct digest remains equivocation. This only releases
        *unprepared* accepted[] entries whose view is strictly less than new_view.
        """
        t0 = now_mono_ns()
        new_view = int(new_view)
        dropped: list[str] = []
        with self._lock:
            accepted = dict(self._state.get("accepted") or {})
            accepted_pp = dict(self._state.get("accepted_pp") or {})
            for key in list(accepted.keys()):
                try:
                    old_view = int(str(key).split(":")[0])
                except (TypeError, ValueError):
                    continue
                if old_view >= new_view:
                    continue
                accepted.pop(key, None)
                accepted_pp.pop(key, None)
                dropped.append(key)
            self._state["accepted"] = accepted
            self._state["accepted_pp"] = accepted_pp
            self._state["view_entered"] = new_view
            self._save()
        vcs = [vc for vc in (view_changes or []) if isinstance(vc, dict)]
        if not vcs:
            vcs = [vc for vc in (self._state.get("view_changes_265") or []) if isinstance(vc, dict)]
        analysis = self.analyze_new_view_certificate(vcs) if vcs else None
        if analysis is not None and analysis.get("claimed_prepared") and not analysis.get("reconstructable"):
            self._trace("enter_view", ok=False, t0=t0, reason="state_incomplete")
            return {
                "ok": False,
                "reason": "state_incomplete",
                "view": new_view,
                "dropped": dropped,
                "new_view_certificate": analysis,
            }
        if analysis is not None and analysis.get("claimed_prepared") and not analysis.get("quorum_ok"):
            self._trace("enter_view", ok=False, t0=t0, reason="state_incomplete")
            return {
                "ok": False,
                "reason": "state_incomplete",
                "view": new_view,
                "dropped": dropped,
                "new_view_certificate": analysis,
            }
        chosen = analysis.get("selected") if analysis and analysis.get("quorum_ok") else None
        if chosen is None and (analysis is None or not analysis.get("claimed_prepared")):
            pending = [row for row in self.prepared_set() if self.finalized_digest(int(row["seq"])) is None]
            if pending:
                chosen = max(pending, key=lambda row: int(row["seq"]))
        bound = self.bind_prepared_constraint(chosen) if chosen else {"ok": False, "reason": "no_prepared"}
        self._trace("enter_view", ok=True, t0=t0, dropped=len(dropped), bound=bool(bound.get("ok")))
        return {
            "ok": True,
            "view": new_view,
            "dropped": dropped,
            "bound": bound,
            "new_view_certificate": analysis,
        }

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
        required = self._must_digest(seq)
        if required and required != digest:
            self._trace("preprepare", ok=False, t0=t0, reason="must_repropose_prepared", seq=seq)
            raise ValueError("must_repropose_prepared")
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
            view = _iint(row, "view", 0)
            seq = _iint(row, "seq")
            digest = str(row.get("digest") or "")
            replica = str(row.get("replica_id") or "")
            msg = pp_message(view=view, seq=seq, digest=digest, replica_id=replica)
            _ok, reason = verify_signed_detailed(row, msg)
            from src.artcb.consensus.replica_identity import BINDING_REASONS

            if not _ok and reason in BINDING_REASONS:
                self._trace("preprepare_recv", ok=False, t0=t0, reason=reason)
                return {"ok": False, "reason": reason}
            self._trace("preprepare_recv", ok=False, t0=t0, reason="invalid")
            return {"ok": False, "reason": "invalid_preprepare"}
        view = int(row["view"])
        if view != self.view:
            self._trace("preprepare_recv", ok=False, t0=t0, reason="wrong_view")
            return {"ok": False, "reason": "wrong_view"}
        seq = int(row["seq"])
        digest = str(row["digest"])
        required = self._must_digest(seq)
        if required and required != digest:
            self._trace("preprepare_recv", ok=False, t0=t0, reason="must_repropose_prepared", seq=seq)
            return {"ok": False, "reason": "must_repropose_prepared"}
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
            msg = prepare_message(
                view=_iint(row, "view", 0),
                seq=_iint(row, "seq"),
                digest=str(row.get("digest") or ""),
                replica_id=str(row.get("replica_id") or ""),
            )
            _ok, reason = verify_signed_detailed(row, msg)
            from src.artcb.consensus.replica_identity import BINDING_REASONS

            if not _ok and reason in BINDING_REASONS:
                self._trace("prepare_recv", ok=False, t0=t0, reason=reason)
                return {"ok": False, "reason": reason}
            self._trace("prepare_recv", ok=False, t0=t0, reason="invalid")
            return {"ok": False, "reason": "invalid_prepare"}
        if _iint(row, "view") != self.view:
            self._trace("prepare_recv", ok=False, t0=t0, reason="wrong_view")
            return {"ok": False, "reason": "wrong_view"}
        view = _iint(row, "view")
        seq = _iint(row, "seq")
        digest = str(row.get("digest") or "")
        accepted = (self._state.get("accepted") or {}).get(f"{view}:{seq}")
        if accepted != digest:
            self._trace("prepare_recv", ok=False, t0=t0, reason="not_accepted", seq=seq)
            return {"ok": False, "reason": "not_accepted"}
        self._store_prepare(row)
        prepared = self._maybe_mark_prepared(view, seq, digest)
        self._trace("prepare_recv", ok=True, t0=t0, seq=seq, prepared=prepared)
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
        view = _iint(row, "view")
        seq = _iint(row, "seq")
        digest = str(row.get("digest") or "")
        prep = (self._state.get("prepared") or {}).get(f"{view}:{seq}") or {}
        if str(prep.get("digest") or "") != digest:
            self._trace("commit_recv", ok=False, t0=t0, reason="not_prepared", seq=seq)
            return {"ok": False, "reason": "not_prepared"}
        cert = self._store_commit(row)
        self._trace("commit_recv", ok=True, t0=t0, seq=seq, certified=bool(cert))
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
        constraint = self._state.get("must_repropose") if isinstance(self._state.get("must_repropose"), dict) else {}
        if constraint and _iint(constraint, "seq") == seq:
            with self._lock:
                self._state.pop("must_repropose", None)
                self._save()
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
        self.remember_view_change_265(row)
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

    def analyze_new_view_certificate(self, view_changes: list[dict[str, Any]]) -> dict[str, Any]:
        """Bind Q VIEW-CHANGE to the prepared actually carried by that quorum.

        A cryptographically valid prepared certificate in a single VIEW-CHANGE
        is not enough to select a NEW-VIEW value. The selected prepared must
        come from a quorum (≥ Q unique replicas) of verified VIEW-CHANGE
        messages, and must be the highest seq with a unique digest among
        those messages.
        """
        valid: list[dict[str, Any]] = []
        ids: list[str] = []
        seen: set[str] = set()
        claimed = False
        reconstructable = False
        for vc in view_changes:
            if not self.verify_view_change_265(vc):
                prepared = vc.get("prepared") if isinstance(vc.get("prepared"), list) else []
                if prepared:
                    claimed = True
                continue
            rid = str(vc.get("replica_id") or "")
            if rid and rid not in seen:
                seen.add(rid)
                ids.append(rid)
                valid.append(vc)
            prepared = vc.get("prepared") if isinstance(vc.get("prepared"), list) else []
            if prepared:
                claimed = True
                if any(verify_prepared_certificate(item) for item in prepared if isinstance(item, dict)):
                    reconstructable = True
        _n, _f, q = _n_f_q()
        quorum_ok = len(ids) >= q
        selected = None
        if quorum_ok:
            by_seq: dict[int, dict[str, dict[str, Any]]] = {}
            for vc in valid:
                for item in vc.get("prepared") or []:
                    if not verify_prepared_certificate(item):
                        continue
                    seq = _iint(item, "seq")
                    digest = str(item.get("digest") or "")
                    by_seq.setdefault(seq, {})[digest] = item
            consistent = []
            for _seq, digests in by_seq.items():
                if len(digests) != 1:
                    continue
                consistent.append(next(iter(digests.values())))
            if consistent:
                selected = max(consistent, key=lambda row: int(row["seq"]))
        view = None
        if valid:
            view = int(valid[0].get("view") or 0)
        reason = "ok"
        if claimed and not reconstructable:
            reason = "state_incomplete"
        elif claimed and not quorum_ok:
            reason = "prepared_without_vc_quorum"
        elif quorum_ok and selected is None:
            reason = "no_prepared"
        return {
            "kind": "NEW_VIEW_CERTIFICATE",
            "view": view,
            "primary": primary_of(int(view)) if view is not None else None,
            "quorum_view_changes": len(ids),
            "q": q,
            "quorum_ok": quorum_ok,
            "replica_ids": ids,
            "claimed_prepared": claimed,
            "reconstructable": reconstructable,
            "selected": selected,
            "reason": reason,
        }

    def select_new_view_value(self, view_changes: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Highest seq whose prepared is carried by a VIEW-CHANGE quorum.

        A single valid prepared certificate is not selectable without Q
        verified VIEW-CHANGE messages from distinct replicas.
        """
        analysis = self.analyze_new_view_certificate(view_changes)
        chosen = analysis.get("selected")
        return chosen if isinstance(chosen, dict) else None

    def bind_prepared_constraint(self, chosen: dict[str, Any] | None) -> dict[str, Any]:
        if not verify_prepared_certificate(chosen):
            return {"ok": False, "reason": "invalid_prepared_certificate"}
        assert chosen is not None
        seq = int(chosen["seq"])
        digest = str(chosen["digest"])
        block = ((chosen.get("preprepare") or {}) if isinstance(chosen.get("preprepare"), dict) else {}).get("block")
        with self._lock:
            self._state["must_repropose"] = {"seq": seq, "digest": digest, "block": block if isinstance(block, dict) else None}
            self._save()
        return {"ok": True, "seq": seq, "digest": digest, "has_block": isinstance(block, dict)}

    def _accept(self, row: dict[str, Any]) -> None:
        view = int(row["view"])
        seq = int(row["seq"])
        digest = str(row["digest"])
        with self._lock:
            self._state.setdefault("accepted", {})[f"{view}:{seq}"] = digest
            if row.get("kind") == "pre-prepare" or row.get("block"):
                self._state.setdefault("accepted_pp", {})[f"{view}:{seq}"] = row
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
        unique: dict[str, dict[str, Any]] = {}
        for m in matching:
            rid = str(m.get("replica_id") or "")
            if rid and rid not in unique:
                unique[rid] = m
        pp = (self._state.get("accepted_pp") or {}).get(f"{view}:{seq}")
        cert = {
            "kind": "prepared-certificate",
            "protocol": PBFT_FINALITY_PROTOCOL,
            "view": view,
            "seq": seq,
            "digest": digest,
            "q": q,
            "replica_ids": sorted(unique),
            "preprepare": pp if isinstance(pp, dict) else None,
            "prepares": list(unique.values()),
        }
        if not verify_prepared_certificate(cert):
            return False
        with self._lock:
            self._state.setdefault("prepared", {})[f"{view}:{seq}"] = cert
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
