"""ARTCB Agent Execution Provenance (AEP) — operational events, not private thinking.

R284 AgentRunLedger is a hash-chain *summary*. Exhaustive Cursor/ChatGPT/Claude
tool traces are NOT_PROVEN until those runtimes emit events. A Python probe
can still be COMPLETE_FOR_PROFILE (e.g. mac_ssh_probe) while SSH itself FAILs.
CERTIFIED_100 stays false.
"""

from __future__ import annotations

from typing import Any

from artcb.trace.agent_run import sha256_bytes, sha256_json

# Operational catalog. THINKING_RECEIVED = private-lane lossless body (hash on
# the public ledger). The thinking bytes themselves are visibility=private.
EVENT_CATALOG: frozenset[str] = frozenset(
    {
        "INPUT_RECEIVED",
        "CONTEXT_RECEIVED",
        "PLAN_CREATED",
        "FILE_READ",
        "FILE_WRITE",
        "GITHUB_READ",
        "GITHUB_PATCH",
        "COMMAND_EXECUTED",
        "NETWORK_REQUEST",
        "SSH_ATTEMPT",
        "SSH_PREPARATION",
        "SECRET_LOOKUP",
        "DOPPLER_READ",
        "DOPPLER_KEY_CHECK",
        "TOOL_CALL",
        "TOOL_RESULT",
        "THINKING_RECEIVED",
        "TEST_STARTED",
        "TEST_RESULT",
        "TEST_EXECUTED",
        "ERROR",
        "RETRY",
        "RETRY_EXHAUSTED",
        "DECISION",
        "ARTCB_SEND",
        "ARTCB_RECEIVE",
        "ARTCB_PROCESSING",
        "ARTCB_QUERY",
        "ARTCB_MEMORY_READ",
        "ARTCB_MEMORY_WRITE",
        "ARTCB_CONNECTION",
        "ARTIFACT_CREATED",
        "PATCH_CREATED",
        "GIT_COMMIT",
        "DEPLOYMENT",
        "LIVE_VERIFICATION",
        "ENVIRONMENT_START",
        "ENVIRONMENT_CHANGED",
        "ENVIRONMENT_END",
        "ROLLBACK",
        "UNTRACED_ACTION",
        "FINAL_VERDICT",
    }
)

# Exhaustive Cursor-session profile — never complete from a Python probe alone.
EXHAUSTIVE_REQUIRED: tuple[str, ...] = (
    "INPUT_RECEIVED",
    "PLAN_CREATED",
    "TOOL_CALL",
    "COMMAND_EXECUTED",
    "FILE_READ",
    "FILE_WRITE",
    "ARTCB_SEND",
    "ARTCB_RECEIVE",
    "FINAL_VERDICT",
)

MAC_SSH_REQUIRED: tuple[str, ...] = (
    "INPUT_RECEIVED",
    "ENVIRONMENT_START",
    "SECRET_LOOKUP",
    "DOPPLER_READ",
    "DOPPLER_KEY_CHECK",
    "SSH_PREPARATION",
    "NETWORK_REQUEST",
    "DECISION",
    "ENVIRONMENT_END",
    "FINAL_VERDICT",
)

R284_SUMMARY_REQUIRED: tuple[str, ...] = (
    "INPUT_RECEIVED",
    "LIVE_VERIFICATION",
    "FINAL_VERDICT",
)

PROFILES: dict[str, tuple[str, ...]] = {
    "mac_ssh_probe": MAC_SSH_REQUIRED,
    "r284_classify_summary": R284_SUMMARY_REQUIRED,
    "exhaustive_agent": EXHAUSTIVE_REQUIRED,
}


def lossless_input(
    raw: bytes,
    *,
    truncated: bool = False,
    transformation_id: str = "",
    transformed: bytes | None = None,
) -> dict[str, Any]:
    """LOSSLESS_INPUT_POLICY: no silent truncation / paraphrase."""
    if truncated and not transformation_id:
        return {
            "ok": False,
            "reason": "silent_truncation",
            "raw_hash": sha256_bytes(raw),
            "raw_bytes": len(raw),
            "truncated": True,
        }
    out: dict[str, Any] = {
        "ok": True,
        "reason": "raw" if not transformation_id else "declared_transform",
        "raw_hash": sha256_bytes(raw),
        "raw_bytes": len(raw),
        "truncated": truncated,
        "transformation_id": transformation_id or "",
        "thinking_included": False,
    }
    if transformed is not None:
        out["transformed_hash"] = sha256_bytes(transformed)
        out["transformed_bytes"] = len(transformed)
    return out


