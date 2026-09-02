#!/usr/bin/env python3
"""Recover ovh-node-2 SSH without wiping the live book (D-054).

Public Cloud rescue → mount the ~49G original ext4 (never the rescue root)
→ append this agent's pubkey → confirm blocks.jsonl → unrescue.

Never prints passwords, PEM, or tokens. Requires KEY_API_ARTCB_DOPPLER_2
(OVH API) and paramiko. Writes ~/.ssh/artcb_ovh_node_2 if missing, then
optionally SSH_PRIVATE_KEY into Doppler artcb-2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "1fc10a3fb27d4511a8c7873cd16243f2"
INSTANCE_ID = "6470522e-1561-4741-9254-5f58b909eeb9"
USER_ID = 765264
IP = "151.80.107.29"
OVH_BASE = "https://eu.api.ovh.com/1.0"
KEY_PATH = Path.home() / ".ssh" / "artcb_ovh_node_2"


def _log(obj: object) -> None:
    print(json.dumps(obj, default=str))


def _sval(secrets: dict, name: str) -> str:
    meta = secrets.get(name) or {}
    return str(meta.get("computed") or meta.get("raw") or "").strip() if isinstance(meta, dict) else ""


def _doppler_artcb2() -> dict[str, str]:
    token = (os.environ.get("KEY_API_ARTCB_DOPPLER_2") or "").strip()
    if not token:
        return {}
    req = Request(
        "https://api.doppler.com/v3/configs/config/secrets?project=artcb-2&config=dev",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode())
    secrets = payload.get("secrets") or {}
    return {
        "OVH_APPLICATION_KEY": _sval(secrets, "OVH_APPLICATION_KEY"),
        "OVH_APPLICATION_SECRET": _sval(secrets, "OVH_APPLICATION_SECRET"),
        "OVH_CONSUMER_KEY": _sval(secrets, "OVH_CONSUMER_KEY"),
    }


def ovh_factory(ak: str, as_: str, ck: str):
    def ovh(method: str, path: str, body: dict | None = None):
        payload = None if body is None else json.dumps(body)
        with urlopen(f"{OVH_BASE}/auth/time", timeout=10) as resp:
            ts = str(int(json.loads(resp.read().decode())))
        url = OVH_BASE + path
        sig_input = "+".join([as_, ck, method, url, payload or "", ts])
        sig = "$1$" + hashlib.sha1(sig_input.encode("utf-8")).hexdigest()
        headers = {
            "X-Ovh-Application": ak,
            "X-Ovh-Timestamp": ts,
            "X-Ovh-Signature": sig,
            "X-Ovh-Consumer": ck,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        req = Request(url, data=None if payload is None else payload.encode(), method=method, headers=headers)
        try:
            with urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:600]
            try:
                parsed = json.loads(detail) if detail else {"detail": detail}
            except json.JSONDecodeError:
                parsed = {"detail": detail}
            return exc.code, parsed

    return ovh


def ensure_key() -> str:
    KEY_PATH.parent.mkdir(mode=0o700, exist_ok=True)
    if not KEY_PATH.is_file() or KEY_PATH.stat().st_size < 80:
        proc = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(KEY_PATH), "-N", "", "-C", "artcb-ovh-node-2-agent-204"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit("ssh-keygen_failed")
        KEY_PATH.chmod(0o600)
    return KEY_PATH.with_suffix(".pub").read_text(encoding="utf-8").strip()


def write_doppler_ssh() -> dict:
    token = (os.environ.get("KEY_API_ARTCB_DOPPLER_2") or "").strip()
    pem = KEY_PATH.read_text(encoding="utf-8")
    body = json.dumps({"project": "artcb-2", "config": "dev", "secrets": {"SSH_PRIVATE_KEY": pem}}).encode()
    req = Request(
        "https://api.doppler.com/v3/configs/config/secrets",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
            return {"http": resp.status, "ok": bool(payload.get("success")), "names": ["SSH_PRIVATE_KEY"]}
    except HTTPError as exc:
        return {"http": exc.code, "ok": False}


def keystone(ovh) -> tuple[str, str]:
    code, body = ovh("POST", f"/cloud/project/{PROJECT_ID}/user/{USER_ID}/regeneratePassword")
    if code not in {200, 201} or not isinstance(body, dict):
        raise RuntimeError("openstack_password_failed")
    pw = str(body.get("password") or "")
    uname = str(body.get("username") or "")
    time.sleep(2)
    auth = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {"user": {"name": uname, "domain": {"name": "Default"}, "password": pw}},
            },
            "scope": {"project": {"id": PROJECT_ID}},
        }
    }
    req = Request(
        "https://auth.cloud.ovh.net/v3/auth/tokens",
        data=json.dumps(auth).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urlopen(req, timeout=20) as resp:
        os_token = resp.headers.get("X-Subject-Token") or ""
        token_body = json.loads(resp.read().decode())
    compute = ""
    for svc in (token_body.get("token") or {}).get("catalog") or []:
        if svc.get("type") != "compute":
            continue
        for ep in svc.get("endpoints") or []:
            if ep.get("interface") == "public" and str(ep.get("region") or "").upper() == "GRA11":
                compute = str(ep.get("url") or "")
    if not os_token or not compute:
        raise RuntimeError("keystone_no_compute")
    return os_token, compute


def console_password(os_token: str, compute: str) -> str:
    req = Request(
        compute.rstrip("/") + f"/servers/{INSTANCE_ID}/action",
        data=json.dumps({"os-getConsoleOutput": {"length": 80}}).encode(),
        method="POST",
        headers={"X-Auth-Token": os_token, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urlopen(req, timeout=30) as resp:
        clog = json.loads(resp.read().decode())
    cands = re.findall(r"Password:\s*(\S+)", str(clog.get("output") or ""))
    return cands[-1] if cands else ""


def wait_status(ovh, want: str, timeout: int = 240) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        _code, inst = ovh("GET", f"/cloud/project/{PROJECT_ID}/instance/{INSTANCE_ID}")
        last = str((inst or {}).get("status") or "")
        _log({"status": last, "want": want})
        if last == want:
            return last
        time.sleep(5)
    raise TimeoutError(f"timeout_waiting_{want}_last_{last}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="actually enter rescue (downtime on :8000)")
    parser.add_argument("--write-doppler", action="store_true", help="store SSH_PRIVATE_KEY in Doppler artcb-2")
    args = parser.parse_args()
    try:
        import paramiko
    except ImportError:
        _log({"ok": False, "error": "paramiko_missing"})
        return 2
    creds = _doppler_artcb2()
    if not all(creds.get(k) for k in ("OVH_APPLICATION_KEY", "OVH_APPLICATION_SECRET", "OVH_CONSUMER_KEY")):
        _log({"ok": False, "error": "missing_ovh2_doppler_creds"})
        return 2
    pub = ensure_key()
    _log({"key_path": str(KEY_PATH), "pub_comment": pub.split()[-1] if pub.split() else "", "book_wipe": False})
    if not args.yes:
        _log({"ok": True, "dry_run": True, "hint": "pass --yes to rescue"})
        return 0
    ovh = ovh_factory(creds["OVH_APPLICATION_KEY"], creds["OVH_APPLICATION_SECRET"], creds["OVH_CONSUMER_KEY"])
    code, inst = ovh("GET", f"/cloud/project/{PROJECT_ID}/instance/{INSTANCE_ID}")
    _log({"instance_http": code, "status": (inst or {}).get("status"), "name": (inst or {}).get("name")})
    code, _body = ovh("POST", f"/cloud/project/{PROJECT_ID}/instance/{INSTANCE_ID}/rescueMode", {"rescue": True})
    _log({"rescue_http": code})
    if code not in {200, 201, 204}:
        return 3
    wait_status(ovh, "RESCUE")
    rescue_pw = ""
    for i in range(24):
        try:
            os_token, compute = keystone(ovh)
            rescue_pw = console_password(os_token, compute)
            _log({"console_try": i + 1, "has_password": bool(rescue_pw)})
            if rescue_pw:
                break
        except Exception as exc:  # noqa: BLE001
            _log({"console_try": i + 1, "error": type(exc).__name__})
        time.sleep(4)
    if not rescue_pw:
        ovh("POST", f"/cloud/project/{PROJECT_ID}/instance/{INSTANCE_ID}/rescueMode", {"rescue": False})
        _log({"ok": False, "error": "no_console_password", "unrescue": True})
        return 4

    def run(cmd: str, timeout: int = 90) -> tuple[int, str, str]:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            IP,
            username="root",
            password=rescue_pw,
            timeout=20,
            look_for_keys=False,
            allow_agent=False,
            banner_timeout=30,
            auth_timeout=20,
        )
        _stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        client.close()
        return rc, out, err

    inject = r"""
