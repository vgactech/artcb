#!/usr/bin/env python3
"""Provision (or reuse) the AWS EC2 instance for aws-node-3.

Maps Cursor secret aliases AWS_API_KEY_AGENT_3 / AWS_API_CLI_AGENT_3 onto
standard AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY. Never prints secret values.
Never writes secrets into git.

Does not launch unless STS+EC2 describe succeed AND the caller passes --yes.
Idempotent: a running/pending instance tagged artcb-node-id=aws-node-3 is reused.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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
FALLBACK_TYPES = ("t3.medium", "t3.small")
UBUNTU_OWNER = "099720109477"
KEY_NAME = "artcb-aws-node-3"
SG_NAME = "artcb-aws-node-3-sg"
TAG_NODE = "aws-node-3"


def _apply_cursor_aliases(env: dict[str, str]) -> None:
    if not env.get("AWS_ACCESS_KEY_ID"):
        alias = (env.get("AWS_API_KEY_AGENT_3") or "").strip()
        if alias:
            env["AWS_ACCESS_KEY_ID"] = alias
    if not env.get("AWS_SECRET_ACCESS_KEY"):
        alias = (env.get("AWS_API_CLI_AGENT_3") or "").strip()
        if alias:
            env["AWS_SECRET_ACCESS_KEY"] = alias


def _aws_env() -> dict[str, str]:
    env = os.environ.copy()
    local = parse_env_file(local_env_path("aws-node-3"))
    for key, val in local.items():
        if val and not env.get(key):
            env[key] = val
    _apply_cursor_aliases(env)
    env.setdefault("AWS_DEFAULT_REGION", local.get("AWS_DEFAULT_REGION") or REGION)
    env.setdefault("AWS_PROFILE", local.get("AWS_CLI_PROFILE") or PROFILE)
    return env


def _aws(args: list[str], env: dict[str, str], timeout: int = 60) -> tuple[int, str, str]:
    cmd = ["aws", *args]
    if "--output" not in args:
        cmd.extend(["--output", "json"])
    has_keys = bool(env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"))
    if env.get("AWS_PROFILE") and not has_keys:
        cmd.extend(["--profile", env["AWS_PROFILE"]])
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _json(out: str) -> Any:
    try:
        return json.loads(out) if out.strip() else None
    except json.JSONDecodeError:
        return None


def _tail(err: str, n: int = 400) -> str:
    return (err or "")[-n:]


def diagnose() -> dict[str, Any]:
    env = _aws_env()
    code, out, err = _aws(["sts", "get-caller-identity"], env)
    identity: dict[str, Any] = _json(out) if code == 0 else {}
    if not isinstance(identity, dict):
        identity = {}
    ec2_code, _ec2_out, ec2_err = _aws(
        ["ec2", "describe-instances", "--region", REGION, "--max-items", "1"],
        env,
    )
    spec = NODES["aws-node-3"]
    sts_ok = code == 0
    ec2_ok = ec2_code == 0
    blocker = None
    if not sts_ok or not ec2_ok:
        blocker = (
            "STS or EC2 describe failed. Need AWS_ACCESS_KEY_ID (or Cursor "
            "AWS_API_KEY_AGENT_3) plus matching secret, and EC2 policies on "
            "node_artcb_3_agent. Do not paste console passwords into git."
        )
    return {
        "node_id": spec.node_id,
        "doppler_project": spec.doppler_project,
        "region": REGION,
        "instance_type": INSTANCE_TYPE,
        "sts_http_or_exit": code,
        "sts_ok": sts_ok,
        "caller_arn": identity.get("Arn"),
        "account": identity.get("Account"),
        "ec2_describe_exit": ec2_code,
        "ec2_allowed": ec2_ok,
        "has_access_key": bool(env.get("AWS_ACCESS_KEY_ID")),
        "credential_alias_used": bool(
            os.environ.get("AWS_API_KEY_AGENT_3") or parse_env_file(local_env_path("aws-node-3")).get("AWS_ACCESS_KEY_ID")
        ),
        "blocker": blocker,
        "stderr_tail": _tail(err or ec2_err),
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


def ensure_ssh_pubkey() -> Path | None:
    home_pub = Path.home() / ".ssh" / "artcb_aws_node_3.pub"
    repo_pub = ROOT / "deploy" / "artcb_aws_node_3.pub"
    priv = Path.home() / ".ssh" / "artcb_aws_node_3"
    if not priv.is_file() or not home_pub.is_file():
        Path.home().joinpath(".ssh").mkdir(mode=0o700, exist_ok=True)
        proc = subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(priv),
                "-N",
                "",
                "-C",
                "artcb-aws-node-3",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        priv.chmod(0o600)
    if home_pub.is_file():
        repo_pub.write_text(home_pub.read_text(encoding="utf-8"), encoding="utf-8")
        return home_pub
    return None


def existing_instance(env: dict[str, str]) -> dict[str, Any] | None:
    code, out, _err = _aws(
        [
            "ec2",
            "describe-instances",
            "--region",
            REGION,
            "--filters",
            "Name=tag:artcb-node-id,Values=aws-node-3",
            "Name=instance-state-name,Values=pending,running,stopping,stopped",
        ],
        env,
    )
    payload = _json(out) if code == 0 else None
    if not isinstance(payload, dict):
        return None
    for res in payload.get("Reservations") or []:
        for inst in res.get("Instances") or []:
            if inst.get("InstanceId"):
                return inst
    return None


def default_vpc_and_subnet(env: dict[str, str]) -> tuple[str | None, str | None]:
    code, out, _err = _aws(
        ["ec2", "describe-vpcs", "--region", REGION, "--filters", "Name=isDefault,Values=true"],
        env,
    )
    payload = _json(out) if code == 0 else None
    vpc_id = None
    if isinstance(payload, dict):
        vpcs = payload.get("Vpcs") or []
        if vpcs:
            vpc_id = vpcs[0].get("VpcId")
    if not vpc_id:
        return None, None
    scode, sout, _serr = _aws(
        [
            "ec2",
            "describe-subnets",
            "--region",
            REGION,
            "--filters",
            f"Name=vpc-id,Values={vpc_id}",
            "Name=map-public-ip-on-launch,Values=true",
        ],
        env,
    )
    spayload = _json(sout) if scode == 0 else None
    subnet_id = None
    if isinstance(spayload, dict):
        subnets = spayload.get("Subnets") or []
        if subnets:
            subnet_id = subnets[0].get("SubnetId")
    return vpc_id, subnet_id


SG_INGRESS_PORTS = (22, 80, 443, 8000, 8443)


def authorize_sg_ports(env: dict[str, str], sg_id: str, ports: tuple[int, ...] = SG_INGRESS_PORTS) -> dict[int, int]:
    """Idempotent: Duplicate is AWS 400, treated as already-open (rc 0 here)."""
    results: dict[int, int] = {}
    for port in ports:
        code, _out, _err = _aws(
            [
                "ec2",
                "authorize-security-group-ingress",
                "--region",
                REGION,
                "--group-id",
                sg_id,
                "--ip-permissions",
                json.dumps(
                    [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": port,
                            "ToPort": port,
                            "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": f"artcb-{port}"}],
                            "Ipv6Ranges": [{"CidrIpv6": "::/0", "Description": f"artcb-{port}-v6"}],
                        }
                    ]
                ),
            ],
            env,
        )
        results[port] = 0 if code == 0 or "InvalidPermission.Duplicate" in (_err or "") else code
    return results


def ensure_security_group(env: dict[str, str], vpc_id: str) -> str | None:
    code, out, _err = _aws(
        [
            "ec2",
            "describe-security-groups",
            "--region",
            REGION,
            "--filters",
            f"Name=group-name,Values={SG_NAME}",
            f"Name=vpc-id,Values={vpc_id}",
        ],
        env,
    )
    payload = _json(out) if code == 0 else None
    if isinstance(payload, dict) and payload.get("SecurityGroups"):
        sg_id = payload["SecurityGroups"][0].get("GroupId")
        if sg_id:
            authorize_sg_ports(env, sg_id)
        return sg_id
    ccode, cout, _cerr = _aws(
        [
            "ec2",
            "create-security-group",
            "--region",
            REGION,
            "--group-name",
            SG_NAME,
            "--description",
            "ARTCB aws-node-3 SSH 22 HTTP 80/8000 TLS 443/8443",
            "--vpc-id",
            vpc_id,
            "--tag-specifications",
            "ResourceType=security-group,Tags=[{Key=Name,Value=artcb-aws-node-3-sg},{Key=artcb-node-id,Value=aws-node-3}]",
        ],
        env,
    )
    created = _json(cout) if ccode == 0 else None
    sg_id = created.get("GroupId") if isinstance(created, dict) else None
    if not sg_id:
        return None
    authorize_sg_ports(env, sg_id)
    return sg_id


def ensure_key_pair(env: dict[str, str], pub: Path) -> dict[str, Any]:
    code, _out, err = _aws(
        [
            "ec2",
            "import-key-pair",
            "--region",
            REGION,
            "--key-name",
            KEY_NAME,
            "--public-key-material",
            f"fileb://{pub}",
            "--tag-specifications",
            "ResourceType=key-pair,Tags=[{Key=artcb-node-id,Value=aws-node-3}]",
        ],
        env,
    )
    duplicate = "InvalidKeyPair.Duplicate" in (err or "")
    return {"import_exit": code, "already_present": duplicate or code == 0, "ok": code == 0 or duplicate}


def wait_public_ip(env: dict[str, str], instance_id: str, timeout: int = 180) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        code, out, err = _aws(
            ["ec2", "describe-instances", "--region", REGION, "--instance-ids", instance_id],
            env,
        )
        payload = _json(out) if code == 0 else None
        inst = {}
        if isinstance(payload, dict):
            res = (payload.get("Reservations") or [{}])[0]
            inst = ((res.get("Instances") or [{}])[0]) if isinstance(res, dict) else {}
        last = {
            "instance_id": instance_id,
            "state": ((inst.get("State") or {}) if isinstance(inst, dict) else {}).get("Name"),
            "public_ip": inst.get("PublicIpAddress") if isinstance(inst, dict) else None,
            "private_ip": inst.get("PrivateIpAddress") if isinstance(inst, dict) else None,
            "az": ((inst.get("Placement") or {}) if isinstance(inst, dict) else {}).get("AvailabilityZone"),
            "stderr_tail": _tail(err),
        }
        if last.get("state") == "running" and last.get("public_ip"):
            return last
        time.sleep(5)
    last["wait_timeout"] = True
    return last


def _append_local_public(ip: str, instance_id: str) -> None:
    path = local_env_path("aws-node-3")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = parse_env_file(path)
    existing["AWS_INSTANCE_ID"] = instance_id
    existing["AWS_SERVER_IP"] = ip
    existing["AWS_DEFAULT_REGION"] = REGION
    lines = [f"{k}={v}" for k, v in existing.items() if v]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def launch(diag: dict[str, Any]) -> dict[str, Any]:
    env = _aws_env()
    pub = ensure_ssh_pubkey()
    if not pub:
        return {**diag, "launched": False, "reason": "missing ~/.ssh/artcb_aws_node_3.pub"}
    found = existing_instance(env)
    if found:
        iid = found.get("InstanceId")
        ip = found.get("PublicIpAddress")
        state = (found.get("State") or {}).get("Name")
        if state == "stopped" and iid:
            _aws(["ec2", "start-instances", "--region", REGION, "--instance-ids", iid], env)
        waited = wait_public_ip(env, iid) if iid else {}
        ip = waited.get("public_ip") or ip
        if ip and iid:
            _append_local_public(str(ip), str(iid))
        diag.update(
            {
                "launched": False,
                "reused": True,
                "instance_id": iid,
                "public_ip": ip,
                "state": waited.get("state") or state,
                "reason": "existing_tagged_instance",
            }
        )
        return diag
    ami = latest_ubuntu_ami(env)
    if not ami:
        return {**diag, "launched": False, "reason": "ubuntu_ami_not_found"}
    vpc_id, subnet_id = default_vpc_and_subnet(env)
    if not vpc_id or not subnet_id:
        return {**diag, "launched": False, "reason": "no_default_vpc_or_public_subnet", "vpc_id": vpc_id}
    sg_id = ensure_security_group(env, vpc_id)
    if not sg_id:
        return {**diag, "launched": False, "reason": "security_group_failed", "vpc_id": vpc_id}
    key_info = ensure_key_pair(env, pub)
    user_data = """#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git curl python3 python3-venv python3-pip build-essential cmake libssl-dev nginx openssl
