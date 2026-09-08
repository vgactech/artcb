"""Primary campaign artefacts — a report is not the proof.

Each campaign writes:
    campaign/<id>/
      manifest.json
      environment.json
      node-<id>/{health,pbft,trace,network}.json
    and SHA256(manifest).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def campaign_root(repo: Path, campaign_id: str) -> Path:
    return Path(repo) / "logs" / "campaigns" / campaign_id


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_attempts() -> list[dict[str, Any]]:
    return []


def record_attempt(
    attempts: list[dict[str, Any]],
    *,
    result: str,
    reason: str = "",
    recovery: str = "",
) -> dict[str, Any]:
    row = {
        "attempt": len(attempts) + 1,
        "result": result,
        "reason": reason,
        "recovery": recovery,
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    attempts.append(row)
    return row


def final_status_from_attempts(attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return "NOT_RUN"
    last = attempts[-1]
    if last.get("result") == "PASS" and any(a.get("result") == "FAIL" for a in attempts[:-1]):
        return "PASS_AFTER_RECOVERY"
    if last.get("result") == "PASS":
        return "PASS"
    return str(last.get("result") or "FAIL")


def write_campaign(
    repo: Path,
    *,
    campaign_id: str,
    code_sha: str,
    runner: str,
    environment: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    results: dict[str, Any],
    extra_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = campaign_root(repo, campaign_id)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "environment.json", environment)
    for nid, files in nodes.items():
        node_dir = root / nid
        node_dir.mkdir(parents=True, exist_ok=True)
        for name, payload in files.items():
            if not name.endswith(".json") and not name.endswith(".jsonl"):
                name = f"{name}.json"
            if isinstance(payload, str):
                (node_dir / name).write_text(payload if payload.endswith("\n") else payload + "\n", encoding="utf-8")
            else:
                write_json(node_dir / name, payload if isinstance(payload, dict) else {"value": payload})
    manifest = {
        "campaign_id": campaign_id,
        "code_sha": code_sha,
        "runner": runner,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "node_ids": sorted(nodes),
        "results": results,
        **(extra_manifest or {}),
    }
    man_path = root / "manifest.json"
    write_json(man_path, manifest)
    digest = sha256_file(man_path)
    (root / "MANIFEST.sha256").write_text(digest + "\n", encoding="utf-8")
    return {"root": str(root), "manifest_sha256": digest, "manifest": manifest}
