"""Shared pytest fixtures.

R396-C : hook forensic nanoseconde pour pytest.
  Chaque test PASS/FAIL/ERROR émet un événement dans data/trace/pytest_trace.jsonl.
  Format : {"kind":"pytest_result","ts_ns":...,"test_id":...,"outcome":...,"dur_ns":...,"commit_sha":...}

  Règle ARTCB : production runtime ≠ CI — les deux doivent être traçables.
  Le hook est fail-open : un échec du logging ne bloque pas les tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from artcb.config import load_settings

TEST_WALLET_PASSPHRASE = "test-passphrase-artcb-dev-32chars!"


# Adresse de nœud fictive pour les tests — format artcb1 requis.
# ARTCB_NODE_WALLET_ADDRESS est obligatoire : le nœud refuse de démarrer sans elle.
TEST_NODE_WALLET_ADDRESS = "artcb1testnode000000000000000000000000000"


@pytest.fixture(autouse=True)
def _clear_replica_registry() -> None:
    """Identity binding override must not leak between tests."""
    from src.artcb.consensus.replica_identity import clear_test_replica_registry

    clear_test_replica_registry()
    yield
    clear_test_replica_registry()


@pytest.fixture(autouse=True)
def _wallet_passphrase_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """All tests use encrypted wallets — ARTCB_WALLET_PASSPHRASE required.

    ARTCB_DATA_DIR is redirected to a per-test tmp_path so that create_app()
    and build_app_state() never touch production keys in ./data/chain/.
    ARTCB_NODE_WALLET_ADDRESS is required (no fallback to anonymous node_uuid).
    """
    monkeypatch.setenv("ARTCB_WALLET_PASSPHRASE", TEST_WALLET_PASSPHRASE)
    monkeypatch.setenv("ARTCB_PQC_ENABLED", "true")
    monkeypatch.setenv("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARTCB_NODE_WALLET_ADDRESS", TEST_NODE_WALLET_ADDRESS)
    monkeypatch.setenv("ARTCB_ALLOW_LOCAL_PEERS", "1")
    monkeypatch.setenv("ARTCB_SKIP_SEED_DISCOVERY", "1")
    monkeypatch.setenv("ARTCB_SKIP_CLOUD_METADATA", "1")


@pytest.fixture
def book_pdf_path() -> Path:
    """Wailly demo PDF — skip tests if missing."""
    path = load_settings().demo_book_pdf
    if not path.is_file():
        pytest.skip(f"Book PDF not found: {path}")
    return path


def pytest_configure(config) -> None:
    """R310 — before test module imports pull in api.main eager app.
    Force non-bootstrap + isolated defaults early; per-test tmp_path still wins later.
    """
    os.environ.setdefault("ARTCB_BOOTSTRAP_NODE", "false")
    os.environ.setdefault("ARTCB_SKIP_SEED_DISCOVERY", "1")
    os.environ.setdefault("ARTCB_SKIP_CLOUD_METADATA", "1")
    os.environ.setdefault("ARTCB_ALLOW_LOCAL_PEERS", "1")


# ── R396-C : Forensic trace pytest → data/trace/pytest_trace.jsonl ───────────

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYTEST_TRACE = _REPO_ROOT / "data" / "trace" / "pytest_trace.jsonl"
_COMMIT_SHA: str | None = None


def _get_commit_sha() -> str:
    """Retourne le SHA court HEAD (mise en cache pour toute la session pytest)."""
    global _COMMIT_SHA
    if _COMMIT_SHA is None:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=str(_REPO_ROOT),
            )
            _COMMIT_SHA = r.stdout.strip() or "unknown"
        except Exception:
            _COMMIT_SHA = "unknown"
    return _COMMIT_SHA


def _emit_pytest_trace(row: dict) -> None:
    """Écrit une ligne JSONL dans data/trace/pytest_trace.jsonl — fail-open."""
    try:
        _PYTEST_TRACE.parent.mkdir(parents=True, exist_ok=True)
        with _PYTEST_TRACE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass  # ne jamais bloquer les tests


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """R396-C — émet un événement nanoseconde à la fin de chaque test (call phase)."""
    t_start = time.time_ns()
    outcome = yield
    if call.when != "call":
        return
    t_end = time.time_ns()
    rep = outcome.get_result()
    _emit_pytest_trace({
        "kind": "pytest_result",
        "ts_ns": t_start,
        "end_ns": t_end,
        "dur_ns": t_end - t_start,
        "test_id": item.nodeid,
        "outcome": rep.outcome,  # "passed" | "failed" | "error"
        "commit_sha": _get_commit_sha(),
        "worker_id": os.environ.get("PYTEST_XDIST_WORKER", "main"),
    })