"""
    types_to_try = (INSTANCE_TYPE, *FALLBACK_TYPES)
    last_err = ""
    last_code = 1
    instance_id = None
    used_type = INSTANCE_TYPE
    for itype in types_to_try:
        used_type = itype
        code, out, err = _aws(
            [
                "ec2",
                "run-instances",
                "--region",
                REGION,
                "--image-id",
                ami,
                "--instance-type",
                itype,
                "--key-name",
                KEY_NAME,
                "--count",
                "1",
                "--subnet-id",
                subnet_id,
                "--security-group-ids",
                sg_id,
                "--associate-public-ip-address",
                "--block-device-mappings",
                "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,DeleteOnTermination=true}",
                "--tag-specifications",
                "ResourceType=instance,Tags=[{Key=Name,Value=node-artcb-3},{Key=artcb-node-id,Value=aws-node-3}]",
                "--user-data",
                user_data,
            ],
            env,
        )
        last_code, last_err = code, err
        if code == 0:
            payload = _json(out) or {}
            instance_id = ((payload.get("Instances") or [{}])[0]).get("InstanceId")
            if instance_id:
                break
    launched = bool(instance_id)
    waited: dict[str, Any] = {}
    if launched and instance_id:
        waited = wait_public_ip(env, instance_id)
        if waited.get("public_ip"):
            _append_local_public(str(waited["public_ip"]), instance_id)
    diag.update(
        {
            "launched": launched,
            "reused": False,
            "ami": ami,
            "instance_id": instance_id,
            "instance_type_used": used_type,
            "vpc_id": vpc_id,
            "subnet_id": subnet_id,
            "security_group_id": sg_id,
            "key_pair": key_info,
            "public_ip": waited.get("public_ip"),
            "state": waited.get("state"),
            "run_instances_exit": last_code,
            "stderr_tail": _tail(last_err or waited.get("stderr_tail") or ""),
        }
    )
    return diag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="call RunInstances if EC2 is allowed")
    parser.add_argument(
        "--open-http",
        action="store_true",
        help="ensure existing SG allows tcp/80 and tcp/443 (no launch)",
    )
    args = parser.parse_args()
    if args.open_http:
        env = _aws_env()
        vpc_id, _subnet = default_vpc_and_subnet(env)
        result: dict[str, Any] = {"open_http": True, "vpc_id": vpc_id}
        if vpc_id:
            sg_id = ensure_security_group(env, vpc_id)
            result["security_group_id"] = sg_id
            result["ok"] = bool(sg_id)
        else:
            result["ok"] = False
            result["reason"] = "no_vpc"
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("ok") else 3
    diag = diagnose()
    if args.yes and diag.get("ec2_allowed"):
        diag = launch(diag)
    elif args.yes and not diag.get("ec2_allowed"):
        diag["launch_skipped"] = "ec2_denied"
    print(json.dumps(diag, indent=2, sort_keys=True, default=str))
    if diag.get("launched") or diag.get("reused"):
        return 0
    return 0 if diag.get("sts_ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
