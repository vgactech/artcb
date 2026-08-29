"""Canonical simulation provenance — never invent hashes.

dependency_lock_hash is pip freeze (or requirements.txt), not sys.version+sha.
git_status_clean is False when the working tree has uncommitted changes.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str], cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())


def git_commit_sha() -> str:
    return _run(["git", "rev-parse", "HEAD"]) or os.environ.get("ARTCB_GIT_SHA", "unknown")


def git_branch() -> str:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or os.environ.get(
        "ARTCB_GIT_BRANCH", "unknown"
    )


def git_status_clean() -> bool:
    return _run(["git", "status", "--porcelain"]) == ""


def working_tree_diff_hash() -> str:
    diff = _run(["git", "diff", "HEAD"])
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"])
    material = (diff + "\n--UNTRACKED--\n" + untracked).encode("utf-8", errors="replace")
    return sha256_bytes(material)


def dependency_lock_hash() -> dict[str, Any]:
    """Real dependency provenance: pip freeze if possible, else requirements.txt."""
    freeze = _run([sys.executable, "-m", "pip", "freeze"])
    req = ROOT / "requirements.txt"
    req_hash = sha256_file(req)
    if freeze:
        lines = sorted(
            line.strip()
            for line in freeze.splitlines()
            if line.strip() and not line.startswith("#")
        )
        return {
            "source": "pip_freeze",
            "package_count": len(lines),
            "hash": sha256_bytes("\n".join(lines).encode("utf-8")),
            "requirements_txt_hash": req_hash,
        }
    return {
        "source": "requirements_txt_only",
        "package_count": None,
        "hash": req_hash,
        "requirements_txt_hash": req_hash,
    }


def collect(
    *,
    protocol_version: str,
    economic_rules_version: str,
    simulation_id: str,
    seed: int,
    script_path: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dirty = not git_status_clean()
    out: dict[str, Any] = {
        "git_commit_sha": git_commit_sha(),
        "git_branch": git_branch(),
        "git_status_clean": not dirty,
        "working_tree_diff_hash": working_tree_diff_hash(),
        "script_path": str(script_path.resolve()),
        "script_sha256": sha256_file(script_path),
        "dependency_lock": dependency_lock_hash(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "seed": seed,
        "protocol_version": protocol_version,
        "economic_rules_version": economic_rules_version,
        "simulation_id": simulation_id,
        "started_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "invented_results": False,
        "certified_distributed_mainnet": False,
    }
    if extra:
        out.update(extra)
    return out


def finish(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(manifest)
    manifest["finished_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return manifest


def dumps(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"
