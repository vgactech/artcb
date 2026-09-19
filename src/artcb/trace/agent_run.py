"""Agent execution provenance — hashes and events, not private model thinking.

Chain: H_i = SHA256(event_i || H_{i-1}). Prompt content stays off-chain;
only prompt_hash is recorded. Failures and retries are first-class events.

R396-B : AgentExecutionRecord — enregistrement structuré d'une session agent.

Règle ARTCB (R396) : FAIL-OPEN EXECUTION, FAIL-CLOSED AUDIT STATUS.
  audit_status = "ok" | "failed" | "incomplete"
  Un audit_status="ok" par défaut sans preuve explicite est interdit.
"""

from __future__ import annotations
MODULE_VERSION = '1.1.0'  # R396-B — AgentExecutionRecord

import hashlib
import json
import time
from dataclasses import dataclass, field
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


# ── R396-B : AgentExecutionRecord ────────────────────────────────────────────

AUDIT_STATUS_OK = "ok"
AUDIT_STATUS_FAILED = "failed"
AUDIT_STATUS_INCOMPLETE = "incomplete"

AGENT_BOB = "bob"
AGENT_CURSOR = "cursor"


@dataclass
class AgentExecutionRecord:
    """Enregistrement structuré d'une session agent (Bob ou Cursor).

    Couvre : démarrage, résultats de tests, feedback auto, statut d'audit.
    Règle R396 : audit_status commence toujours à INCOMPLETE — jamais "ok" par défaut.

    Champs :
        agent_id           : "bob" | "cursor" | autre
        session_id         : identifiant de session agent (opaque)
        task_id            : identifiant de tâche ARTCB (R-nnn, TASK-xxx…)
        repo_sha_before    : HEAD avant la session
        repo_sha_after     : HEAD après commit (peut être identique si pas de commit)
        start_ns           : timestamp wall ns début
        end_ns             : timestamp wall ns fin (0 si non terminé)
        tests_passed       : nb tests pytest PASS
        tests_failed       : nb tests pytest FAIL
        tests_error        : nb tests pytest ERROR
        feedback_status    : "ok" | "failed" | "incomplete" (résultat de R392)
        audit_status       : statut global — JAMAIS "ok" par défaut
        artifact_hash      : SHA-256 hex du principal artefact produit (ou "")
        note               : commentaire libre
    """
    agent_id: str = AGENT_BOB
    session_id: str = ""
    task_id: str = ""
    repo_sha_before: str = ""
    repo_sha_after: str = ""
    start_ns: int = field(default_factory=time.time_ns)
    end_ns: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_error: int = 0
    feedback_status: str = AUDIT_STATUS_INCOMPLETE
    audit_status: str = AUDIT_STATUS_INCOMPLETE  # jamais "ok" par défaut
    artifact_hash: str = ""
    note: str = ""

    def finish(
        self,
        *,
        audit_status: str,
        feedback_status: str = AUDIT_STATUS_INCOMPLETE,
        repo_sha_after: str = "",
        artifact_hash: str = "",
    ) -> None:
        """Marque la session comme terminée avec un audit_status explicite.

        Doit être appelé APRÈS avoir obtenu le résultat de R392 et des tests.
        Ne jamais passer audit_status="ok" sans preuve des tests + feedback.
        """
        self.end_ns = time.time_ns()
        self.audit_status = audit_status
        self.feedback_status = feedback_status
        if repo_sha_after:
            self.repo_sha_after = repo_sha_after
        if artifact_hash:
            self.artifact_hash = artifact_hash

    def to_dict(self) -> dict[str, Any]:
        """Sérialisation complète sans information privée."""
        return {
            "schema": "AgentExecutionRecord/R396-B/v1",
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "repo_sha_before": self.repo_sha_before,
            "repo_sha_after": self.repo_sha_after,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "duration_ms": round((self.end_ns - self.start_ns) / 1_000_000, 3) if self.end_ns else None,
            "tests": {
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "error": self.tests_error,
            },
            "feedback_status": self.feedback_status,
            "audit_status": self.audit_status,
            "artifact_hash": self.artifact_hash,
            "note": self.note,
            "certified_100": False,
        }

    def write(self, trace_dir: Path) -> Path:
        """Écrit l'enregistrement dans trace_dir/agent_execution_records.jsonl (append).

        Retourne le chemin du fichier.
        """
        trace_dir.mkdir(parents=True, exist_ok=True)
        out = trace_dir / "agent_execution_records.jsonl"
        line = json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with out.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return out
