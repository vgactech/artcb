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


def release_identity() -> dict:
    sha = os.getenv("ARTCB_GIT_SHA", "").strip() or _git("rev-parse", "HEAD")
    branch = os.getenv("ARTCB_GIT_BRANCH", "").strip() or _git("rev-parse", "--abbrev-ref", "HEAD")
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
