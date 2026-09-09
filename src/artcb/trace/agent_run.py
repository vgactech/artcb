"""Agent execution provenance — hashes and events, not private model thinking.

Chain: H_i = SHA256(event_i || H_{i-1}). Prompt content stays off-chain;
only prompt_hash is recorded. Failures and retries are first-class events.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

POLICY_ID = "284-environment-classification"
POLICY_VERSION = "284.1"
POLICY_RULES = (
    "UNKNOWN!=BARE_METAL;"
    "SOFTWARE_TPM!=L3;"
    "device_present!=HYPERVISOR_VTPM;"
    "NOT_REACHABLE!=CERTIFIED_OK;"
    "NOT_APPLICABLE_excluded_from_denominator;"
    "LOCAL_NONCE!=VERIFIER_CHALLENGE;"
    "PRE_R273_K1_Node2=GAP_not_PASS;"
    "N04_50=FAIL_last"
)


def policy_hash() -> str:
    raw = f"{POLICY_ID}|{POLICY_VERSION}|{POLICY_RULES}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256_bytes(blob)


class AgentRunLedger:
    def __init__(self, *, run_id: str, agent_id: str, prompt_hash: str, code_sha: str) -> None:
        self.run_id = run_id
        self.agent_id = agent_id
        self.prompt_hash = prompt_hash
        self.code_sha = code_sha
        self.prev = "0" * 64
        self.events: list[dict[str, Any]] = []

    def add(
        self,
        action: str,
        *,
        status: str,
        input_hash: str = "",
        output_hash: str = "",
        artifact_hash: str = "",
        detail: dict[str, Any] | None = None,
        actor: str = "AGENT_ACTION",
    ) -> dict[str, Any]:
        body = {
            "event_id": f"{self.run_id}-{len(self.events) + 1:04d}",
            "run_id": self.run_id,
            "parent_event_id": self.events[-1]["event_id"] if self.events else "",
            "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent_id": self.agent_id,
            "actor": actor,
            "action": action,
            "status": status,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "artifact_hash": artifact_hash,
            "code_sha": self.code_sha,
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "policy_hash": policy_hash(),
            "detail": detail or {},
        }
        digest = sha256_json({"event": body, "prev": self.prev})
        body["chain_hash"] = digest
        body["prev_hash"] = self.prev
        self.prev = digest
        self.events.append(body)
        return body

    def write(self, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "prompt_hash": self.prompt_hash,
            "code_sha": self.code_sha,
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "policy_hash": policy_hash(),
            "tip": self.prev,
            "events": self.events,
            "note": (
                "Hashes only. Private model thinking is not recorded. "
                "A missing failure event is itself a provenance gap."
            ),
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload
