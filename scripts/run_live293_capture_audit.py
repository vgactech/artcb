#!/usr/bin/env python3
"""R293 live capture audit — four layers. Does not dump thinking/chat bodies.

Chat visible ≠ ingest hook ≠ ARTCB stored. MCP transcript thinking fields are
layer 2. ARTCB_INGEST_THINKING_FILE unset remains NOT_PROVEN for layer 1.
Never prints API keys. Never POSTs the transcript (secret-like strings).
CERTIFIED_100=false. N04 last. PRE_R273 GAP kept.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402
from artcb.trace.aep import certify_provenance  # noqa: E402
from artcb.trace.agent_run import (  # noqa: E402
    AEP_POLICY_ID,
    AEP_POLICY_VERSION,
    AgentRunLedger,
    aep_policy_hash,
    sha256_bytes,
)
from artcb.trace.capture_inventory import classify_capture_inventory  # noqa: E402
from artcb.trace.thinking import empty_thinking_states  # noqa: E402

HTTP = l265.HTTP


def _latest_mcp_transcript(bc_id: str) -> Path | None:
    root = Path("/tmp/cursor/cloud-agent-transcripts")
    if not root.is_dir() or not bc_id:
        return None
    hits = sorted(root.glob(f"*/{bc_id}/transcript.json"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def _transcript_meta(path: Path) -> dict:
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    data = json.loads(raw)
    msgs = data.get("messages") if isinstance(data, dict) else data
    n_msgs = len(msgs) if isinstance(msgs, list) else 0
    thinking_n = 0
    thinking_chars = 0
    secret_like = False

    def walk(obj: object, parent_role: str | None = None) -> None:
        nonlocal thinking_n, thinking_chars, secret_like
        if isinstance(obj, dict):
            role = obj.get("role") if isinstance(obj.get("role"), str) else parent_role
            th = obj.get("thinking")
            if isinstance(th, str) and th:
                thinking_n += 1
                thinking_chars += len(th)
                if "artcb_" in th or "BEGIN " in th:
                    secret_like = True
            for v in obj.values():
                if isinstance(v, str) and ("artcb_" in v or "BEGIN PRIVATE" in v):
                    secret_like = True
                walk(v, role if isinstance(role, str) else parent_role)
        elif isinstance(obj, list):
            for x in obj:
                walk(x, parent_role)

    if isinstance(msgs, list):
        for m in msgs:
            walk(m)
    return {
        "bytes": len(raw),
        "sha256": digest,
        "message_count": n_msgs,
        "thinking_fields": thinking_n,
        "thinking_chars": thinking_chars,
        "secret_like": secret_like,
        "path": str(path),
    }


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    health = {nid: l265._http("GET", f"{HTTP[nid]}/health", timeout=12) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (health[nid].get("git_sha") or "")[:40] for nid in OFFICIAL_COMPUTE_NODE_IDS}
    chain = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/chain/status", timeout=12)
    bc = (os.environ.get("CURSOR_CONVERSATION_ID") or "").strip()
    transcripts_env = (os.environ.get("AGENT_TRANSCRIPTS") or "").strip()
    sock = (os.environ.get("CURSOR_AGENT_SOCKET") or "").strip()
    mcp_path = _latest_mcp_transcript(bc)
    meta = _transcript_meta(mcp_path) if mcp_path and mcp_path.is_file() else {}
    inv = classify_capture_inventory(
        ingest_thinking_file=os.environ.get("ARTCB_INGEST_THINKING_FILE") or "",
        ingest_prompt_file=os.environ.get("ARTCB_INGEST_PROMPT_FILE") or "",
        agent_transcripts_dir=transcripts_env,
        transcripts_dir_exists=bool(transcripts_env) and Path(transcripts_env).exists(),
        cursor_socket_path=sock,
        socket_exists=bool(sock) and Path(sock).exists(),
        mcp_transcript_fetched=bool(meta),
        mcp_transcript_bytes=int(meta.get("bytes") or 0),
        mcp_transcript_sha256=str(meta.get("sha256") or ""),
        mcp_message_count=int(meta.get("message_count") or 0),
        mcp_thinking_field_count=int(meta.get("thinking_fields") or 0),
        mcp_thinking_chars=int(meta.get("thinking_chars") or 0),
        mcp_contains_secret_like=bool(meta.get("secret_like")) if meta else None,
        conversation_id=bc,
    )
    thinking = empty_thinking_states(
        reason="layer2_mcp_transcript_observed_ingest_hook_unset"
        if meta
        else "cursor_runtime_did_not_inject_thinking"
    )
    led = AgentRunLedger(
        run_id=f"AR-293-{stamp}",
        agent_id="cursor-cloud-agent",
        prompt_hash=str(meta.get("sha256") or hashlib.sha256(b"").hexdigest()),
        code_sha=shas.get("ovh-node-1") or "",
        policy_id=AEP_POLICY_ID,
        policy_version=AEP_POLICY_VERSION,
        policy_hash_value=aep_policy_hash(),
    )
    led.set_thinking_states(thinking)
    led.add("INPUT_RECEIVED", status="PASS", input_hash=str(meta.get("sha256") or ""), detail={"layer": "audit"})
    led.add(
        "SECRET_LOOKUP",
        status="FAIL",
        detail={"target": "ARTCB_INGEST_THINKING_FILE", "result": "UNSET"},
    )
    led.add(
        "FILE_READ",
        status="FAIL" if not (transcripts_env and Path(transcripts_env).exists()) else "PASS",
        detail={
            "target": "AGENT_TRANSCRIPTS",
            "env_set": bool(transcripts_env),
            "dir_exists": bool(transcripts_env) and Path(transcripts_env).exists(),
        },
    )
    led.add(
        "NETWORK_REQUEST",
        status="PASS" if meta else "SKIP",
        detail={
            "target": "cursor_cloud_mcp_transcript",
            "fetched": bool(meta),
            "bytes": meta.get("bytes"),
            "sha256": meta.get("sha256"),
            "thinking_fields": meta.get("thinking_fields"),
            "body_printed": False,
        },
    )
    led.add(
        "DECISION",
        status="FAIL",
        detail={
            "thinking_recorded": False,
            "chat_visible_neq_stored": True,
            "layer2_mcp": bool(meta),
            "layer1_ingest": False,
        },
    )
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        led.add(
            "LIVE_VERIFICATION",
            status="PASS" if health[nid].get("git_sha") else "FAIL",
            detail={"node_id": nid, "git_sha": shas[nid]},
            actor="SYSTEM_ACTION",
        )
    led.add("FINAL_VERDICT", status="FAIL", detail={"certified_100": False, "thinking_recorded": False})
    exhaustive = certify_provenance(led.events, profile="exhaustive_agent", thinking_states=thinking)
    out = {
        "run_id": led.run_id,
        "inventory": inv,
        "official_shas": shas,
        "ovh1_height": chain.get("height"),
        "ovh1_last_hash": chain.get("last_hash"),
        "thinking_recorded": False,
        "certified_100": False,
        "exhaustive": exhaustive["profile_certification"],
        "mcp_transcript_path_recorded": bool(meta),
        "body_printed": False,
        "posted_to_artcb": False,
        "reason_not_posted": "transcript_may_contain_secrets; live still 05d7030 32k cap; integrity not proven",
    }
    path = ROOT / "logs" / f"293_capture_audit_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = led.write(path)
    payload = {**out, "tip": ledger["tip"], "event_count": len(led.events)}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (ROOT / "logs" / "293_capture_audit_latest.json").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(
        {
            "run_id": led.run_id,
            "thinking_recorded": False,
            "ingest_hook": False,
            "mcp_fetched": bool(meta),
            "mcp_bytes": meta.get("bytes"),
            "mcp_sha256": (meta.get("sha256") or "")[:16],
            "thinking_fields": meta.get("thinking_fields"),
            "agent_transcripts_dir_exists": inv["layers"]["3_agent_vm"]["agent_transcripts_dir_exists"],
            "socket_exists": inv["layers"]["3_agent_vm"]["cursor_socket_exists"],
            "exhaustive": exhaustive["profile_certification"],
            "certified_100": False,
            "official_shas": {k: v[:7] for k, v in shas.items()},
            "height": chain.get("height"),
            "wrote": str(path),
            "posted_to_artcb": False,
        },
        indent=2,
    ))
    if exhaustive["certified_100"] or payload["thinking_recorded"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