set -euo pipefail
echo LIVE_ROOT $(findmnt -n -o SOURCE /)
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
LIVE=$(findmnt -n -o SOURCE /)
ORIG=""
while read -r name size fstype mp; do
  [ "$fstype" = "ext4" ] || continue
  case "$name" in
    /dev/*) dev="$name" ;;
    *) dev="/dev/$name" ;;
  esac
  [ "$dev" = "$LIVE" ] && continue
  case "$size" in
    49G|48.9G|50G|49.*) ORIG=$dev ;;
  esac
done < <(lsblk -nr -o NAME,SIZE,FSTYPE,MOUNTPOINT)
test -n "$ORIG"
mkdir -p /mnt/orig
mount "$ORIG" /mnt/orig
test -d /mnt/orig/home/ubuntu
AUTH=/mnt/orig/home/ubuntu/.ssh/authorized_keys
mkdir -p /mnt/orig/home/ubuntu/.ssh
touch "$AUTH"
chmod 700 /mnt/orig/home/ubuntu/.ssh
PUB_LINE='__PUB__'
grep -qxF "$PUB_LINE" "$AUTH" 2>/dev/null || printf '%s\n' "$PUB_LINE" >> "$AUTH"
chown -R 1000:1000 /mnt/orig/home/ubuntu/.ssh || true
chmod 600 "$AUTH"
echo AUTH_LINES $(wc -l < "$AUTH")
BOOK=/mnt/orig/home/ubuntu/artcb/data/chain/blocks.jsonl
test -f "$BOOK"
echo BOOK_LINES $(wc -l < "$BOOK")
echo BOOK_PRESERVED
echo install.sh not executed
echo init_genesis.py not executed
sync
umount /mnt/orig
echo UNMOUNTED
"""
    inject = inject.replace("__PUB__", pub)
    rc, out, err = (1, "", "ssh_not_tried")
    for i in range(15):
        try:
            rc, out, err = run(inject, timeout=90)
            _log({"inject_try": i + 1, "rc": rc, "stdout_tail": out[-1500:], "stderr_tail": err[-300:]})
            if rc == 0:
                break
        except Exception as exc:  # noqa: BLE001
            _log({"inject_try": i + 1, "error": type(exc).__name__})
            time.sleep(4)
    else:
        ovh("POST", f"/cloud/project/{PROJECT_ID}/instance/{INSTANCE_ID}/rescueMode", {"rescue": False})
        _log({"ok": False, "error": "inject_failed", "unrescue": True})
        return 5
    if rc != 0:
        ovh("POST", f"/cloud/project/{PROJECT_ID}/instance/{INSTANCE_ID}/rescueMode", {"rescue": False})
        return 5
    ovh("POST", f"/cloud/project/{PROJECT_ID}/instance/{INSTANCE_ID}/rescueMode", {"rescue": False})
    wait_status(ovh, "ACTIVE")
    proc = subprocess.run(
        [
            "ssh", "-i", str(KEY_PATH),
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=12",
            f"ubuntu@{IP}",
            "echo SSH_OK; hostname; git -C /home/ubuntu/artcb rev-parse HEAD; wc -l /home/ubuntu/artcb/data/chain/blocks.jsonl",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    _log({"ssh_rc": proc.returncode, "stdout": (proc.stdout or "")[-400:], "stderr": (proc.stderr or "")[-200:]})
    doppler = write_doppler_ssh() if args.write_doppler else {"skipped": True}
    _log({"ok": proc.returncode == 0, "doppler": doppler, "certified_distributed_mainnet": False})
    return 0 if proc.returncode == 0 else 6


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        _log({"ok": False, "error": type(exc).__name__})
        raise SystemExit(1)
