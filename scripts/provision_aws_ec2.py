#!/usr/bin/env python3
"""Provision (or refuse) the AWS EC2 instance for aws-node-3.

Does not launch anything unless AWS credentials can call STS *and* the
caller passes --yes. IAM user node_artcb_3_agent was observed with only
IAMUserChangePassword — RunInstances is denied until an admin attaches
EC2 policies or injects access keys.

Never prints secret values. Never writes secrets into git.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import parse_env_file  # noqa: E402
from artcb.node_registry import NODES, local_env_path  # noqa: E402

REGION = "eu-west-3"
PROFILE = "artcb-node-3"
INSTANCE_TYPE = "t3.large"
UBUNTU_OWNER = "099720109477"


def _aws_env() -> dict[str, str]:
    env = os.environ.copy()
    local = parse_env_file(local_env_path("aws-node-3"))
    if local.get("AWS_ACCESS_KEY_ID") and not env.get("AWS_ACCESS_KEY_ID"):
        env["AWS_ACCESS_KEY_ID"] = local["AWS_ACCESS_KEY_ID"]
        env["AWS_SECRET_ACCESS_KEY"] = local.get("AWS_SECRET_ACCESS_KEY", "")
    env.setdefault("AWS_DEFAULT_REGION", local.get("AWS_DEFAULT_REGION") or REGION)
    env.setdefault("AWS_PROFILE", local.get("AWS_CLI_PROFILE") or PROFILE)
    return env


def _aws(args: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    cmd = ["aws", *args, "--output", "json"]
    if env.get("AWS_PROFILE") and "AWS_ACCESS_KEY_ID" not in os.environ:
        cmd.extend(["--profile", env["AWS_PROFILE"]])
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def diagnose() -> dict[str, Any]:
    env = _aws_env()
    code, out, err = _aws(["sts", "get-caller-identity"], env)
    identity: dict[str, Any] = {}
    if code == 0:
        try:
            identity = json.loads(out)
        except json.JSONDecodeError:
            identity = {"raw": "unparsed"}
    ec2_code, _ec2_out, ec2_err = _aws(
        ["ec2", "describe-instances", "--region", REGION, "--max-items", "1"],
        env,
    )
    spec = NODES["aws-node-3"]
    return {
        "node_id": spec.node_id,
        "doppler_project": spec.doppler_project,
        "region": REGION,
        "instance_type": INSTANCE_TYPE,
        "sts_http_or_exit": code,
        "sts_ok": code == 0,
        "caller_arn": identity.get("Arn"),
        "account": identity.get("Account"),
        "ec2_describe_exit": ec2_code,
        "ec2_allowed": ec2_code == 0,
        "blocker": None
        if code == 0 and ec2_code == 0
        else (
            "IAM user node_artcb_3_agent has IAMUserChangePassword only "
            "(observed 2026-08-31 console: AccessDenied iam:ListAccessKeys, "
            "ec2:DescribeInstanceStatus, no RunInstances). "
            "Admin of account 599128160879 must attach AmazonEC2FullAccess "
            "(or equivalent) plus iam:CreateAccessKey on self, OR inject "
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY into Cursor secrets. "
            "Do not paste console passwords into git."
        ),
        "stderr_tail": ((err or ec2_err) or "")[-300:],
        "secrets_printed": False,
        "launched": False,
    }


def latest_ubuntu_ami(env: dict[str, str]) -> str | None:
    code, out, _err = _aws(
        [
            "ec2",
            "describe-images",
            "--region",
            REGION,
            "--owners",
            UBUNTU_OWNER,
            "--filters",
            "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
            "Name=state,Values=available",
            "--query",
            "sort_by(Images,&CreationDate)[-1].ImageId",
        ],
        env,
    )
    if code != 0:
        return None
    ami = out.strip().strip('"')
    return ami if ami.startswith("ami-") else None


def launch(diag: dict[str, Any]) -> dict[str, Any]:
    env = _aws_env()
    pub = Path.home() / ".ssh" / "artcb_aws_node_3.pub"
    if not pub.is_file():
        return {**diag, "launched": False, "reason": "missing ~/.ssh/artcb_aws_node_3.pub"}
    ami = latest_ubuntu_ami(env)
    if not ami:
        return {**diag, "launched": False, "reason": "ubuntu_ami_not_found"}
    # Import key pair (idempotent-ish)
    _aws(
        ["ec2", "import-key-pair", "--region", REGION, "--key-name", "artcb-aws-node-3", "--public-key-material", f"fileb://{pub}"],
        env,
    )
    user_data = """#!/bin/bash
set -euo pipefail
apt-get update -y
apt-get install -y git curl python3 python3-venv python3-pip build-essential
"""
    code, out, err = _aws(
        [
            "ec2",
            "run-instances",
            "--region",
            REGION,
            "--image-id",
            ami,
            "--instance-type",
            INSTANCE_TYPE,
            "--key-name",
            "artcb-aws-node-3",
            "--count",
            "1",
            "--tag-specifications",
            "ResourceType=instance,Tags=[{Key=Name,Value=node-artcb-3},{Key=artcb-node-id,Value=aws-node-3}]",
            "--user-data",
            user_data,
        ],
        env,
    )
    launched = False
    instance_id = None
    if code == 0:
        try:
            payload = json.loads(out)
            instance_id = ((payload.get("Instances") or [{}])[0]).get("InstanceId")
            launched = bool(instance_id)
        except json.JSONDecodeError:
            launched = False
    diag.update(
        {
            "launched": launched,
            "ami": ami,
            "instance_id": instance_id,
            "run_instances_exit": code,
            "stderr_tail": (err or "")[-300:],
        }
    )
    return diag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="actually call RunInstances if EC2 is allowed")
    args = parser.parse_args()
    diag = diagnose()
    if args.yes and diag.get("ec2_allowed"):
        diag = launch(diag)
    elif args.yes and not diag.get("ec2_allowed"):
        diag["launch_skipped"] = "ec2_denied"
    print(json.dumps(diag, indent=2, sort_keys=True, default=str))
    if diag.get("launched"):
        return 0
    return 0 if diag.get("sts_ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
