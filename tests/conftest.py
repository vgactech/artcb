"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from artcb.config import load_settings

TEST_WALLET_PASSPHRASE = "test-passphrase-artcb-dev-32chars!"


# Adresse de nœud fictive pour les tests — format artcb1 requis.
# ARTCB_NODE_WALLET_ADDRESS est obligatoire : le nœud refuse de démarrer sans elle.
TEST_NODE_WALLET_ADDRESS = "artcb1testnode000000000000000000000000000"


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
