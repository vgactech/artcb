"""Official-replica path — full book among the four compute IPv4s.

Anonymous P2P stays public-only. That path cannot rebuild a mixed
public/private hash chain (a public block's prev_hash often points at a
private predecessor). The four official nodes are the operator set, not
anonymous peers: they receive every visibility, plus graphs / KCG / ingest
index, so height 1074 is the same book everywhere.

Never accept a replica envelope from a non-official host.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from src.artcb.crypto.kem import KEMError, encrypt_payload
from src.artcb.node_registry import (
    NODES,
    OFFICIAL_COMPUTE_HTTP_PORT,
    OFFICIAL_COMPUTE_IPV4,
    OFFICIAL_COMPUTE_NODE_IDS,
    is_official_compute_ipv4,
)
from src.artcb.p2p.flux import append_flux
from src.artcb.p2p.peers import PeerRecord
from src.artcb.p2p.sync import P2PSyncError, P2PSyncService

logger = logging.getLogger("artcb.p2p.official_replica")

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})
BLOCK_CHUNK = 20
FILE_CHUNK = 8
FILE_BYTES_CAP = 1_500_000
HTTP_TIMEOUT = 180.0
REPLICA_REL_GLOBS: tuple[tuple[str, str], ...] = (
    ("graphs", "*.json"),
    ("memory", "repo_index.jsonl"),
    ("kcg", "*"),
    ("consensus", "byzantine_evidence.jsonl"),
)


def replica_peer_allowed(host: str) -> bool:
    raw = (host or "").strip().lower()
    if raw in LOOPBACK_HOSTS:
        return True
    return is_official_compute_ipv4(raw)


def request_peer_host(request: Any) -> str:
    """Trust X-Forwarded-For only when the TCP peer is loopback (nginx)."""
    client = ""
    if getattr(request, "client", None) is not None:
        client = (request.client.host or "").strip()
    if client in LOOPBACK_HOSTS:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        return forwarded or client
    return client


def data_dir_of(sync: P2PSyncService) -> Path:
    return Path(sync.chain.blocks_path).parent.parent


def list_replica_blocks(sync: P2PSyncService, *, from_index: int = 0, limit: int = BLOCK_CHUNK) -> list[dict[str, Any]]:
    cap = max(1, min(int(limit or BLOCK_CHUNK), 80))
    start = max(0, int(from_index or 0))
    blocks = sync.chain._read_all_blocks()
    out = [b for b in blocks if int(b.get("index") or 0) >= start]
    return out[:cap]


def import_replica_blocks(
    sync: P2PSyncService,
    blocks: list[dict[str, Any]],
    *,
    from_node_id: str = "official-replica",
) -> dict[str, Any]:
    imported = 0
    duplicates = 0
    rejected: list[dict[str, Any]] = []
    ordered = sorted(
        blocks,
        key=lambda row: int(row.get("index") or 0) if str(row.get("index") or "").isdigit() or isinstance(row.get("index"), int) else 0,
    )
    for block in ordered:
        existing = sync.chain._read_all_blocks()
        block_hash = str(block.get("hash") or "")
        if block_hash and any(str(row.get("hash") or "") == block_hash for row in existing):
            duplicates += 1
            continue
        held = next((row for row in existing if int(row.get("index", -1)) == int(block.get("index") or -1)), None)
        try:
            ok = sync.chain.import_extending_block(
                block, require_public=False, from_node_id=from_node_id
            )
        except Exception as exc:  # noqa: BLE001 — one bad block must not abort the chunk mid-write
            rejected.append({"index": block.get("index"), "reason": type(exc).__name__})
            break
        if ok:
            imported += 1
        else:
            reason = "import_failed"
            if held and str(held.get("hash") or "") and block_hash and str(held.get("hash")) != block_hash:
                reason = "equivocation"
            rejected.append({"index": block.get("index"), "reason": reason})
            break
    return {
        "imported": imported,
        "duplicates": duplicates,
        "rejected": rejected,
        "received": len(blocks),
        "height": len(sync.chain._read_all_blocks()),
        "last_hash": sync.chain.last_hash(),
    }


def _safe_rel(rel: str) -> Path | None:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return None
    if path.parts and path.parts[0] not in {"graphs", "memory", "kcg", "consensus"}:
        return None
    return path


def list_replica_files(data_dir: Path) -> list[dict[str, Any]]:
    root = Path(data_dir)
    items: list[dict[str, Any]] = []
    for folder, pattern in REPLICA_REL_GLOBS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            items.append({"path": rel, "sha256": digest, "bytes": path.stat().st_size})
    return items


def read_replica_file_payloads(data_dir: Path, rels: list[str]) -> list[dict[str, Any]]:
    root = Path(data_dir)
    out: list[dict[str, Any]] = []
    import base64

    for rel in rels:
        safe = _safe_rel(rel)
        if safe is None:
            continue
        path = root / safe
        if not path.is_file():
            continue
        raw = path.read_bytes()
        out.append(
            {
                "path": safe.as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "content_b64": base64.b64encode(raw).decode("ascii"),
            }
        )
    return out


def write_replica_files(data_dir: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    import base64

    root = Path(data_dir)
    written = 0
    skipped = 0
    rejected = 0
    for item in files:
        safe = _safe_rel(str(item.get("path") or ""))
        if safe is None:
            rejected += 1
            continue
        try:
            raw = base64.b64decode(str(item.get("content_b64") or ""), validate=True)
        except (ValueError, TypeError):
            rejected += 1
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if item.get("sha256") and str(item.get("sha256")) != digest:
            rejected += 1
            continue
        dest = root / safe
        dest.parent.mkdir(parents=True, exist_ok=True)
        if safe.as_posix() == "consensus/byzantine_evidence.jsonl" and dest.is_file():
            existing = {ln for ln in dest.read_text(encoding="utf-8").splitlines() if ln.strip()}
            incoming = [ln for ln in raw.decode("utf-8", errors="replace").splitlines() if ln.strip()]
            extra = [ln for ln in incoming if ln not in existing]
            if not extra:
                skipped += 1
                continue
            with dest.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(extra) + "\n")
            written += 1
            continue
        if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == digest:
            skipped += 1
            continue
        dest.write_bytes(raw)
        written += 1
    return {"written": written, "skipped": skipped, "rejected": rejected, "received": len(files)}


def official_http_targets() -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    for node_id in OFFICIAL_COMPUTE_NODE_IDS:
        spec = NODES[node_id]
        host = spec.ssh_host
        if not host:
            continue
        rows.append((node_id, host, OFFICIAL_COMPUTE_HTTP_PORT))
    return rows


def _peer_from_status(node_id: str, host: str, port: int, status: dict[str, Any]) -> PeerRecord | None:
    kem = str(status.get("kem_public_key_hex") or "")
    if len(kem) < 32:
        return None
    return PeerRecord(
        peer_id=str(status.get("node_id") or node_id),
        host=host,
        port=port,
        kem_public_key_hex=kem,
        label=node_id,
        scheme="http",
    )


def probe_official_peer(host: str, port: int, timeout: float = 8.0) -> dict[str, Any]:
    url = f"http://{host}:{port}"
    out: dict[str, Any] = {"host": host, "port": port}
    try:
        with httpx.Client(timeout=timeout) as client:
            t0 = time.perf_counter()
            health = client.get(f"{url}/health")
            out["health_http"] = health.status_code
            out["health_rtt_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            t1 = time.perf_counter()
            p2p = client.get(f"{url}/api/v1/p2p/status")
            out["p2p_http"] = p2p.status_code
            out["p2p_rtt_ms"] = round((time.perf_counter() - t1) * 1000, 2)
            out["p2p"] = p2p.json() if p2p.status_code == 200 else {}
            t2 = time.perf_counter()
            chain = client.get(f"{url}/api/v1/chain/status")
            out["chain_http"] = chain.status_code
            out["chain_rtt_ms"] = round((time.perf_counter() - t2) * 1000, 2)
            out["chain"] = chain.json() if chain.status_code == 200 else {}
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
    return out


def push_encrypted(sync: P2PSyncService, peer: PeerRecord, payload: dict[str, Any], path: str) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    t_enc = time.perf_counter()
    try:
        envelope = encrypt_payload(raw, bytes.fromhex(peer.kem_public_key_hex))
    except (KEMError, ValueError, RuntimeError) as exc:
        raise P2PSyncError(f"replica_encrypt_failed:{type(exc).__name__}") from exc
    envelope["from_node_id"] = sync.identity.node_id
    envelope["from_kem_public_key_hex"] = sync.identity.kem_public_key_hex
    envelope["official_replica"] = "1"
    encrypt_ms = round((time.perf_counter() - t_enc) * 1000, 2)
    url = f"{peer.base_url}{path}"
    wire = json.dumps({"envelope": envelope}, ensure_ascii=False).encode("utf-8")
    t_http = time.perf_counter()
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.post(url, json={"envelope": envelope})
            body = resp.json() if resp.content else {}
            resp.raise_for_status()
    except Exception as exc:
        http_ms = round((time.perf_counter() - t_http) * 1000, 2)
        raise P2PSyncError(f"replica_http_failed:{type(exc).__name__}:http_ms={http_ms}") from exc
    http_ms = round((time.perf_counter() - t_http) * 1000, 2)
    return {
        "encrypt_ms": encrypt_ms,
        "http_ms": http_ms,
        "rtt_ms": round(encrypt_ms + http_ms, 2),
        "bytes_plain": len(raw),
        "bytes_wire": len(wire),
        "remote": body,
    }


def push_blocks_to_peer(
    sync: P2PSyncService,
    peer: PeerRecord,
    *,
    from_index: int,
    chunk: int = BLOCK_CHUNK,
) -> list[dict[str, Any]]:
    data_dir = data_dir_of(sync)
    blocks = [b for b in sync.chain._read_all_blocks() if int(b.get("index") or 0) >= int(from_index)]
    rows: list[dict[str, Any]] = []
    if not blocks:
        row = append_flux(
            data_dir,
            {
                "kind": "official_replica_blocks",
                "direction": "push",
                "peer": peer.label or peer.peer_id,
                "host": peer.host,
                "from_index": from_index,
                "to_index": from_index,
                "pushed": 0,
                "imported": 0,
                "ok": True,
                "message": "nothing_to_send",
            },
        )
        return [row]
    size = max(1, min(int(chunk or BLOCK_CHUNK), 80))
    height_before_local = len(sync.chain._read_all_blocks())
    for offset in range(0, len(blocks), size):
        batch = blocks[offset : offset + size]
        start = int(batch[0].get("index") or 0)
        end = int(batch[-1].get("index") or 0)
        try:
            sent = push_encrypted(
                sync,
                peer,
                {
                    "kind": "official_replica",
                    "from_index": start,
                    "to_index": end,
                    "blocks": batch,
                    "count": len(batch),
                },
                "/api/v1/p2p/replica/push",
            )
            remote = sent.get("remote") or {}
            row = append_flux(
                data_dir,
                {
                    "kind": "official_replica_blocks",
                    "direction": "push",
                    "peer": peer.label or peer.peer_id,
                    "host": peer.host,
                    "chunk": f"{start}-{end}",
                    "from_index": start,
                    "to_index": end,
                    "pushed": len(batch),
                    "imported": int(remote.get("imported") or 0),
                    "duplicates": remote.get("duplicates"),
                    "bytes_plain": sent["bytes_plain"],
                    "bytes_wire": sent["bytes_wire"],
                    "encrypt_ms": sent["encrypt_ms"],
                    "http_ms": sent["http_ms"],
                    "rtt_ms": sent["rtt_ms"],
                    "height_before_remote": remote.get("height"),
                    "last_hash_remote": remote.get("last_hash"),
                    "height_local": height_before_local,
                    "ok": True,
                },
            )
            rows.append(row)
            if remote.get("rejected"):
                break
        except P2PSyncError as exc:
            row = append_flux(
                data_dir,
                {
                    "kind": "official_replica_blocks",
                    "direction": "push",
                    "peer": peer.label or peer.peer_id,
                    "host": peer.host,
                    "chunk": f"{start}-{end}",
                    "from_index": start,
                    "to_index": end,
                    "pushed": len(batch),
                    "ok": False,
                    "error": str(exc)[:200],
                },
            )
            rows.append(row)
            break
    return rows


def _file_chunks(items: list[dict[str, Any]]) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    current_bytes = 0
    for item in items:
        size = int(item.get("bytes") or 0)
        if current and (len(current) >= FILE_CHUNK or current_bytes + size > FILE_BYTES_CAP):
            chunks.append(current)
            current = []
            current_bytes = 0
        current.append(str(item["path"]))
        current_bytes += size
    if current:
        chunks.append(current)
    return chunks


def push_files_to_peer(sync: P2PSyncService, peer: PeerRecord) -> list[dict[str, Any]]:
    data_dir = data_dir_of(sync)
    catalog = list_replica_files(data_dir)
    rows: list[dict[str, Any]] = []
    for rels in _file_chunks(catalog):
        payloads = read_replica_file_payloads(data_dir, rels)
        if not payloads:
            continue
        start_name = payloads[0]["path"]
        try:
            sent = push_encrypted(
                sync,
                peer,
                {"kind": "official_replica_files", "files": payloads, "count": len(payloads)},
                "/api/v1/p2p/replica/files",
            )
            remote = sent.get("remote") or {}
            row = append_flux(
                data_dir,
                {
                    "kind": "official_replica_files",
                    "direction": "push",
                    "peer": peer.label or peer.peer_id,
                    "host": peer.host,
                    "chunk": start_name,
                    "pushed": len(payloads),
                    "imported": int(remote.get("written") or 0),
                    "bytes_plain": sent["bytes_plain"],
                    "bytes_wire": sent["bytes_wire"],
                    "encrypt_ms": sent["encrypt_ms"],
                    "http_ms": sent["http_ms"],
                    "rtt_ms": sent["rtt_ms"],
                    "ok": True,
                },
            )
            rows.append(row)
        except P2PSyncError as exc:
            row = append_flux(
                data_dir,
                {
                    "kind": "official_replica_files",
                    "direction": "push",
                    "peer": peer.label or peer.peer_id,
                    "host": peer.host,
                    "chunk": start_name,
                    "pushed": len(payloads),
                    "ok": False,
                    "error": str(exc)[:200],
                },
            )
            rows.append(row)
            break
    return rows


def run_official_replica(sync: P2PSyncService, *, include_files: bool = True) -> dict[str, Any]:
    """Push the local book to every other official compute node."""
    local_kem = sync.identity.kem_public_key_hex
    peers_out: list[dict[str, Any]] = []
    for node_id, host, port in official_http_targets():
        probe = probe_official_peer(host, port)
        p2p = probe.get("p2p") or {}
        if str(p2p.get("kem_public_key_hex") or "") == local_kem:
            peers_out.append({"node_id": node_id, "host": host, "skipped": "self"})
            continue
        if probe.get("error") or int(probe.get("p2p_http") or 0) != 200:
            peers_out.append({"node_id": node_id, "host": host, "ok": False, "probe": probe})
            continue
        peer = _peer_from_status(node_id, host, port, p2p)
        if peer is None:
            peers_out.append({"node_id": node_id, "host": host, "ok": False, "error": "no_kem"})
            continue
        remote_height = int((probe.get("chain") or {}).get("height") or 0)
        block_rows = push_blocks_to_peer(sync, peer, from_index=remote_height)
        file_rows: list[dict[str, Any]] = []
        if include_files and all(r.get("ok") for r in block_rows):
            file_rows = push_files_to_peer(sync, peer)
        after = probe_official_peer(host, port)
        peers_out.append(
            {
                "node_id": node_id,
                "host": host,
                "ok": all(r.get("ok") for r in block_rows) and all(r.get("ok") for r in file_rows or [{"ok": True}]),
                "height_before": remote_height,
                "height_after": (after.get("chain") or {}).get("height"),
                "last_hash_after": (after.get("chain") or {}).get("last_hash"),
                "probe_rtt_ms": {
                    "health": probe.get("health_rtt_ms"),
                    "p2p": probe.get("p2p_rtt_ms"),
                    "chain": probe.get("chain_rtt_ms"),
                },
                "block_chunks": block_rows,
                "file_chunks": len(file_rows),
                "file_ok": all(r.get("ok") for r in file_rows) if file_rows else None,
            }
        )
    return {
        "official_ipv4": list(OFFICIAL_COMPUTE_IPV4),
        "local_height": len(sync.chain._read_all_blocks()),
        "local_last_hash": sync.chain.last_hash(),
        "peers": peers_out,
        "note": (
            "Anonymous P2P stays public-only. This path is the four official "
            "compute IPv4s only. Ingest 1065 had no inter-node flux."
        ),
    }
