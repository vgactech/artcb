#!/usr/bin/env python3
"""Build a NitroTPM AMI from the current UEFI aws-node-3 volume and launch a candidate.

Does NOT recast guest swtpm as L3. Does NOT enable TPM on i-085b74abd1aaf04ee.
Does NOT wipe blocks.jsonl. Stays t3.small eu-west-3.

The candidate is tagged aws-node-3-nitrotpm and artcb is stopped on boot so
it cannot join PBFT as a second aws-node-3. Cut-over (EIP/IP + binding +
stop old) is a separate --cutover step after a verified quote.
"""

from __future__ import annotations

import argparse
import base64
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
from artcb.node_registry import local_env_path  # noqa: E402

REGION = "eu-west-3"
SOURCE_INSTANCE = "i-085b74abd1aaf04ee"
INSTANCE_TYPE = "t3.small"
KEY_NAME = "artcb-aws-node-3"
ROOT_DEVICE = "/dev/sda1"
CANDIDATE_TAG = "aws-node-3-nitrotpm"

USER_DATA = """#!/bin/bash
set -eu
systemctl stop artcb.service 2>/dev/null || true
systemctl disable artcb.service 2>/dev/null || true
systemctl stop artcb-follow-main.timer 2>/dev/null || true
systemctl disable artcb-follow-main.timer 2>/dev/null || true
usermod -aG tss ubuntu 2>/dev/null || true
mkdir -p /var/lib/artcb/node/tpm
chown ubuntu:ubuntu /var/lib/artcb/node/tpm
touch /var/lib/artcb/nitrotpm-candidate
"""


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
    if env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"):
        env.pop("AWS_PROFILE", None)
    env.setdefault("AWS_DEFAULT_REGION", local.get("AWS_DEFAULT_REGION") or REGION)
    return env


def _aws(args: list[str], env: dict[str, str], timeout: int = 120) -> tuple[int, str, str]:
    cmd = ["aws", *args]
    if "--output" not in args:
        cmd.extend(["--output", "json"])
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _json(out: str) -> Any:
    try:
        return json.loads(out) if out.strip() else None
    except json.JSONDecodeError:
        return None


def _tail(err: str, n: int = 500) -> str:
    return (err or "")[-n:]


def describe_instance(env: dict[str, str], iid: str) -> dict[str, Any]:
    code, out, err = _aws(["ec2", "describe-instances", "--region", REGION, "--instance-ids", iid], env)
    payload = _json(out) if code == 0 else None
    inst: dict[str, Any] = {}
    if isinstance(payload, dict):
        res = (payload.get("Reservations") or [{}])[0]
        inst = ((res.get("Instances") or [{}])[0]) if isinstance(res, dict) else {}
    return {"ok": code == 0 and bool(inst.get("InstanceId")), "instance": inst, "stderr_tail": _tail(err)}


def wait_snapshot(env: dict[str, str], snap_id: str, timeout: int = 1800) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        code, out, err = _aws(["ec2", "describe-snapshots", "--region", REGION, "--snapshot-ids", snap_id], env)
        payload = _json(out) if code == 0 else None
        snap = ((payload.get("Snapshots") or [{}])[0]) if isinstance(payload, dict) else {}
        last = {
            "snapshot_id": snap_id,
            "state": snap.get("State"),
            "progress": snap.get("Progress"),
            "stderr_tail": _tail(err),
        }
        if snap.get("State") == "completed":
            return last
        if snap.get("State") == "error":
            last["ok"] = False
            return last
        time.sleep(15)
    last["wait_timeout"] = True
    return last


def wait_image(env: dict[str, str], ami: str, timeout: int = 900) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        code, out, err = _aws(["ec2", "describe-images", "--region", REGION, "--image-ids", ami], env)
        payload = _json(out) if code == 0 else None
        img = ((payload.get("Images") or [{}])[0]) if isinstance(payload, dict) else {}
        last = {
            "image_id": ami,
            "state": img.get("State"),
            "boot_mode": img.get("BootMode"),
            "tpm_support": img.get("TpmSupport"),
            "stderr_tail": _tail(err),
        }
        if img.get("State") == "available":
            return last
        if img.get("State") in {"failed", "error"}:
            last["ok"] = False
            return last
        time.sleep(10)
    last["wait_timeout"] = True
    return last


