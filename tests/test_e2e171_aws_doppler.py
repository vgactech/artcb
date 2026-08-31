"""Phase 171 — bind real Doppler slugs artcb-2 / artcb3; AWS IAM gate. No secrets."""

from __future__ import annotations

import re

import pytest

from artcb.live import resolve_doppler_project, resolve_doppler_token, resolve_doppler_config
from artcb.node_registry import (
    NODES,
    SHARED_DOPPLER_PROJECT,
    SHARED_ONLY_SECRETS,
    doppler_project_for,
    doppler_token_env_for,
    public_registry,
    secret_belongs_on_node,
    secret_must_stay_shared,
)


def test_user_created_doppler_slugs_are_isolated() -> None:
    assert doppler_project_for("ovh-node-2") == "artcb-2"
    assert doppler_project_for("aws-node-3") == "artcb3"
    assert NODES["ovh-node-2"].doppler_project != NODES["aws-node-3"].doppler_project
    assert NODES["ovh-node-2"].doppler_project != SHARED_DOPPLER_PROJECT
    assert NODES["aws-node-3"].doppler_project != SHARED_DOPPLER_PROJECT
    # OVH1 dedicated vault still pending — live token remains on shared project.
    assert doppler_project_for("ovh-node-1") == SHARED_DOPPLER_PROJECT


def test_per_node_service_token_env_names() -> None:
    assert doppler_token_env_for("ovh-node-2") == "KEY_API_ARTCB_DOPPLER_2"
    assert doppler_token_env_for("aws-node-3") == "KEY_API_ARTCB_DOPPLER_3"
    assert doppler_token_env_for("ovh-node-1") == "DOPPLER_TOKEN"
    assert NODES["ovh-node-2"].doppler_config == "dev"
    assert NODES["aws-node-3"].doppler_config == "dev"


def test_stripe_stays_off_node_vaults() -> None:
    assert secret_must_stay_shared("KEY_API_STRIPE")
    assert not secret_belongs_on_node("ovh-node-2", "KEY_API_STRIPE")
    assert not secret_belongs_on_node("aws-node-3", "BOB_API_KEY")
    assert secret_belongs_on_node("ovh-node-2", "OVH_CONSUMER_KEY")
    assert secret_belongs_on_node("aws-node-3", "AWS_ACCESS_KEY_ID")
    assert "AWS_CONSOLE_PASSWORD" not in SHARED_ONLY_SECRETS
    assert "AWS_CONSOLE_PASSWORD" not in NODES["aws-node-3"].__dataclass_fields__


def test_resolve_uses_real_slugs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOPPLER_PROJECT", raising=False)
    monkeypatch.setenv("ARTCB_NODE_ID", "ovh-node-2")
    assert resolve_doppler_project() == "artcb-2"
    assert resolve_doppler_config() == "dev"
    monkeypatch.setenv("ARTCB_NODE_ID", "aws-node-3")
    assert resolve_doppler_project() == "artcb3"
    monkeypatch.setenv("KEY_API_ARTCB_DOPPLER_3", "dp.st.test-token-not-real")
    assert resolve_doppler_token() == "dp.st.test-token-not-real"


def test_ovh2_still_has_no_ssh_host() -> None:
    assert NODES["ovh-node-2"].ssh_host == "151.80.107.29"
    assert "vc491276-ovh" in NODES["ovh-node-2"].public_notes
    assert NODES["ovh-node-1"].ssh_host == "152.228.144.34"
    assert "IAMUserChangePassword" in NODES["aws-node-3"].public_notes


def test_public_registry_has_no_secrets() -> None:
    blob = str(public_registry())
    assert not re.search(r"artcb_[0-9a-fA-F]{16,}", blob)
    assert "BEGIN" not in blob
    for forbidden in ("nV5Q4z", "7255a8ad", "8a226e45", "dp.st"):
        assert forbidden not in blob
    assert "artcb-2" in blob
    assert "artcb3" in blob
