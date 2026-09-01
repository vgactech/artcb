"""Canonical real-node identities and Doppler project isolation.

One Doppler project per cloud account / real node. Never mix OVH-1, OVH-2,
AWS-3, and OVH-4 credentials in ``artcb-blockchain`` (shared app secrets only).

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
    doppler_config: str = "dev"
    doppler_token_env: str = "DOPPLER_TOKEN"
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
        doppler_project="artcb-blockchain",
        doppler_token_env="DOPPLER_TOKEN",
        health_http="http://152.228.144.34:8000",
        api_https="https://152.228.144.34:8443",
        ssh_host="152.228.144.34",
        ssh_user="ubuntu",
        public_notes=(
            "Existing GRA11 live node at 152.228.144.34. "
            "Dedicated vault artcb-ovh-node-1 was never created (service token "
            "cannot POST /v3/projects). Live token artcb-node-1 stays on shared "
            "artcb-blockchain until a personal Doppler token splits OVH-1 keys. "
            "SSH key name artcb-cloud-agent-20260819."
        ),
    ),
    "ovh-node-2": NodeSpec(
        node_id="ovh-node-2",
        display_name="node artcb 2",
        provider="ovh",
        doppler_project="artcb-2",
        doppler_token_env="KEY_API_ARTCB_DOPPLER_2",
        health_http="http://151.80.107.29:8000",
        api_https="https://151.80.107.29:8443",
        ssh_host="151.80.107.29",
        ssh_user="ubuntu",
        public_notes=(
            "OVH nic vc491276-ovh (vgac4237@gmail.com). "
            "Public Cloud project 1fc10a3fb27d4511a8c7873cd16243f2. "
            "Instance node-artcb-ovh-2 GRA11 d2-8 id 6470522e-1561-4741-9254-5f58b909eeb9 "
            "IPv4 151.80.107.29. Doppler artcb-2. SSH key artcb-ovh-node-2."
        ),
    ),
    "aws-node-3": NodeSpec(
        node_id="aws-node-3",
        display_name="node artcb 3",
        provider="aws",
        doppler_project="artcb3",
        doppler_token_env="KEY_API_ARTCB_DOPPLER_3",
        health_http="http://51.44.222.232:8000",
        api_https="https://51.44.222.232:8443",
        ssh_host="51.44.222.232",
        ssh_user="ubuntu",
        public_notes=(
            "AWS account 599128160879 IAM user node_artcb_3_agent. "
            "Doppler project artcb3 (service token Cursor KEY_API_ARTCB_DOPPLER_3). "
            "CLI profile artcb-node-3. Region eu-west-3 (Paris). "
            "Cursor secret aliases AWS_API_KEY_AGENT_3 / AWS_API_CLI_AGENT_3 map to "
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY. "
            "IAM 2026-08-31 later session: AdministratorAccess + AmazonEC2FullAccess "
            "+ IAMFullAccess + IAMUserChangePassword (earlier probe had ChangePassword only). "
            "EC2 i-085b74abd1aaf04ee public IP 51.44.222.232 (t3.small fallback from t3.large)."
        ),
    ),
    "ovh-node-4": NodeSpec(
        node_id="ovh-node-4",
        display_name="node artcb 4",
        provider="ovh",
        doppler_project="artcb-4",
        doppler_token_env="KEY_API_ARTCB_DOPPLER_4",
        health_http="http://91.134.45.8:8000",
        api_https="https://91.134.45.8:8443",
        ssh_host="91.134.45.8",
        ssh_user="ubuntu",
        public_notes=(
            "OVH nic xy4589-ovh (vgac42@gmail.com). "
            "Public Cloud project 926bb1d6755e4f2c98ae9db06ef44e4f "
            "(description 'node artcb ovh 4'). "
            "Instance node-artcb-ovh-4 id 22dc6a47-5b79-4084-82d7-eabb4f5b2680 "
            "GRA11 d2-8 IPv4 91.134.45.8. Doppler slug artcb-4 "
            "(UI name ARTCB_API_4). SSH key artcb-ovh-node-4. "
            "Never reuse OVH1 152.228.144.34 or OVH2 151.80.107.29 credentials."
        ),
    ),
    "ovh-baremetal-1": NodeSpec(
        node_id="ovh-baremetal-1",
        display_name="node artcb bare metal 1 (pending — no dedicated IP)",
        provider="ovh-baremetal",
        doppler_project="artcb-baremetal-1",
        doppler_token_env="KEY_API_ARTCB_DOPPLER_BAREMETAL",
        health_http=None,
        api_https=None,
        ssh_host=None,
        ssh_user="ubuntu",
        public_notes=(
            "Fifth TEST hardware node (physical server, not an OpenStack VM). "
            "Never reuse ovh-node-1 / 152.228.144.34. Not a genesis rewrite. "
            "2026-09-01 hunt (D-047): no third OVH3 nic keys. The ~10 EUR is "
            "Public Cloud credit on xy4589-ovh (OVH4 project node artcb ovh 4): "
            "credit 263152 available 10.00 EUR (Credit provisionning); "
            "free-trial 263153 available 199.84 EUR. ovhAccount FR prepaid "
            "0.00 EUR on xy4589-ovh and vc491276-ovh. Cloud credit cannot pay "
            "Eco/Kimsufi dedicated. KS-B 25skb012 = 9.99 EUR/month catalog FR; "
            "GRA availability=unavailable; GET /order/cart/.../checkout HTTP 400 "
            "'not available in gra'. Do not charge the OVH4 card. "
            "KEY_API_ARTCB_DOPPLER_3 is AWS artcb3, not OVH. No project artcb-3. "
            "artcb-baremetal-1 pending DOPPLER_PERSONAL_TOKEN. IP still empty."
        ),
    ),
    "replit-node-1": NodeSpec(
        node_id="replit-node-1",
        display_name="node artcb replit (any account)",
        provider="replit",
        doppler_project="artcb-blockchain",
        doppler_token_env="DOPPLER_TOKEN",
        health_http=None,
        api_https=None,
        ssh_host=None,
        ssh_user="runner",
        public_notes=(
            "No hardcoded *.replit.app host. Any Replit Autoscale clone detects "
            "its public URL from REPLIT_DEV_DOMAIN / REPLIT_DOMAINS / REPL_SLUG "
            "and announces itself to the four infrastructure seeds. Stays "
            "bootstrap without wallet / init-node (D-044/D-045) until the "
            "operator chooses otherwise."
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
            "ARTCB_WALLET_PASSPHRASE",
        }
    ),
    "ovh-node-4": frozenset(
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
            "ARTCB_WALLET_PASSPHRASE",
        }
    ),
    "aws-node-3": frozenset(
        {
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_API_KEY_AGENT_3",
            "AWS_API_CLI_AGENT_3",
            "AWS_ACCOUNT_ID",
            "AWS_DEFAULT_REGION",
            "AWS_IAM_USER",
            "AWS_CONSOLE_URL",
            "AWS_CLI_PROFILE",
            "AWS_SERVER_IP",
            "AWS_INSTANCE_ID",
            "ARTCB_API_KEY",
            "ARTCB_API_URL",
            "ARTCB_WALLET_PASSPHRASE",
        }
    ),
    "ovh-baremetal-1": frozenset(
        {
            "OVH3_APPLICATION_KEY",
            "OVH3_APPLICATION_SECRET",
            "OVH3_CONSUMER_KEY",
            "OVH3_NIC",
            "OVH_APPLICATION_KEY",
            "OVH_APPLICATION_SECRET",
            "OVH_CONSUMER_KEY",
            "OVH_ENDPOINT",
            "OVH_NIC",
            "SSH_PRIVATE_KEY",
            "ARTCB_API_KEY",
            "ARTCB_API_URL",
            "ARTCB_WALLET_PASSPHRASE",
        }
    ),
    "replit-node-1": frozenset(
        {
            "ARTCB_API_KEY",
            "ARTCB_API_URL",
            "ARTCB_WALLET_PASSPHRASE",
            "DOPPLER_TOKEN",
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
                "doppler_token_env": spec.doppler_token_env,
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


def doppler_token_env_for(node_id: str) -> str:
    return get_node(node_id).doppler_token_env


def secret_belongs_on_node(node_id: str, name: str) -> bool:
    return name in NODE_SECRET_ALLOWLIST[node_id]


def secret_must_stay_shared(name: str) -> bool:
    return name in SHARED_ONLY_SECRETS
