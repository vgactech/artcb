#!/usr/bin/env python3
"""Create the Cursor-agent wallet + API key on artcb-node-1.

Runs the sensitive steps on the node via SSH (localhost API).
Never prints tokens, passwords, or seeds.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import (  # noqa: E402
    DEFAULT_LIVE_URL,
    DEFAULT_SSH_HOST,
    DEFAULT_SSH_USER,
    apply_key_to_environ,
    ensure_ovh_ssh_key,
    http_json,
    local_env_path,
    pull_remote_agent_env,
    write_doppler_secrets,
    write_local_env,
)

REMOTE_PY = r"""
import json, os, secrets, pathlib, urllib.request, urllib.error

BASE = "http://127.0.0.1:8000"
WALLET = "cursor-cloud-agent"
ENV_PATH = pathlib.Path("/home/ubuntu/.artcb/cursor_agent.env")
PUBLIC_URL = "http://152.228.144.34:8000"

def http(method, path, body=None, token=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(detail) if detail else {"detail": detail}
        except Exception:
            parsed = {"detail": detail[:240]}
        return exc.code, parsed

def load_env(path):
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out

existing = load_env(ENV_PATH)
password = existing.get("ARTCB_AGENT_WALLET_PASSWORD") or secrets.token_urlsafe(24)
code, wallets = http("GET", "/api/v1/wallet/list")
names = [w.get("name") for w in (wallets.get("wallets") or [])] if isinstance(wallets, dict) else []
created = False
if WALLET not in names:
    code, created_body = http("POST", "/api/v1/wallet/create", {"name": WALLET, "password": password})
    if code >= 400:
        print(json.dumps({"ok": False, "step": "wallet_create", "http": code, "detail": created_body}))
        raise SystemExit(1)
    created = True
    # discard seed immediately — file on node + password are enough to login
    if isinstance(created_body, dict):
        created_body.pop("seed_hex", None)

code, sess = http("POST", "/api/v1/auth/login", {"name": WALLET, "password": password})
if code >= 400 or not isinstance(sess, dict) or not sess.get("session_token"):
    print(json.dumps({"ok": False, "step": "login", "http": code, "detail": sess}))
    raise SystemExit(1)

token = existing.get("ARTCB_API_KEY", "")
key_id = existing.get("ARTCB_AGENT_KEY_ID", "")
preview = ""
rotated = False
if token.startswith("artcb_"):
    code, me = http("GET", "/api/v1/api-keys/me", token=token)
    if code == 200:
        key_id = me.get("key_id", key_id)
        preview = me.get("key_id", "")[:12]
    else:
        token = ""

if not token.startswith("artcb_"):
    code, gen = http(
        "POST",
        "/api/v1/api-keys/generate",
        {
            "label": "cursor-cloud-agent",
            "scopes": ["read", "write"],
            "expires_days": 90,
        },
        token=sess["session_token"],
    )
    if code >= 400 or not isinstance(gen, dict) or not str(gen.get("token", "")).startswith("artcb_"):
        print(json.dumps({"ok": False, "step": "generate", "http": code, "detail": gen}))
        raise SystemExit(1)
    token = gen["token"]
    key_id = gen.get("key_id", "")
    preview = gen.get("key_preview", "")
    rotated = True

ENV_PATH.parent.mkdir(mode=0o700, exist_ok=True)
lines = [
    f"ARTCB_API_URL={PUBLIC_URL}",
    f"ARTCB_API_KEY={token}",
    f"ARTCB_AGENT_WALLET={WALLET}",
    f"ARTCB_AGENT_WALLET_PASSWORD={password}",
    f"ARTCB_AGENT_ADDRESS={sess.get('address','')}",
    f"ARTCB_AGENT_KEY_ID={key_id}",
]
ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
ENV_PATH.chmod(0o600)

print(json.dumps({
    "ok": True,
    "wallet": WALLET,
    "address": sess.get("address"),
    "key_id": key_id,
    "key_preview": preview,
    "created_wallet": created,
    "generated_new_key": rotated,
    "env_path": str(ENV_PATH),
}))
"""


def main() -> int:
    key_path = ensure_ovh_ssh_key()
    if key_path is None:
        print(json.dumps({"ok": False, "error": "OVH SSH key unavailable"}))
        return 2
    completed = subprocess.run(
        [
            "ssh",
            "-i",
            str(key_path),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            f"{DEFAULT_SSH_USER}@{DEFAULT_SSH_HOST}",
            "python3 -",
        ],
        input=REMOTE_PY,
        check=False,
        timeout=60,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "remote provision failed",
                    "rc": completed.returncode,
                    "stderr": (completed.stderr or "")[-400:],
                    "stdout": (completed.stdout or "")[-400:],
                }
            )
        )
        return 1
    try:
        meta = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        print(json.dumps({"ok": False, "error": "remote JSON parse", "stdout": (completed.stdout or "")[-200]}))
        return 1
    if not meta.get("ok"):
        print(json.dumps(meta))
        return 1

    pulled = pull_remote_agent_env()
    key = pulled.get("ARTCB_API_KEY", "")
    if not key.startswith("artcb_"):
        print(json.dumps({"ok": False, "error": "scp env missing ARTCB_API_KEY", **{k: meta.get(k) for k in ("key_id", "address")}}))
        return 1
    write_local_env(
        {
            "ARTCB_API_URL": pulled.get("ARTCB_API_URL", DEFAULT_LIVE_URL),
            "ARTCB_API_KEY": key,
            "ARTCB_AGENT_WALLET": pulled.get("ARTCB_AGENT_WALLET", ""),
            "ARTCB_AGENT_ADDRESS": pulled.get("ARTCB_AGENT_ADDRESS", ""),
            "ARTCB_AGENT_KEY_ID": pulled.get("ARTCB_AGENT_KEY_ID", ""),
        }
    )
    # keep password only on the node / local 600 file already via scp
    apply_key_to_environ(key)
    local = local_env_path()
    local.chmod(stat.S_IRUSR | stat.S_IWUSR)

    doppler = write_doppler_secrets(
        {
            "ARTCB_API_KEY": key,
            "ARTCB_API_URL": pulled.get("ARTCB_API_URL", DEFAULT_LIVE_URL),
            "ARTCB_AGENT_KEY_ID": pulled.get("ARTCB_AGENT_KEY_ID", ""),
        }
    )
    status, me = http_json("GET", f"{DEFAULT_LIVE_URL}/api/v1/api-keys/me", api_key=key)
    print(
        json.dumps(
            {
                "ok": status == 200,
                "live_url": DEFAULT_LIVE_URL,
                "wallet": meta.get("wallet"),
                "address": meta.get("address"),
                "key_id": meta.get("key_id") or (me.get("key_id") if isinstance(me, dict) else None),
                "key_preview": meta.get("key_preview"),
                "created_wallet": meta.get("created_wallet"),
                "generated_new_key": meta.get("generated_new_key"),
                "me_http": status,
                "me_scopes": me.get("scopes") if isinstance(me, dict) else None,
                "doppler_write": doppler,
                "local_env": str(local),
                "token_printed": False,
            },
            indent=2,
        )
    )
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
