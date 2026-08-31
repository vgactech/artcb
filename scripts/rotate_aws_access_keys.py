#!/usr/bin/env python3
"""Rotate IAM access keys for node_artcb_3_agent AFTER live AWS access is proven.

Creates a new key, writes it to Doppler artcb3 + ~/.artcb/nodes/aws-node-3.env
+ ~/.aws/credentials [artcb-node-3], verifies STS with the new key, then
deactivates (does not delete) the previous key.

Never prints secret values. Does not touch OVH1. Does not reduce IAM policies.
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
from artcb.node_registry import local_env_path  # noqa: E402

IAM_USER = "node_artcb_3_agent"
PROFILE = "artcb-node-3"
REGION = "eu-west-3"


def _apply_aliases(env: dict[str, str]) -> None:
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
    _apply_aliases(env)
    env.setdefault("AWS_DEFAULT_REGION", REGION)
    return env


def _aws(args: list[str], env: dict[str, str], timeout: int = 60) -> tuple[int, Any, str]:
    cmd = ["aws", *args, "--output", "json"]
    has_keys = bool(env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"))
    if env.get("AWS_PROFILE") and not has_keys:
        cmd.extend(["--profile", env["AWS_PROFILE"]])
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, check=False)
    parsed: Any = None
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return proc.returncode, parsed, (proc.stderr or "")[-400:]


def _write_local(access: str, secret: str, old_id: str | None) -> None:
    path = local_env_path("aws-node-3")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = parse_env_file(path)
    existing["AWS_ACCESS_KEY_ID"] = access
    existing["AWS_SECRET_ACCESS_KEY"] = secret
    existing["AWS_API_KEY_AGENT_3"] = access
    existing["AWS_API_CLI_AGENT_3"] = secret
    existing["AWS_IAM_USER"] = IAM_USER
    existing["AWS_DEFAULT_REGION"] = REGION
    existing["AWS_CLI_PROFILE"] = PROFILE
    if old_id:
        existing["AWS_PREVIOUS_ACCESS_KEY_ID"] = old_id
        existing["AWS_PREVIOUS_KEY_STATUS"] = "Inactive"
    lines = [f"{k}={v}" for k, v in existing.items() if v]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    creds = Path.home() / ".aws" / "credentials"
    creds.parent.mkdir(mode=0o700, exist_ok=True)
    block = (
        f"[{PROFILE}]\n"
        f"aws_access_key_id = {access}\n"
        f"aws_secret_access_key = {secret}\n"
        f"region = {REGION}\n"
    )
    previous = creds.read_text(encoding="utf-8") if creds.is_file() else ""
    if f"[{PROFILE}]" in previous:
        import re

        previous = re.sub(
            rf"\[{PROFILE}\]\n(?:.*\n)*?(?=\[|\Z)",
            block + "\n",
            previous,
        )
        creds.write_text(previous, encoding="utf-8")
    else:
        with creds.open("a", encoding="utf-8") as fh:
            if previous and not previous.endswith("\n"):
                fh.write("\n")
            fh.write(block)
    creds.chmod(0o600)


def _doppler_write(access: str, secret: str) -> dict[str, Any]:
    token = (os.environ.get("KEY_API_ARTCB_DOPPLER_3") or os.environ.get("DOPPLER_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "reason": "no_doppler_token"}
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    payload = json.dumps(
        {
            "project": "artcb3",
            "config": "dev",
            "secrets": {
                "AWS_ACCESS_KEY_ID": access,
                "AWS_SECRET_ACCESS_KEY": secret,
                "AWS_API_KEY_AGENT_3": access,
                "AWS_API_CLI_AGENT_3": secret,
            },
        }
    ).encode()
    req = Request(
        "https://api.doppler.com/v3/configs/config/secrets",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            return {"ok": resp.status in {200, 201}, "http": resp.status, "names": 4}
    except HTTPError as exc:
        return {"ok": False, "http": exc.code, "reason": "doppler_http_error"}
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "reason": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    env = _aws_env()
    report: dict[str, Any] = {
        "iam_user": IAM_USER,
        "secrets_printed": False,
        "cursor_aliases_will_stale": True,
        "iam_policies_unchanged": True,
        "rotated": False,
    }
    code, ident, err = _aws(["sts", "get-caller-identity"], env)
    report["pre_sts"] = {
        "ok": code == 0,
        "account": (ident or {}).get("Account") if isinstance(ident, dict) else None,
        "arn_suffix": ((ident or {}).get("Arn") or "")[-40:] if isinstance(ident, dict) else None,
        "stderr_class": "present" if err else "empty",
    }
    if code != 0:
        report["reason"] = "sts_failed_no_rotation"
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3
    if not args.yes:
        report["reason"] = "pass_--yes_after_access_validated"
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    old_id = env.get("AWS_ACCESS_KEY_ID") or ""
    code_list, listed, _ = _aws(["iam", "list-access-keys", "--user-name", IAM_USER], env)
    keys = ((listed or {}).get("AccessKeyMetadata") or []) if isinstance(listed, dict) else []
    report["keys_before_count"] = len(keys)
    if len(keys) >= 2:
        extras = [k for k in keys if (k.get("AccessKeyId") or "") != old_id]
        deleted = 0
        for extra in extras:
            eid = extra.get("AccessKeyId")
            if not eid:
                continue
            dc, _, _ = _aws(
                ["iam", "delete-access-key", "--user-name", IAM_USER, "--access-key-id", eid],
                env,
            )
            if dc == 0:
                deleted += 1
        report["orphan_keys_deleted"] = deleted
        code_list, listed, _ = _aws(["iam", "list-access-keys", "--user-name", IAM_USER], env)
        keys = ((listed or {}).get("AccessKeyMetadata") or []) if isinstance(listed, dict) else []
        report["keys_after_orphan_cleanup"] = len(keys)
        if len(keys) >= 2:
            report["reason"] = "two_keys_already_exist_delete_inactive_first"
            print(json.dumps(report, indent=2, sort_keys=True))
            return 4
    code_c, created, err_c = _aws(
        ["iam", "create-access-key", "--user-name", IAM_USER],
        env,
    )
    ak = (created or {}).get("AccessKey") if isinstance(created, dict) else None
    if code_c != 0 or not isinstance(ak, dict) or not ak.get("AccessKeyId") or not ak.get("SecretAccessKey"):
        report["reason"] = "create_access_key_failed"
        report["create_stderr_present"] = bool(err_c)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 5
    new_id = str(ak["AccessKeyId"])
    new_secret = str(ak["SecretAccessKey"])
    new_env = {
        "PATH": env.get("PATH", ""),
        "HOME": env.get("HOME", ""),
        "AWS_ACCESS_KEY_ID": new_id,
        "AWS_SECRET_ACCESS_KEY": new_secret,
        "AWS_DEFAULT_REGION": env.get("AWS_DEFAULT_REGION") or REGION,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    code_n, ident_n, err_n = 1, None, ""
    for attempt in range(6):
        time.sleep(2 + attempt)
        code_n, ident_n, err_n = _aws(["sts", "get-caller-identity"], new_env)
        if code_n == 0:
            break
    if code_n != 0:
        _aws(
            ["iam", "delete-access-key", "--user-name", IAM_USER, "--access-key-id", new_id],
            env,
        )
        report["reason"] = "new_key_sts_failed_new_key_deleted_old_kept"
        report["new_key_id_prefix"] = new_id[:8]
        report["sts_retry_stderr_present"] = bool(err_n)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 6
    _write_local(new_id, new_secret, old_id or None)
    doppler = _doppler_write(new_id, new_secret)
    deactivated = False
    if old_id and old_id != new_id:
        code_d, _, _ = _aws(
            [
                "iam",
                "update-access-key",
                "--user-name",
                IAM_USER,
                "--access-key-id",
                old_id,
                "--status",
                "Inactive",
            ],
            new_env,
        )
        deactivated = code_d == 0
    report.update(
        {
            "rotated": True,
            "new_key_id_prefix": new_id[:8],
            "old_key_id_prefix": (old_id[:8] if old_id else None),
            "old_key_deactivated": deactivated,
            "new_sts_ok": True,
            "doppler": {"ok": doppler.get("ok"), "http": doppler.get("http")},
            "local_env_updated": True,
            "aws_credentials_profile": PROFILE,
        }
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["rotated"] and report["new_sts_ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
