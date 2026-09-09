"""R293 — four capture layers. Chat visible ≠ ARTCB stored.

Layer 1: model runtime CoT (ARTCB_INGEST_THINKING_FILE)
Layer 2: Cursor chat / transcript store (MCP transcript.json, AGENT_TRANSCRIPTS)
Layer 3: this VM (env, socket, files)
Layer 4: ARTCB private memo + integrity chain

A Cursor Cloud transcript that *contains* ``thinking`` fields is layer 2.
It does not set thinking_recorded. Ingest hook unset remains NOT_PROVEN.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from artcb.trace.thinking import empty_thinking_states

LAYERS = ("model_runtime", "cursor_interface", "agent_vm", "artcb")


def classify_capture_inventory(
    *,
    ingest_thinking_file: str = "",
    ingest_prompt_file: str = "",
    agent_transcripts_dir: str = "",
    transcripts_dir_exists: bool = False,
    cursor_socket_path: str = "",
    socket_exists: bool = False,
    mcp_transcript_fetched: bool = False,
    mcp_transcript_bytes: int = 0,
    mcp_transcript_sha256: str = "",
    mcp_message_count: int = 0,
    mcp_thinking_field_count: int = 0,
    mcp_thinking_chars: int = 0,
    mcp_contains_secret_like: bool | None = None,
    conversation_id: str = "",
) -> dict[str, Any]:
    ingest_set = bool((ingest_thinking_file or "").strip())
    prompt_set = bool((ingest_prompt_file or "").strip())
    transcripts_set = bool((agent_transcripts_dir or "").strip())
    thinking = empty_thinking_states(
        reason=(
            "ingest_hook_unset"
            if not ingest_set
            else "ingest_path_set_but_not_stored_in_artcb"
        )
    )
    # MCP thinking fields are layer-2 observations, not the ingest hook.
    if mcp_thinking_field_count and not ingest_set:
        thinking["reason"] = (
            "layer2_transcript_has_thinking_fields_but_ingest_hook_unset"
        )
    return {
        "layers": {
            "1_model_runtime": {
                "artcb_ingest_thinking_file_set": ingest_set,
                "status": "NOT_PROVEN" if not ingest_set else "PATH_SET",
            },
            "2_cursor_interface": {
                "mcp_transcript_fetched": bool(mcp_transcript_fetched),
                "mcp_transcript_bytes": int(mcp_transcript_bytes),
                "mcp_transcript_sha256": mcp_transcript_sha256 or "",
                "mcp_message_count": int(mcp_message_count),
                "embedded_thinking_fields": int(mcp_thinking_field_count),
                "embedded_thinking_chars": int(mcp_thinking_chars),
                "status": "OBSERVED_VIA_MCP" if mcp_transcript_fetched else "NOT_PROVEN",
                "note": (
                    "Chat/transcript store. Embedded thinking strings ≠ "
                    "ARTCB_INGEST_THINKING_FILE and ≠ thinking_recorded."
                ),
            },
            "3_agent_vm": {
                "agent_transcripts_env_set": transcripts_set,
                "agent_transcripts_dir_exists": bool(transcripts_dir_exists),
                "cursor_socket_exists": bool(socket_exists),
                "cursor_socket_path_set": bool((cursor_socket_path or "").strip()),
                "conversation_id_set": bool((conversation_id or "").strip()),
                "ingest_prompt_file_set": prompt_set,
                "status": "PARTIAL",
            },
            "4_artcb": {
                "thinking_states": thinking,
                "thinking_recorded": False,
                "status": "NOT_STORED",
            },
        },
        "thinking_recorded": False,
        "thinking_available_from_runtime": False,
        "thinking_received": False,
        "thinking_private_stored": False,
        "thinking_integrity_verified": False,
        "embedded_thinking_fields_observed": bool(mcp_thinking_field_count),
        "chat_visible_neq_artcb_stored": True,
        "mcp_contains_secret_like": mcp_contains_secret_like,
        "certified_100": False,
        "note": (
            "Visible chat or MCP transcript ≠ VM ingest hook ≠ ARTCB private "
            "byte-for-byte store. Do not POST secret-bearing transcripts public."
        ),
    }


def path_exists(raw: str) -> bool:
    p = Path((raw or "").strip())
    return bool(str(p)) and p.exists()
