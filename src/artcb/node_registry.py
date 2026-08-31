"""Canonical real-node identities and Doppler project isolation.

One Doppler project per cloud account / real node. Never mix OVH-1, OVH-2, and
AWS-3 credentials in ``artcb-blockchain`` (shared app secrets only).

Public identifiers only. Secrets live in Doppler or ``~/.artcb/nodes/*.env``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

SHARED_DOPPLER_PROJECT = "artcb-blockchain"
SHARED_DOPPLER_CONFIG = "dev"
LOCAL_NODES_DIR = Path.home() / ".artcb" / "nodes"


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    display_name: str
    provider: str
    doppler_project: str
    doppler_config: str = "prd"
    health_http: str | None = None
    api_https: str | None = None
    ssh_host: str | None = None
    ssh_user: str = "ubuntu"
    public_notes: str = ""


# Public map — no secrets.
NODES: dict[str, NodeSpec] = {
    "ovh-node-1": NodeSpec(
        node_id="ovh-node-1",
        display_name="node artcb 1",
        provider="ovh",
        doppler_project="artcb-ovh-node-1",
        health_http="http://152.228.144.34:8000",
        api_https="https://152.228.144.34:8443",
        ssh_host="152.228.144.34",
        ssh_user="ubuntu",
        public_notes=(
            "Existing GRA11 live node at 152.228.144.34. "
            "OKMS named node artcb 1 in eu-west-par (id not stored in git). "
            "SSH key name artcb-cloud-agent-20260819. "
            "OVH API keys currently in Cursor env are a *different* application "
            "than vc491276-ovh / Agent-Autonome node artcb 2."
        ),
    ),
    "ovh-node-2": NodeSpec(
        node_id="ovh-node-2",
        display_name="node artcb 2",
        provider="ovh",
        doppler_project="artcb-ovh-node-2",
        public_notes=(
            "OVH nic vc491276-ovh (vgac4237@gmail.com). "
            "API application: Agent-Autonome node artcb 2. "
            "No public IPv4 registered in this repo until inventory confirms a VM."
        ),
    ),
    "aws-node-3": NodeSpec(
        node_id="aws-node-3",
        display_name="node artcb 3",
        provider="aws",
        doppler_project="artcb-aws-node-3",
        public_notes=(
            "AWS account 599128160879 IAM user node_artcb_3_agent. "
            "Console https://599128160879.signin.aws.amazon.com/console. "
            "CLI profile artcb-node-3. Region default eu-west-3 (Paris) until confirmed. "
            "Browser aws login required — no access keys in this agent yet."
        ),
    ),
}

# Secrets that belong on a node project — never copy Stripe/Bob/GitHub here.
NODE_SECRET_ALLOWLIST = {
    "ovh-node-1": frozenset(
        {
            "OVH_APPLICATION_KEY",
            "OVH_APPLICATION_SECRET",
            "OVH_CONSUMER_KEY",
            "OVH_ENDPOINT",
            "OVH_CLOUD_PROJECT_ID",
            "OVH_SERVER_IP",
            "OVH_SERVER_USER",
            "SSH_PRIVATE_KEY",
            "ARTCB_API_KEY",
            "ARTCB_API_URL",
            "ARTCB_AGENT_KEY_ID",
            "ARTCB_WALLET_PASSPHRASE",
        }
    ),
    "ovh-node-2": frozenset(
        {
            "OVH_APPLICATION_KEY",
            "OVH_APPLICATION_SECRET",
            "OVH_CONSUMER_KEY",
            "OVH_ENDPOINT",
            "OVH_CLOUD_PROJECT_ID",
            "OVH_SERVER_IP",
            "OVH_SERVER_USER",
            "OVH_NIC",
            "SSH_PRIVATE_KEY",
            "ARTCB_API_KEY",
            "ARTCB_API_URL",
        }
    ),
    "aws-node-3": frozenset(
        {
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_ACCOUNT_ID",
            "AWS_DEFAULT_REGION",
            "AWS_IAM_USER",
            "AWS_CONSOLE_URL",
            "ARTCB_API_KEY",
            "ARTCB_API_URL",
        }
    ),
}

SHARED_ONLY_SECRETS = frozenset(
    {
        "KEY_API_STRIPE",
        "BOB_API_KEY",
        "GRADIUM_API_KEY",
        "GITHUB_TOKEN",
        "KAGGLE_KEY",
        "ALCHEMY_API_KEY",
        "INFURA_PROJECT_SECRET",
        "LOOPQA_API_TOKEN",
        "MANUS_API_KEY",
        "NGROK_AUTHTOKEN",
        "NGROK_API_KEY",
    }
)


def get_node(node_id: str) -> NodeSpec:
    if node_id not in NODES:
        raise KeyError(f"unknown ARTCB node_id={node_id!r}")
    return NODES[node_id]


def doppler_project_for(node_id: str) -> str:
    return get_node(node_id).doppler_project


def local_env_path(node_id: str) -> Path:
    return LOCAL_NODES_DIR / f"{node_id}.env"


def public_registry() -> dict[str, Any]:
    return {
        "shared_doppler_project": SHARED_DOPPLER_PROJECT,
        "shared_doppler_config": SHARED_DOPPLER_CONFIG,
        "isolation_rule": "one Doppler project per real node / cloud account",
        "nodes": {
            nid: {
                "display_name": spec.display_name,
                "provider": spec.provider,
                "doppler_project": spec.doppler_project,
                "doppler_config": spec.doppler_config,
                "health_http": spec.health_http,
                "api_https": spec.api_https,
                "ssh_host": spec.ssh_host,
                "ssh_user": spec.ssh_user,
                "notes": spec.public_notes,
            }
            for nid, spec in NODES.items()
        },
        "shared_only_secret_names": sorted(SHARED_ONLY_SECRETS),
    }


def secret_belongs_on_node(node_id: str, name: str) -> bool:
    return name in NODE_SECRET_ALLOWLIST[node_id]


def secret_must_stay_shared(name: str) -> bool:
    return name in SHARED_ONLY_SECRETS
