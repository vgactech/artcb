"""Four independent settlement replicas over HTTP (same machine, real processes).

NOT four OVH VMs. NOT libp2p. NOT mainnet.

Each replica has its own SettlementLedger file. A prepare/commit majority
is required before a WorkID is paid. Same WorkID + different SettlementID
cannot produce two payments.

Classification: DISTRIBUTED PROCESS SIMULATION.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.artcb.economics.economic_snapshot import AlreadySettled, SettlementLedger, settlement_id

logger = logging.getLogger("artcb.economics.replicated_settlement")

PROTOCOL_VERSION = "169-replicated-settlement"


class Partitioned(RuntimeError):
    pass


class SnapshotMismatch(ValueError):
    pass


@dataclass
class ReplicaState:
    node_id: str
    data_dir: Path
    ledger: SettlementLedger
    reservations: dict[str, str] = field(default_factory=dict)  # work_id -> sid
    isolated: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def prepare(self, work_id: str, sid: str) -> str:
        with self.lock:
            if self.ledger.count_for_work(work_id) > 0:
                return "already_settled"
            held = self.reservations.get(work_id)
            if held and held != sid:
                return "reserved_other"
            self.reservations[work_id] = sid
            return "prepared"

    def commit(self, work_id: str, sid: str, epoch: int) -> dict[str, Any]:
        with self.lock:
            try:
                row = self.ledger.consume(sid, work_id=work_id, node_id=self.node_id, epoch=epoch)
            except AlreadySettled:
                if self.ledger.count_for_work(work_id) == 1:
                    return {"ok": True, "duplicate": True, "work_id": work_id}
                raise
            self.reservations.pop(work_id, None)
            return {"ok": True, "duplicate": False, **row}


class ReplicaServer:
    def __init__(self, node_id: str, host: str, port: int, data_dir: Path) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self.state = ReplicaState(
            node_id=node_id,
            data_dir=data_dir,
            ledger=SettlementLedger(data_dir / "ledger.json"),
        )
        self.peer_urls: list[str] = []
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        state = self.state
        node_id = self.node_id

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                return

            def _json(self, code: int, payload: dict[str, Any]) -> None:
                raw = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._json(200, {"node": node_id, "ok": True, "isolated": state.isolated})
                    return
                if self.path == "/consumed":
                    self._json(200, {"node": node_id, "rows": state.ledger.to_list()})
                    return
                self._json(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/isolate":
                    state.isolated = bool(body.get("isolated", True))
                    self._json(200, {"isolated": state.isolated})
                    return
                if state.isolated and self.path in ("/prepare", "/commit"):
                    self._json(503, {"error": "partitioned"})
                    return
                if self.path == "/prepare":
                    result = state.prepare(str(body["work_id"]), str(body["settlement_id"]))
                    self._json(200 if result == "prepared" else 409, {"result": result, "node": node_id})
                    return
                if self.path == "/commit":
                    try:
                        row = state.commit(str(body["work_id"]), str(body["settlement_id"]), int(body.get("epoch", 1)))
                        self._json(200, row)
                    except AlreadySettled as exc:
                        self._json(409, {"error": "AlreadySettled", "detail": str(exc)})
                    return
                self._json(404, {"error": "not_found"})

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name=f"replica-{node_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 2.0) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = {"detail": detail[:200]}
        return exc.code, parsed
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


class Cluster:
    def __init__(self, replicas: list[ReplicaServer]) -> None:
        self.replicas = replicas
        self._commit_locks: dict[str, threading.Lock] = {}
        urls = [r.url for r in replicas]
        for r in replicas:
            r.peer_urls = urls

    @property
    def majority(self) -> int:
        return (len(self.replicas) // 2) + 1

    def settle(
        self,
        *,
        proposer: str,
        work_id: str,
        snapshot_digest: str,
        epoch: int = 1,
        protocol_version: str = PROTOCOL_VERSION,
        forged_sid: str | None = None,
    ) -> dict[str, Any]:
        sid = forged_sid or settlement_id(
            work_id=work_id,
            snapshot_digest=snapshot_digest,
            protocol_version=protocol_version,
        )
        prepared = 0
        rejected = []
        reachable = 0
        for r in self.replicas:
            code, body = _http_json("POST", f"{r.url}/prepare", {"work_id": work_id, "settlement_id": sid})
            if code == 0 or body.get("error") == "partitioned":
                rejected.append({"node": r.node_id, "error": "partition"})
                continue
            reachable += 1
            if code == 200 and body.get("result") == "prepared":
                prepared += 1
            else:
                rejected.append({"node": r.node_id, "result": body.get("result") or body})
        if prepared < self.majority:
            return {
                "ok": False,
                "reason": "no_majority",
                "settlement_id": sid,
                "work_id": work_id,
                "proposer": proposer,
                "prepared": prepared,
                "reachable": reachable,
                "rejected": rejected,
            }
        lock = self._commit_locks.setdefault(work_id, threading.Lock())
        with lock:
            already = sum(1 for r in self.replicas if r.state.ledger.count_for_work(work_id) > 0)
            if already >= self.majority:
                return {
                    "ok": False,
                    "reason": "already_settled",
                    "settlement_id": sid,
                    "work_id": work_id,
                    "proposer": proposer,
                    "prepared": prepared,
                    "rejected": rejected,
                }
            commits = []
            for r in self.replicas:
                code, body = _http_json(
                    "POST",
                    f"{r.url}/commit",
                    {"work_id": work_id, "settlement_id": sid, "epoch": epoch},
                )
                if code == 200 and not body.get("duplicate"):
                    commits.append(r.node_id)
            return {
                "ok": bool(commits),
                "settlement_id": sid,
                "work_id": work_id,
                "proposer": proposer,
                "prepared": prepared,
                "commits": commits,
                "rejected": rejected,
            }

    def isolate(self, node_id: str, isolated: bool) -> None:
        for r in self.replicas:
            if r.node_id == node_id:
                _http_json("POST", f"{r.url}/isolate", {"isolated": isolated})

    def consumed_counts(self, work_id: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.replicas:
            out[r.node_id] = r.state.ledger.count_for_work(work_id)
        return out

    def stop(self) -> None:
        for r in self.replicas:
            r.stop()


def build_cluster(root: Path, *, base_port: int = 18691) -> Cluster:
    replicas: list[ReplicaServer] = []
    for i, name in enumerate(("A", "B", "C", "D")):
        data = root / name
        data.mkdir(parents=True, exist_ok=True)
        srv = ReplicaServer(name, "127.0.0.1", base_port + i, data)
        srv.start()
        replicas.append(srv)
    return Cluster(replicas)
