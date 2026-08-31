"""Phase 172 — AWS EC2 aws-node-3 with Cursor key aliases. No secrets."""

from __future__ import annotations

import re
from pathlib import Path

from artcb.node_registry import NODES, public_registry, secret_belongs_on_node

ROOT = Path(__file__).resolve().parents[1]


def test_aws_notes_record_admin_and_aliases() -> None:
    notes = NODES["aws-node-3"].public_notes
    assert "599128160879" in notes
    assert "eu-west-3" in notes
    assert "AdministratorAccess" in notes
    assert "AWS_API_KEY_AGENT_3" in notes
    assert "IAMUserChangePassword" in notes
    assert NODES["ovh-node-2"].ssh_host == "151.80.107.29"
    assert NODES["ovh-node-1"].ssh_host == "152.228.144.34"
    assert NODES["aws-node-3"].ssh_host == "51.44.222.232"
    assert NODES["aws-node-3"].health_http == "http://51.44.222.232:8000"


def test_aws_alias_secrets_are_allowlisted() -> None:
    assert secret_belongs_on_node("aws-node-3", "AWS_ACCESS_KEY_ID")
    assert secret_belongs_on_node("aws-node-3", "AWS_API_KEY_AGENT_3")
    assert secret_belongs_on_node("aws-node-3", "AWS_API_CLI_AGENT_3")
    assert secret_belongs_on_node("aws-node-3", "ARTCB_WALLET_PASSPHRASE")
    assert not secret_belongs_on_node("aws-node-3", "KEY_API_STRIPE")
    assert not secret_belongs_on_node("aws-node-3", "AWS_CONSOLE_PASSWORD")


def test_provision_script_maps_aliases_and_is_idempotent() -> None:
    src = (ROOT / "scripts" / "provision_aws_ec2.py").read_text(encoding="utf-8")
    assert "AWS_API_KEY_AGENT_3" in src
    assert "AWS_API_CLI_AGENT_3" in src
    assert "existing_instance" in src
    assert "ensure_security_group" in src
    assert "associate-public-ip-address" in src
    blob = str(public_registry())
    assert not re.search(r"artcb_[0-9a-fA-F]{16,}", blob)
    for forbidden in ("nV5Q4z", "AKIAYW7", "ssPu", "dp.st"):
        assert forbidden not in blob
        assert forbidden not in src


def test_deploy_aws_does_not_touch_ovh1() -> None:
    body = (ROOT / "scripts" / "deploy_aws.sh").read_text(encoding="utf-8")
    assert "152.228.144.34 n'a PAS été modifié" in body
    assert "aws-node-3" in body
    assert "artcb3" in body
    assert "Ne crée PAS de VM OVH 2" in body
    assert "deploy_ovh.sh" not in body
