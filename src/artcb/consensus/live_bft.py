"""Live prepare/commit quorum between protocol-compatible peers (DV-05 C).

Lifted from replicated_settlement.Cluster (same-machine sim) onto the
live HTTP API. Classical bound: N >= 3F+1, Q = 2F+1.
With four live machines: N=4, F=1, Q=3.

This is settlement uniqueness (WorkID / SettlementID), not a rewrite of
block append. Block production remains longest valid public chain.
certified_distributed_mainnet is a separate gate.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.artcb.economics.economic_snapshot import AlreadySettled, SettlementLedger, settlement_id
from src.artcb.p2p.peers import PeerRecord

logger = logging.getLogger("artcb.consensus.live_bft")

LIVE_BFT_PROTOCOL: str = "188-live-bft-prepare-commit"


def n_f_q(n: int) -> tuple[int, int | None, int]:
    """Return (N, F, Q). F is None when N < 4 (3F+1 cannot give F>=1)."""
    n = int(n)
    if n < 4:
        return n, None, (n // 2) + 1 if n > 0 else 0
    f = (n - 1) // 3
    q = 2 * f + 1
    return n, f, q


def unique_compatible_hosts(peers: list[PeerRecord], *, self_host: str = "") -> list[PeerRecord]:
    seen: set[str] = set()
    out: list[PeerRecord] = []
    self_norm = (self_host or "").strip()
    if self_norm:
        seen.add(self_norm)
    for peer in peers:
        if not peer.protocol_compatible:
            continue
        host = (peer.host or "").strip()
        if not host or host in seen:
            continue
        seen.add(host)
        out.append(peer)
    return out


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 8.0) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


class LiveBftEngine:
    """Local replica + coordinator for live peers."""

    def __init__(self, data_dir, *, node_id: str) -> None:
        from pathlib import Path

        root = Path(data_dir)
        self.node_id = node_id
        self.ledger = SettlementLedger(root / "consensus" / "ledger.json")
        self._reservations: dict[str, str] = {}
        self._lock = threading.Lock()

    def prepare_local(self, work_id: str, sid: str) -> str:
        with self._lock:
            if self.ledger.count_for_work(work_id) > 0:
                return "already_settled"
            held = self._reservations.get(work_id)
            if held and held != sid:
                return "reserved_other"
            self._reservations[work_id] = sid
            return "prepared"

    def commit_local(self, work_id: str, sid: str, epoch: int) -> dict[str, Any]:
        with self._lock:
            try:
                row = self.ledger.consume(sid, work_id=work_id, node_id=self.node_id, epoch=epoch)
            except AlreadySettled:
                if self.ledger.count_for_work(work_id) == 1:
                    return {"ok": True, "duplicate": True, "work_id": work_id}
                raise
            self._reservations.pop(work_id, None)
            return {"ok": True, "duplicate": False, **row}

    def status(self, peers: list[PeerRecord], *, self_host: str = "") -> dict[str, Any]:
        remotes = unique_compatible_hosts(peers, self_host=self_host)
        n, f, q = n_f_q(1 + len(remotes))
        return {
            "live_bft_implemented": True,
            "protocol": LIVE_BFT_PROTOCOL,
            "n": n,
            "f": f,
            "q": q,
            "classical_bound": "N >= 3F+1",
            "quorum_rule": "Q = 2F+1",
            "bft_capable": f is not None and f >= 1,
            "compatible_remote_hosts": [p.host for p in remotes],
            "scope": "settlement_prepare_commit",
            "not_block_append_bft": True,
        }

    def propose(
        self,
        *,
        work_id: str,
        snapshot_digest: str,
        peers: list[PeerRecord],
        self_host: str = "",
        epoch: int = 1,
        forged_sid: str | None = None,
        skip_hosts: set[str] | None = None,
        extra_delay_hosts: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        remotes = unique_compatible_hosts(peers, self_host=self_host)
        skip = {h.strip() for h in (skip_hosts or set())}
        remotes = [p for p in remotes if p.host not in skip]
        n, f, q = n_f_q(1 + len(remotes) + len(skip))
        sid = forged_sid or settlement_id(
            work_id=work_id,
            snapshot_digest=snapshot_digest,
            protocol_version=LIVE_BFT_PROTOCOL,
        )
        if f is None:
            return {
                "ok": False,
                "reason": "n_lt_4_not_bft",
                "settlement_id": sid,
                "work_id": work_id,
                "n": n,
                "f": f,
                "q": q,
                "prepared": 0,
                "rejected": [],
            }
        delays = extra_delay_hosts or {}
        prepared = 0
        rejected: list[dict[str, Any]] = []
        local = self.prepare_local(work_id, sid)
        if local == "prepared":
            prepared += 1
        else:
            rejected.append({"node": self.node_id, "result": local})
        for peer in remotes:
            timeout = 8.0 + float(delays.get(peer.host, 0))
            code, body = _http_json(
                "POST",
                f"{peer.base_url}/api/v1/consensus/prepare",
                {"work_id": work_id, "settlement_id": sid},
                timeout=timeout,
            )
            if code == 200 and body.get("result") == "prepared":
                prepared += 1
            else:
                rejected.append({"host": peer.host, "http": code, "body": body})
        if f is None or prepared < q:
            return {
                "ok": False,
                "reason": "no_majority" if f is not None else "n_lt_4_not_bft",
                "settlement_id": sid,
                "work_id": work_id,
                "n": n,
                "f": f,
                "q": q,
                "prepared": prepared,
                "rejected": rejected,
            }
        commits = []
        try:
            self.commit_local(work_id, sid, epoch)
            commits.append(self.node_id)
        except AlreadySettled as exc:
            return {
                "ok": False,
                "reason": "already_settled",
                "settlement_id": sid,
                "work_id": work_id,
                "detail": str(exc),
                "n": n,
                "f": f,
                "q": q,
                "prepared": prepared,
            }
        for peer in remotes:
            code, body = _http_json(
                "POST",
                f"{peer.base_url}/api/v1/consensus/commit",
                {"work_id": work_id, "settlement_id": sid, "epoch": epoch},
                timeout=8.0,
            )
            if code == 200 and body.get("ok"):
                commits.append(peer.host)
        return {
            "ok": True,
            "settlement_id": sid,
            "work_id": work_id,
            "n": n,
            "f": f,
            "q": q,
            "prepared": prepared,
            "commits": commits,
            "rejected": rejected,
        }
