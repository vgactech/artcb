"""R293 — chat visible ≠ thinking recorded; four capture layers."""

from __future__ import annotations

from artcb.trace.capture_inventory import classify_capture_inventory
from artcb.trace.thinking import derive_thinking_recorded


def test_mcp_transcript_with_thinking_fields_is_not_thinking_recorded() -> None:
    inv = classify_capture_inventory(
        ingest_thinking_file="",
        agent_transcripts_dir="/home/ubuntu/.cursor/projects/workspace/agent-transcripts",
        transcripts_dir_exists=False,
        cursor_socket_path="/run/cursor/api.sock",
        socket_exists=True,
        mcp_transcript_fetched=True,
        mcp_transcript_bytes=30_650_605,
        mcp_transcript_sha256="ab" * 32,
        mcp_message_count=14248,
        mcp_thinking_field_count=2500,
        mcp_thinking_chars=1_807_778,
        mcp_contains_secret_like=True,
        conversation_id="bc-test",
    )
    assert inv["thinking_recorded"] is False
    assert inv["thinking_available_from_runtime"] is False
    assert inv["thinking_received"] is False
    assert inv["thinking_integrity_verified"] is False
    assert inv["embedded_thinking_fields_observed"] is True
    assert inv["chat_visible_neq_artcb_stored"] is True
    assert inv["layers"]["1_model_runtime"]["status"] == "NOT_PROVEN"
    assert inv["layers"]["2_cursor_interface"]["status"] == "OBSERVED_VIA_MCP"
    assert inv["layers"]["3_agent_vm"]["agent_transcripts_dir_exists"] is False
    assert inv["layers"]["4_artcb"]["status"] == "NOT_STORED"
    assert inv["certified_100"] is False
    assert derive_thinking_recorded(inv["layers"]["4_artcb"]["thinking_states"]) is False


def test_env_path_without_directory_is_not_capture() -> None:
    inv = classify_capture_inventory(
        agent_transcripts_dir="/no/such/transcripts",
        transcripts_dir_exists=False,
    )
    assert inv["layers"]["3_agent_vm"]["agent_transcripts_env_set"] is True
    assert inv["layers"]["3_agent_vm"]["agent_transcripts_dir_exists"] is False
    assert inv["thinking_recorded"] is False


def test_ingest_hook_unset_keeps_layer1_not_proven() -> None:
    inv = classify_capture_inventory()
    assert inv["layers"]["1_model_runtime"]["artcb_ingest_thinking_file_set"] is False
    assert inv["layers"]["1_model_runtime"]["status"] == "NOT_PROVEN"
    assert inv["embedded_thinking_fields_observed"] is False
