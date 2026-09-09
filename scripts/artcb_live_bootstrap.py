#!/usr/bin/env python3
"""Activate the live ARTCB node for this agent process.

Order: Cursor env → Doppler → ~/.artcb/cursor_agent.env → SSH pull from OVH.
If ARTCB_INGEST_PROMPT_FILE is set, POST that file to /ai/memo (agent-mediated;
Cursor does not inject the prompt). Prints metadata only. Never prints the API key.
Exit 0 if /health is reachable. Exit 3 if the key is missing but the node is up.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / "src")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from artcb.live import (  # noqa: E402
    apply_key_to_environ,
    compact_memory_snapshot,
    fetch_doppler_secret,
    http_json,
    ingest_prompt_file,
    ingest_thinking_file,
    prompt_file_skipped_reason,
    thinking_file_skipped_reason,
    pull_remote_agent_env,
    resolve_api_key,
    resolve_api_url,
    write_bootstrap_stamp,
    write_local_env,
)
from artcb.trace.thinking import empty_thinking_states  # noqa: E402


def _load_key() -> tuple[str, str]:
    key = resolve_api_key()
    if key:
        return key, "env_or_local_file"
    doppler_key = fetch_doppler_secret("ARTCB_API_KEY") or fetch_doppler_secret("ARTCB_NODE_API_KEY")
    if doppler_key.startswith("artcb_"):
        write_local_env({"ARTCB_API_URL": resolve_api_url(), "ARTCB_API_KEY": doppler_key})
        return doppler_key, "doppler"
    pulled = pull_remote_agent_env()
    remote_key = pulled.get("ARTCB_API_KEY", "")
    if remote_key.startswith("artcb_"):
        return remote_key, "ssh_node"
    return "", "missing"


def main() -> int:
    url = resolve_api_url()
    os.environ["ARTCB_API_URL"] = url
    key, source = _load_key()
    if key:
        apply_key_to_environ(key)

    health_code, health = http_json("GET", f"{url}/health")
    me_code, me = (0, {})
    if key:
        me_code, me = http_json("GET", f"{url}/api/v1/api-keys/me", api_key=key)
    econ_code, econ = http_json("GET", f"{url}/api/v1/economics/params")
    proto_code, proto = http_json("GET", f"{url}/api/v1/mining/protocol/status")
    chain_code, chain = http_json("GET", f"{url}/api/v1/chain/status")
    mem_code, memory = (0, {})
    kcg_code, kcg_stats = (0, {})
    ctx_code, context = (0, {})
    if key:
        mem_code, memory = http_json("GET", f"{url}/api/v1/ai/memory?limit=5", api_key=key)
        kcg_code, kcg_stats = http_json("GET", f"{url}/api/v1/kcg/stats", api_key=key)
        ctx_code, context = http_json("GET", f"{url}/api/v1/ai/context?limit=3", api_key=key)
    memory_snap = compact_memory_snapshot(
        chain=chain if isinstance(chain, dict) else {},
        memory=memory if isinstance(memory, dict) else {},
        kcg_stats=kcg_stats if isinstance(kcg_stats, dict) else {},
        context=context if isinstance(context, dict) else {},
    )

    last_memo_http = 0
    last_memo_chars = None
    last_memo_sha256 = None
    last_idx = memory_snap.get("last_memo_index")
    if key and last_idx is not None:
        last_memo_http, last_memo = http_json(
            "GET", f"{url}/api/v1/ai/memo/{last_idx}", api_key=key
        )
        if isinstance(last_memo, dict):
            text = last_memo.get("content_text") or ""
            if isinstance(text, str) and text:
                last_memo_chars = len(text)
                last_memo_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

    ingest: dict = {
        "ingest_platform_hook": False,
        "ingest_attempted": False,
        "ingest_skipped": True,
        "ingest_reason": prompt_file_skipped_reason(""),
        "includes_thinking": False,
        "includes_system_prompt": False,
        "token_count_known": False,
    }
    prompt_file = (os.environ.get("ARTCB_INGEST_PROMPT_FILE") or "").strip()
    if prompt_file and key:
        ingest["ingest_attempted"] = True
        p = Path(prompt_file)
        if p.is_file():
            ingest = ingest_prompt_file(
                p,
                url=url,
                api_key=key,
                tags=["ingest_at_receipt", "user_query", "bootstrap"],
                session_id="bootstrap-turn-prompt",
            )
        else:
            ingest["ingest_reason"] = prompt_file_skipped_reason(prompt_file)
            ingest["ingest_path"] = prompt_file

    thinking_ingest: dict = {
        "ingest_attempted": False,
        "ingest_skipped": True,
        "includes_thinking": False,
        "visibility": "private",
        "reason": thinking_file_skipped_reason(""),
        **empty_thinking_states(reason=thinking_file_skipped_reason("")),
    }
    thinking_file = (os.environ.get("ARTCB_INGEST_THINKING_FILE") or "").strip()
    if thinking_file and key:
        thinking_ingest["ingest_attempted"] = True
        tp = Path(thinking_file)
        if tp.is_file():
            thinking_ingest = ingest_thinking_file(tp, url=url, api_key=key)
        else:
            thinking_ingest["reason"] = thinking_file_skipped_reason(thinking_file)
            thinking_ingest["ingest_path"] = thinking_file
            thinking_ingest.update(
                empty_thinking_states(reason=thinking_file_skipped_reason(thinking_file))
            )
            thinking_ingest["thinking_available_from_runtime"] = True

    status = {
        "ok": health_code == 200,
        "live_url": url,
        "key_source": source,
        "key_present": bool(key),
        "health_http": health_code,
        "git_sha": health.get("git_sha") if isinstance(health, dict) else None,
        "git_branch": health.get("git_branch") if isinstance(health, dict) else None,
        "pqc": (health.get("pqc") or {}).get("algorithm") if isinstance(health, dict) else None,
        "me_http": me_code,
        "key_id": me.get("key_id") if isinstance(me, dict) else None,
        "scopes": me.get("scopes") if isinstance(me, dict) else None,
        "economics_http": econ_code,
        "protocol_http": proto_code,
        "h_adult": proto.get("h_adult") if isinstance(proto, dict) else None,
        "chain_http": chain_code,
        "ai_memory_http": mem_code,
        "kcg_http": kcg_code,
        "ai_context_http": ctx_code,
        **memory_snap,
        "last_memo_http": last_memo_http,
        "last_memo_content_chars": last_memo_chars,
        "last_memo_content_sha256": last_memo_sha256,
        "ingest": ingest,
        "thinking_ingest": thinking_ingest,
        "token_printed": False,
    }
    write_bootstrap_stamp(
        {
            "bootstrap_ok": health_code == 200 and bool(key) and me_code == 200,
            "node_url": url,
            "node_git_sha": health.get("git_sha") if isinstance(health, dict) else None,
            "node_identity": health.get("service") if isinstance(health, dict) else None,
            "api_key_id": me.get("key_id") if isinstance(me, dict) else None,
            "scopes": me.get("scopes") if isinstance(me, dict) else None,
            **memory_snap,
        }
    )
    print(json.dumps(status, indent=2))
    if health_code != 200:
        return 2
    if not key or me_code != 200:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