def verify_hash_chain(events: list[dict[str, Any]]) -> bool:
    prev = "0" * 64
    for ev in events:
        if (ev.get("prev_hash") or "") != prev:
            return False
        body = {k: v for k, v in ev.items() if k not in {"chain_hash", "prev_hash"}}
        digest = sha256_json({"event": body, "prev": prev})
        if digest != ev.get("chain_hash"):
            return False
        prev = digest
    return True


def _actions(events: list[dict[str, Any]]) -> list[str]:
    return [str(ev.get("action") or "") for ev in events]


def _failed_without_status(events: list[dict[str, Any]]) -> list[str]:
    """A failed operational step must carry FAIL/ERROR/TIMEOUT status — not PASS."""
    gaps = []
    for ev in events:
        action = str(ev.get("action") or "")
        status = str(ev.get("status") or "")
        if action in {"NETWORK_REQUEST", "SSH_ATTEMPT", "SECRET_LOOKUP", "DOPPLER_READ"} and status == "PASS":
            detail = ev.get("detail") or {}
            if str(detail.get("result") or "").upper() in {"TIMEOUT", "ABSENT", "HTTP_400", "NOT_FOUND", "FAIL"}:
                gaps.append(ev.get("event_id") or action)
        if action == "SSH_ATTEMPT" and status not in {"PASS", "FAIL", "TIMEOUT", "ERROR", "SKIP"}:
            gaps.append(ev.get("event_id") or action)
    return gaps


def certify_provenance(
    events: list[dict[str, Any]],
    *,
    profile: str,
    thinking_recorded: bool = False,
    cursor_runtime_instrumented: bool = False,
    lossless_ok: bool = True,
) -> dict[str, Any]:
    required = PROFILES.get(profile) or EXHAUSTIVE_REQUIRED
    actions = _actions(events)
    missing = [name for name in required if name not in actions]
    chain_ok = verify_hash_chain(events) if events else False
    failure_gaps = _failed_without_status(events)
    has_input = "INPUT_RECEIVED" in actions
    has_verdict = "FINAL_VERDICT" in actions
    trace_complete = (
        not missing
        and chain_ok
        and not failure_gaps
        and has_input
        and has_verdict
        and lossless_ok
        and not thinking_recorded
    )
    if profile == "exhaustive_agent":
        trace_complete = False  # never claimed from this layer alone
        missing = list(dict.fromkeys(list(missing) + ["CURSOR_RUNTIME_HOOK"]))
    if profile == "r284_classify_summary" and not missing:
        # Summary profile can be complete *as a summary* — exhaustive is still PARTIAL.
        profile_cert = "COMPLETE_FOR_SUMMARY"
    elif trace_complete:
        profile_cert = "COMPLETE_FOR_PROFILE"
    elif has_input and has_verdict and chain_ok:
        profile_cert = "PARTIAL"
    else:
        profile_cert = "NOT_PROVEN"

    e2e = "NOT_PROVEN"
    return {
        "profile": profile,
        "profile_certification": profile_cert,
        "execution_trace_complete": bool(trace_complete and profile != "exhaustive_agent"),
        "tool_trace_complete": False,
        "cursor_runtime_instrumented": bool(cursor_runtime_instrumented),
        "thinking_recorded": False,
        "chain_ok": chain_ok,
        "missing_events": missing,
        "failure_status_gaps": failure_gaps,
        "event_count": len(events),
        "artcb_send_verified": "ARTCB_SEND" in actions and "ARTCB_RECEIVE" in actions,
        "e2e_agent_artcb": e2e,
        "certified_100": False,
        "ssh_outcome_separate": True,
        "note": (
            "SSH FAIL may coexist with COMPLETE_FOR_PROFILE. "
            "R284 six-event logs remain PARTIAL for exhaustive provenance. "
            "Private thinking is not recorded."
        ),
    }
