"""Phase 170 — Doppler/node isolation. No secrets, no invented live SHA."""

from __future__ import annotations

from pathlib import Path

import pytest

from artcb.live import resolve_api_url, resolve_doppler_project
from artcb.node_registry import (
    NODES,
    SHARED_DOPPLER_PROJECT,
    SHARED_ONLY_SECRETS,
    doppler_project_for,
    public_registry,
    secret_belongs_on_node,
    secret_must_stay_shared,
)


def test_three_isolated_doppler_projects() -> None:
    projects = {spec.doppler_project for spec in NODES.values()}
    assert projects == {
        "artcb-ovh-node-1",
        "artcb-ovh-node-2",
        "artcb-aws-node-3",
    }
    assert SHARED_DOPPLER_PROJECT not in projects
    assert len(projects) == 3


def test_stripe_and_bob_stay_shared() -> None:
    assert secret_must_stay_shared("KEY_API_STRIPE")
    assert secret_must_stay_shared("BOB_API_KEY")
    assert not secret_belongs_on_node("ovh-node-2", "KEY_API_STRIPE")
    assert not secret_belongs_on_node("aws-node-3", "GITHUB_TOKEN")
    assert secret_belongs_on_node("ovh-node-2", "OVH_APPLICATION_SECRET")
    assert secret_belongs_on_node("aws-node-3", "AWS_ACCESS_KEY_ID")
    assert "AWS_CONSOLE_PASSWORD" not in SHARED_ONLY_SECRETS


def test_ovh1_public_identity_unchanged() -> None:
    n1 = NODES["ovh-node-1"]
    assert n1.ssh_host == "152.228.144.34"
    assert n1.api_https == "https://152.228.144.34:8443"
    n2 = NODES["ovh-node-2"]
    assert n2.ssh_host is None
    assert "vc491276-ovh" in n2.public_notes


def test_resolve_doppler_project_by_node_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOPPLER_PROJECT", raising=False)
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-2")
    assert resolve_doppler_project() == "artcb-ovh-node-2"
    monkeypatch.setenv("ARTCB_NODE_ID", "aws-node-3")
    assert resolve_doppler_project() == "artcb-aws-node-3"
    monkeypatch.setenv("DOPPLER_PROJECT", "artcb-blockchain")
    assert resolve_doppler_project() == "artcb-blockchain"


def test_default_live_url_is_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARTCB_API_URL", raising=False)
    monkeypatch.delenv("ARTCB_NODE_URL", raising=False)
    assert resolve_api_url() == "https://152.228.144.34:8443"


def test_public_registry_has_no_secret_values() -> None:
    blob = str(public_registry())
    import re

    assert not re.search(r"artcb_[0-9a-fA-F]{16,}", blob)
    assert "BEGIN" not in blob
    for forbidden in ("nV5Q4z", "7255a8ad", "8a226e45"):
        assert forbidden not in blob
    assert doppler_project_for("ovh-node-1") == "artcb-ovh-node-1"
