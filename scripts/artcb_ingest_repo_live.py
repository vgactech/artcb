#!/usr/bin/env python3
"""Push the git-tracked tree onto the live book, scoped by visibility.

Public bodies → public blocks. Org/group/private bodies → private blocks
(not P2P) + public catalog listing every path. Secrets: catalog only.
Never prints tokens.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import (  # noqa: E402
    apply_key_to_environ,
    assert_live_transport,
    auth_headers,
    resolve_api_key,
    resolve_api_url,
    tls_context,
)
from artcb.memory.repo_ingest import git_tracked_files, pack_batches, read_record  # noqa: E402


def _call(method: str, path: str, body: dict | None = None, timeout: int = 180) -> tuple[int, dict]:
    key = resolve_api_key()
    url = resolve_api_url().rstrip("/") + path
    assert_live_transport(url, sending_bearer=True)
    data = None if body is None else json.dumps(body).encode()
    headers = auth_headers(key)
    headers["X-ARTCB-Agent-Id"] = "cursor-cloud-agent"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout, context=tls_context(url)) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail[:500]}
        return exc.code, parsed


def main() -> int:
    apply_key_to_environ(resolve_api_key())
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    paths = git_tracked_files(ROOT)
    records = [read_record(ROOT, rel) for rel in paths]
    batches = pack_batches(records, git_sha=git_sha)
    results = []
    for batch in batches:
        payload = batch.to_payload()
        st, resp = _call("POST", "/api/v1/ai/ingest-batch", payload)
        via = "ingest-batch"
        if st in {404, 405, 422}:
            via = "ai-memo"
            vis = "public" if batch.scope == "public" else "private"
            st, resp = _call(
                "POST",
                "/api/v1/ai/memo",
                {
                    "content": payload["source_text"],
                    "memo_type": "observation",
                    "tags": [
                        "ingest",
                        batch.scope,
                        batch.kind,
                        batch.batch_id,
                    ],
                    "session_id": "sess_249_repo_ingest",
                    "visibility": vis,
                    "inject_context": False,
                },
            )
        rec = {
            "http": st,
            "via": via,
            "batch_id": batch.batch_id,
            "scope": batch.scope,
            "kind": batch.kind,
            "file_count": len(batch.files),
            "chars": len(batch.source_text),
            "block_index": resp.get("block_index"),
            "hash": resp.get("block_hash") or resp.get("hash"),
            "graph_id": resp.get("graph_id"),
            "detail": resp.get("detail") if st >= 400 else None,
        }
        results.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        if st >= 500:
            # one retry
            st, resp = _call("POST", "/api/v1/ai/ingest-batch", payload)
            rec["retry_http"] = st
            rec["retry_block"] = resp.get("block_index")
            print(json.dumps({"retry": rec["batch_id"], "http": st, "block": rec["retry_block"]}), flush=True)

    # KCG on catalog graph if we have it
    catalog = next((r for r in results if r["kind"] == "repo_catalog" and r["http"] == 200), None)
    kcg = None
    if catalog and catalog.get("graph_id"):
        st, kcg = _call(
            "POST",
            "/api/v1/kcg/publish",
            {
                "graph_id": catalog["graph_id"],
                "producer_address": "cursor-cloud-agent",
                "pol_block_index": catalog.get("block_index") or 0,
                "pol_score": 0.75,
                "title": f"Repo catalog {git_sha[:12]} n={len(records)}",
                "visibility": "public",
            },
        )
        kcg = {"http": st, **({} if not isinstance(kcg, dict) else kcg)}

    st_mem, memory = _call("GET", "/api/v1/ai/ingest/catalog")
    st_chain, chain = _call("GET", "/api/v1/chain/status")
    summary = {
        "git_sha": git_sha,
        "tracked": len(records),
        "batches": len(batches),
        "ok": sum(1 for r in results if r["http"] == 200),
        "fail": sum(1 for r in results if r["http"] != 200),
        "by_scope": {},
        "kcg": {k: kcg.get(k) for k in ("http", "knowledge_id", "graph_id") if kcg},
        "catalog_http": st_mem,
        "catalog_count": memory.get("count") if isinstance(memory, dict) else None,
        "catalog_by_scope": memory.get("by_scope") if isinstance(memory, dict) else None,
        "chain": chain if st_chain == 200 else {"http": st_chain},
        "token_printed": False,
    }
    for r in results:
        if r["http"] == 200:
            summary["by_scope"][r["scope"]] = summary["by_scope"].get(r["scope"], 0) + 1
    out = ROOT / "logs" / "249_ingest_live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # do not write this json into git; local measure only
    try:
        out.write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")
    except OSError:
        pass
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["fail"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
