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


def _same_commit(a: str, b: str) -> bool:
    """Abbreviated and full SHAs of the same commit count as a match."""
    left, right = a.lower(), b.lower()
    n = min(len(left), len(right))
    return n >= 7 and left[:n] == right[:n]


def _is_ancestor(pin: str, tip: str) -> bool:
    """True if pin is an ancestor of tip (fast-forward allowed). Never logs pin."""
    if not pin or not tip:
        return False
    if _same_commit(pin, tip):
        return True
    try:
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", pin, tip],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _release_integrity(advertised: str, sources: list[str], pin: str) -> str:
    if not advertised:
        return "unknown"
    for item in sources:
        if not _same_commit(advertised, item):
            return "source_mismatch"
    if pin and not _same_commit(advertised, pin) and not _is_ancestor(pin, advertised):
        return "pin_mismatch"
    return "ok"


def release_identity() -> dict:
    file_sha, file_branch = _from_release_file()
    env_sha = os.getenv("ARTCB_GIT_SHA", "").strip()
    git_sha = _git("rev-parse", "HEAD")
    sha = env_sha or file_sha or git_sha
    branch = (
        os.getenv("ARTCB_GIT_BRANCH", "").strip()
        or file_branch
        or _git("rev-parse", "--abbrev-ref", "HEAD")
    )
    pin = os.getenv("ARTCB_REPLIT_PIN_SHA", "").strip()
    sources = [item for item in (env_sha, file_sha, git_sha) if item]
    integrity = _release_integrity(sha, sources, pin)
    logger.debug(
        "release identity sha=%s branch=%s integrity=%s pin_set=%s",
        (sha[:12] if sha else None),
        branch or None,
        integrity,
        bool(pin),
    )
    return {
        "git_sha": sha or None,
        "git_branch": branch or None,
        "version": API_VERSION,
        "release_integrity": integrity,
        "pin_sha": pin or None,
    }