def wait_instance_ip(env: dict[str, str], iid: str, timeout: int = 240) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        got = describe_instance(env, iid)
        inst = got.get("instance") or {}
        last = {
            "instance_id": iid,
            "state": ((inst.get("State") or {}) if isinstance(inst, dict) else {}).get("Name"),
            "public_ip": inst.get("PublicIpAddress") if isinstance(inst, dict) else None,
            "private_ip": inst.get("PrivateIpAddress") if isinstance(inst, dict) else None,
        }
        if last.get("state") == "running" and last.get("public_ip"):
            return last
        time.sleep(5)
    last["wait_timeout"] = True
    return last


def existing_candidate(env: dict[str, str]) -> dict[str, Any] | None:
    code, out, _err = _aws(
        [
            "ec2",
            "describe-instances",
            "--region",
            REGION,
            "--filters",
            f"Name=tag:artcb-node-id,Values={CANDIDATE_TAG}",
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


def existing_tpm_ami(env: dict[str, str]) -> dict[str, Any] | None:
    code, out, _err = _aws(
        [
            "ec2",
            "describe-images",
            "--region",
            REGION,
            "--owners",
            "self",
            "--filters",
            "Name=tag:artcb-purpose,Values=nitrotpm-ami",
            "Name=state,Values=available",
        ],
        env,
    )
    payload = _json(out) if code == 0 else None
    if not isinstance(payload, dict):
        return None
    images = payload.get("Images") or []
    if not images:
        return None
    images.sort(key=lambda im: im.get("CreationDate") or "")
    return images[-1]


def build(yes: bool) -> dict[str, Any]:
    env = _aws_env()
    source = describe_instance(env, SOURCE_INSTANCE)
    inst = source.get("instance") or {}
    vol = None
    for bdm in inst.get("BlockDeviceMappings") or []:
        if bdm.get("DeviceName") == ROOT_DEVICE:
            vol = (bdm.get("Ebs") or {}).get("VolumeId")
    out: dict[str, Any] = {
        "source_instance": SOURCE_INSTANCE,
        "source_state": ((inst.get("State") or {}).get("Name") if isinstance(inst, dict) else None),
        "source_boot_mode": inst.get("BootMode") if isinstance(inst, dict) else None,
        "source_tpm": inst.get("TpmSupport") if isinstance(inst, dict) else None,
        "source_uefi_preferred": (inst.get("BootMode") if isinstance(inst, dict) else None) in {"uefi", "uefi-preferred"},
        "volume_id": vol,
        "instance_type": INSTANCE_TYPE,
        "certified_100": False,
        "recast_swtpm": False,
        "secrets_printed": False,
    }
    if not source.get("ok") or not vol:
        out["ok"] = False
        out["reason"] = "source_instance_or_volume_missing"
        out["stderr_tail"] = source.get("stderr_tail")
        return out
    if not yes:
        out["ok"] = True
        out["dry_run"] = True
        out["note"] = "pass --yes to snapshot, RegisterImage(tpm v2.0, uefi), launch t3.small candidate"
        return out

    found = existing_candidate(env)
    if found:
        waited = wait_instance_ip(env, found["InstanceId"])
        out.update(
            {
                "ok": True,
                "reused_candidate": True,
                "candidate_instance_id": found["InstanceId"],
                "candidate_public_ip": waited.get("public_ip") or found.get("PublicIpAddress"),
                "candidate_state": waited.get("state"),
                "image_id": found.get("ImageId"),
            }
        )
        return out

    ami_existing = existing_tpm_ami(env)
    snap_id = None
    ami_id = ami_existing.get("ImageId") if ami_existing else None
    if ami_id:
        out["reused_ami"] = ami_id
        img_wait = {
            "image_id": ami_id,
            "state": "available",
            "boot_mode": ami_existing.get("BootMode"),
            "tpm_support": ami_existing.get("TpmSupport"),
        }
    else:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        scode, sout, serr = _aws(
            [
                "ec2",
                "create-snapshot",
                "--region",
                REGION,
                "--volume-id",
                vol,
                "--description",
                f"ARTCB aws-node-3 UEFI root NitroTPM {stamp}",
                "--tag-specifications",
                "ResourceType=snapshot,Tags=["
                f"{{Key=Name,Value=artcb-aws3-nitrotpm-{stamp}}},"
                "{Key=artcb-node-id,Value=aws-node-3},"
                "{Key=artcb-purpose,Value=nitrotpm-ami}]",
            ],
            env,
        )
        sp = _json(sout) if scode == 0 else {}
        snap_id = (sp or {}).get("SnapshotId")
        out["snapshot_create_exit"] = scode
        out["snapshot_id"] = snap_id
        if not snap_id:
            out["ok"] = False
            out["reason"] = "snapshot_failed"
            out["stderr_tail"] = _tail(serr)
            return out
        snap_wait = wait_snapshot(env, snap_id)
        out["snapshot_wait"] = snap_wait
        if snap_wait.get("state") != "completed":
            out["ok"] = False
            out["reason"] = "snapshot_not_completed"
            return out
        rcode, rout, rerr = _aws(
            [
                "ec2",
                "register-image",
                "--region",
                REGION,
                "--name",
                f"artcb-aws3-nitrotpm-{stamp}",
                "--description",
                "ARTCB aws-node-3 Ubuntu 24.04 UEFI NitroTPM v2.0 - not L4 hardware TPM",
                "--architecture",
                "x86_64",
                "--virtualization-type",
                "hvm",
                "--boot-mode",
                "uefi",
                "--tpm-support",
                "v2.0",
                "--ena-support",
                "--sriov-net-support",
                "simple",
                "--imds-support",
                "v2.0",
                "--root-device-name",
                ROOT_DEVICE,
                "--block-device-mappings",
                json.dumps(
                    [
                        {
                            "DeviceName": ROOT_DEVICE,
                            "Ebs": {
                                "SnapshotId": snap_id,
                                "VolumeType": "gp3",
                                "DeleteOnTermination": True,
                            },
                        }
                    ]
                ),
            ],
            env,
        )
        rp = _json(rout) if rcode == 0 else {}
        ami_id = (rp or {}).get("ImageId")
        out["register_exit"] = rcode
        out["image_id"] = ami_id
        if not ami_id:
            out["ok"] = False
            out["reason"] = "register_image_failed"
            out["stderr_tail"] = _tail(rerr)
            return out
        _aws(
            [
                "ec2",
                "create-tags",
                "--region",
                REGION,
                "--resources",
                ami_id,
                "--tags",
                "Key=Name,Value=artcb-aws3-nitrotpm",
                "Key=artcb-purpose,Value=nitrotpm-ami",
                "Key=artcb-node-id,Value=aws-node-3",
            ],
            env,
        )
        img_wait = wait_image(env, ami_id)
        out["image_wait"] = img_wait
        if img_wait.get("state") != "available":
            out["ok"] = False
            out["reason"] = "ami_not_available"
            return out

    subnet = inst.get("SubnetId")
    sgs = [g.get("GroupId") for g in inst.get("SecurityGroups") or [] if g.get("GroupId")]
    user_b64 = base64.b64encode(USER_DATA.encode()).decode()
    lcode, lout, lerr = _aws(
        [
            "ec2",
            "run-instances",
            "--region",
            REGION,
            "--image-id",
            ami_id,
            "--instance-type",
            INSTANCE_TYPE,
            "--key-name",
            KEY_NAME,
            "--count",
            "1",
            "--subnet-id",
            subnet,
            "--security-group-ids",
            *sgs,
            "--associate-public-ip-address",
            "--metadata-options",
            "HttpTokens=required,HttpEndpoint=enabled",
            "--user-data",
            user_b64,
            "--tag-specifications",
            "ResourceType=instance,Tags=["
            "{Key=Name,Value=node-artcb-3-nitrotpm},"
            f"{{Key=artcb-node-id,Value={CANDIDATE_TAG}}},"
            f"{{Key=artcb-replaces,Value={SOURCE_INSTANCE}}}]",
        ],
        env,
    )
    lp = _json(lout) if lcode == 0 else {}
    cand = ((lp or {}).get("Instances") or [{}])[0].get("InstanceId")
    out["run_instances_exit"] = lcode
    out["candidate_instance_id"] = cand
    if not cand:
        out["ok"] = False
        out["reason"] = "run_instances_failed"
        out["stderr_tail"] = _tail(lerr)
        return out
    waited = wait_instance_ip(env, cand)
    out["candidate_public_ip"] = waited.get("public_ip")
    out["candidate_private_ip"] = waited.get("private_ip")
    out["candidate_state"] = waited.get("state")
    out["ok"] = waited.get("state") == "running" and bool(waited.get("public_ip"))
    out["note"] = (
        "Candidate launched with artcb disabled. Probe /dev/tpm0 over SSH. "
        "Do not update official_platform_binding until a verified quote. "
        "NitroTPM on a VM is L3, never L4. Guest swtpm is not this path."
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    result = build(yes=args.yes)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
