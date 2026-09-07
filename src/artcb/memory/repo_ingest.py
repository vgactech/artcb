"""Pack a git tree into scoped ingest batches (catalog + file bodies)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.artcb.ir.models import IREdge, IRGraph, IRNode, sha256_text
from src.artcb.memory.repo_scope import (
    Visibility,
    chain_visibility,
    classify_path,
    is_binary_path,
    is_secret_path,
    redact_text,
)

CATALOG_KIND = "repo_catalog"
BATCH_KIND = "repo_batch"
FILE_MARK = "###FILE"
FILE_END = "###END"
DEFAULT_BATCH_CHARS = 28_000
DEFAULT_MAX_FILE_CHARS = 28_000
LOGICAL_ORG = "org_artcb_memory"
LOGICAL_GROUP = "group_artcb_agents"


@dataclass
class FileRecord:
    path: str
    sha256: str
    size: int
    scope: Visibility
    body: str | None
    redacted_lines: int = 0
    binary: bool = False
    secret: bool = False
    skipped_reason: str | None = None


@dataclass
class IngestBatch:
    batch_id: str
    scope: Visibility
    chain_visibility: str
    kind: str
    files: list[dict[str, Any]] = field(default_factory=list)
    source_text: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "scope": self.scope,
            "chain_visibility": self.chain_visibility,
            "kind": self.kind,
            "scope_id": LOGICAL_ORG if self.scope == "organization" else (
                LOGICAL_GROUP if self.scope == "group" else None
            ),
            "file_count": len(self.files),
            "files": self.files,
            "source_text": self.source_text,
        }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_tracked_files(root: Path) -> list[str]:
    raw = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=root,
        text=False,
    )
    return [p.decode("utf-8") for p in raw.split(b"\0") if p]


def read_record(root: Path, rel: str) -> FileRecord:
    path = root / rel
    scope = classify_path(rel)
    if not path.is_file():
        return FileRecord(rel, "0" * 64, 0, scope, None, skipped_reason="missing")
    data = path.read_bytes()
    digest = sha256_bytes(data)
    size = len(data)
    secret = is_secret_path(rel)
    binary = is_binary_path(rel) or b"\x00" in data[:4096]
    if secret:
        return FileRecord(rel, digest, size, "private", None, secret=True, skipped_reason="secret")
    if binary:
        return FileRecord(rel, digest, size, scope, None, binary=True, skipped_reason="binary")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return FileRecord(rel, digest, size, scope, None, binary=True, skipped_reason="not_utf8")
    text, n_redact = redact_text(text)
    return FileRecord(rel, digest, size, scope, text, redacted_lines=n_redact)


def catalog_lines(records: Iterable[FileRecord], *, git_sha: str) -> str:
    rows = []
    for r in records:
        rows.append(
            {
                "path": r.path,
                "sha256": r.sha256,
                "size": r.size,
                "scope": r.scope,
                "chain_visibility": chain_visibility(r.scope),
                "body": r.body is not None,
                "binary": r.binary,
                "secret": r.secret,
                "redacted_lines": r.redacted_lines,
                "skipped_reason": r.skipped_reason,
            }
        )
    header = {
        "kind": CATALOG_KIND,
        "git_sha": git_sha,
        "file_count": len(rows),
        "logical_org": LOGICAL_ORG,
        "logical_group": LOGICAL_GROUP,
    }
    lines = [json.dumps(header, ensure_ascii=False)]
    lines.extend(json.dumps(row, ensure_ascii=False) for row in rows)
    return "\n".join(lines) + "\n"


def _chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def iter_body_units(record: FileRecord, *, max_file_chars: int) -> Iterator[tuple[str, str, str, int]]:
    """Yield (path_label, sha256, text, chunk_index)."""
    if record.body is None:
        return
    chunks = _chunk_text(record.body, max_file_chars)
    if len(chunks) == 1:
        yield record.path, record.sha256, chunks[0], 0
        return
    for i, chunk in enumerate(chunks):
        yield f"{record.path}#chunk{i}", record.sha256, chunk, i


def pack_batches(
    records: list[FileRecord],
    *,
    git_sha: str,
    batch_chars: int = DEFAULT_BATCH_CHARS,
    max_file_chars: int = DEFAULT_MAX_FILE_CHARS,
) -> list[IngestBatch]:
    catalog_text = catalog_lines(records, git_sha=git_sha)
    catalog_files = [{"path": r.path, "sha256": r.sha256, "scope": r.scope, "size": r.size} for r in records]
    batches: list[IngestBatch] = []
    cat_chunks = _chunk_text(catalog_text, batch_chars)
    for i, chunk in enumerate(cat_chunks):
        batches.append(
            IngestBatch(
                batch_id=f"cat_{i}_{uuid.uuid4().hex[:8]}",
                scope="public",
                chain_visibility="public",
                kind=CATALOG_KIND,
                files=catalog_files if i == 0 else [{"path": f"_catalog_chunk_{i}", "sha256": "", "scope": "public", "size": len(chunk)}],
                source_text=chunk,
            )
        )
    buckets: dict[Visibility, list[tuple[str, str, str]]] = {
        "public": [],
        "organization": [],
        "group": [],
        "private": [],
    }
    for rec in records:
        for path_label, digest, text, _i in iter_body_units(rec, max_file_chars=max_file_chars):
            buckets[rec.scope].append((path_label, digest, text))

    for scope, units in buckets.items():
        current: list[dict[str, Any]] = []
        parts: list[str] = []
        size = 0

        def flush() -> None:
            nonlocal current, parts, size
            if not current:
                return
            batches.append(
                IngestBatch(
                    batch_id=f"b_{uuid.uuid4().hex[:10]}",
                    scope=scope,
                    chain_visibility=chain_visibility(scope),
                    kind=BATCH_KIND,
                    files=current,
                    source_text="".join(parts),
                )
            )
            current, parts, size = [], [], 0

        for path_label, digest, text in units:
            block = f"{FILE_MARK} path={path_label} sha256={digest}\n{text}\n{FILE_END}\n"
            if size and size + len(block) > batch_chars:
                flush()
            current.append({"path": path_label, "sha256": digest, "chars": len(text)})
            parts.append(block)
            size += len(block)
        flush()
    return batches


def build_ingest_graph(batch: IngestBatch) -> IRGraph:
    graph_id = f"ing_{batch.kind}_{batch.batch_id}"
    checksum = sha256_text(batch.source_text)
    nodes: list[IRNode] = []
    paths = [f["path"] for f in batch.files[:48]]
    title = f"ARTCB ingest {batch.kind} scope={batch.scope} n={len(batch.files)}"
    nodes.append(
        IRNode(
            id="n1",
            t="E",
            sym="ING1",
            txt=title,
            checksum=sha256_text(title),
            start=0,
            end=len(title),
        )
    )
    for i, path in enumerate(paths, start=2):
        nodes.append(
            IRNode(
                id=f"n{i}",
                t="F",
                sym=f"P{i}",
                txt=path,
                checksum=sha256_text(path),
                start=0,
                end=len(path),
            )
        )
    edges = [
        IREdge(**{"from": "n1", "to": f"n{i}", "rel": "contains", "w": 1.0})
        for i in range(2, len(nodes) + 1)
    ]
    return IRGraph(
        graph_id=graph_id,
        source_text=batch.source_text,
        nodes=nodes,
        edges=edges,
        checksum=checksum,
        orig_symbols={"learning_source": f"ai:ingest:{batch.kind}", "scope": batch.scope},
    )


def persist_index_rows(data_dir: Path, rows: list[dict[str, Any]]) -> Path:
    path = Path(data_dir) / "memory" / "repo_index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def load_index(data_dir: Path) -> list[dict[str, Any]]:
    path = Path(data_dir) / "memory" / "repo_index.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def apply_ingest_batch(state: Any, batch: IngestBatch, *, agent_id: str = "cursor-cloud-agent") -> dict[str, Any]:
    """Encode + persist graph + append one block. No contributors → no 60s mining throttle."""
    graph = build_ingest_graph(batch)
    state.register_graph(graph)
    graph_root = sha256_text(graph.checksum).replace("sha256:", "")
    public_symbols = {
        "learning_source": f"ai:ingest:{batch.kind}",
        "memo_type": "ingest",
        "agent_id": agent_id,
        "scope": batch.scope,
        "batch_id": batch.batch_id,
        "file_count": str(len(batch.files)),
        "kind": batch.kind,
    }
    if batch.scope == "organization":
        public_symbols["organization_id"] = LOGICAL_ORG
    if batch.scope == "group":
        public_symbols["group_id"] = LOGICAL_GROUP
    block = state.chain.append_block(
        graph_id=graph.graph_id,
        graph_root=graph_root,
        pol_score=0.75,
        visibility=batch.chain_visibility,
        group_id=None,
        contributors=None,
        public_symbols=public_symbols,
        source=f"ai:ingest:{batch.kind}",
    )
    data_dir = getattr(getattr(state, "settings", None), "data_dir", None)
    if data_dir is None:
        data_dir = Path("data")
    rows = [
        {
            "path": f.get("path"),
            "sha256": f.get("sha256"),
            "scope": batch.scope,
            "batch_id": batch.batch_id,
            "graph_id": graph.graph_id,
            "block_index": block.index,
            "block_hash": block.hash,
            "kind": batch.kind,
        }
        for f in batch.files
    ]
    persist_index_rows(Path(data_dir), rows)
    return {
        "ingested": True,
        "batch_id": batch.batch_id,
        "scope": batch.scope,
        "chain_visibility": batch.chain_visibility,
        "kind": batch.kind,
        "file_count": len(batch.files),
        "block_index": block.index,
        "block_hash": block.hash,
        "graph_id": graph.graph_id,
        "chars": len(batch.source_text),
    }


def parse_batch_files(source_text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    chunks = source_text.split(FILE_MARK)
    for chunk in chunks[1:]:
        header, _, rest = chunk.partition("\n")
        body, _, _tail = rest.partition(FILE_END)
        path = ""
        digest = ""
        for tok in header.split():
            if tok.startswith("path="):
                path = tok[5:]
            elif tok.startswith("sha256="):
                digest = tok[7:]
        out.append({"path": path, "sha256": digest, "text": body.lstrip("\n")})
    return out
