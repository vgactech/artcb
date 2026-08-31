"""Deployed binary identity — git SHA/branch for health proofs.

Never logs secrets. Values come from env (systemd/start_node) or `git`.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("artcb.release")

ROOT = Path(__file__).resolve().parents[2]
API_VERSION = "0.3.0"


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _from_release_file() -> tuple[str, str]:
    """Replit Autoscale often has no .git. replit_start.sh writes this file after pull."""
    path = ROOT / ".artcb_release"
    if not path.is_file():
        return "", ""
    sha = ""
    branch = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _, val = line.partition("=")
        if key.strip() == "ARTCB_GIT_SHA":
            sha = val.strip()
        elif key.strip() == "ARTCB_GIT_BRANCH":
            branch = val.strip()
    return sha, branch


def release_identity() -> dict:
    file_sha, file_branch = _from_release_file()
    sha = os.getenv("ARTCB_GIT_SHA", "").strip() or file_sha or _git("rev-parse", "HEAD")
    branch = os.getenv("ARTCB_GIT_BRANCH", "").strip() or file_branch or _git("rev-parse", "--abbrev-ref", "HEAD")
    logger.debug(
        "release identity sha=%s branch=%s",
        (sha[:12] if sha else None),
        branch or None,
    )
    return {
        "git_sha": sha or None,
        "git_branch": branch or None,
        "version": API_VERSION,
    }
