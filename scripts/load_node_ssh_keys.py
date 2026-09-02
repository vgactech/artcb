#!/usr/bin/env python3
"""Write per-node SSH private keys to ~/.ssh (mode 600). Never prints key material.

Sources, in order, for each dest:
  1. Cursor/env OVH_SSH_PRIVATE_KEY (OVH1 only)
  2. Doppler SSH_PRIVATE_KEY of that node's project
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DESTS = {
    "ovh1": {
        "dest": Path.home() / ".ssh" / "artcb_ovh_deploy",
        "token_env": "DOPPLER_TOKEN",
        "project": "artcb-blockchain",
        "env_pem": "OVH_SSH_PRIVATE_KEY",
    },
    "ovh2": {
        "dest": Path.home() / ".ssh" / "artcb_ovh_node_2",
        "token_env": "KEY_API_ARTCB_DOPPLER_2",
        "project": "artcb-2",
        "env_pem": "OVH2_SSH_PRIVATE_KEY",
    },
    "aws3": {
        "dest": Path.home() / ".ssh" / "artcb_aws_node_3",
        "token_env": "KEY_API_ARTCB_DOPPLER_3",
        "project": "artcb3",
        "env_pem": "AWS3_SSH_PRIVATE_KEY",
    },
    "ovh4": {
        "dest": Path.home() / ".ssh" / "artcb_ovh_node_4",
        "token_env": "KEY_API_ARTCB_DOPPLER_4",
        "project": "artcb-4",
        "env_pem": "OVH4_SSH_PRIVATE_KEY",
    },
}


def _looks_like_key(raw: str) -> bool:
    return "BEGIN" in raw and "PRIVATE" in raw


def _normalize(raw: str) -> str:
    norm = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not norm.endswith("\n"):
        norm += "\n"
    return norm


def _write(dest: Path, raw: str) -> None:
    dest.parent.mkdir(mode=0o700, exist_ok=True)
    dest.write_text(_normalize(raw), encoding="utf-8")
    dest.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _doppler_ssh(token: str, project: str) -> str:
    url = (
        "https://api.doppler.com/v3/configs/config/secrets"
        f"?project={project}&config=dev"
    )
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""
    secrets = payload.get("secrets") or {}
    meta = secrets.get("SSH_PRIVATE_KEY") or {}
    return (meta.get("computed") or meta.get("raw") or "").strip()


def main() -> int:
    rows = []
    ok = 0
    for name, spec in DESTS.items():
        dest: Path = spec["dest"]
        source = "missing"
        raw = (os.environ.get(spec["env_pem"]) or "").strip()
        if _looks_like_key(raw):
            source = "env"
        else:
            token = (os.environ.get(spec["token_env"]) or "").strip()
            if token:
                pulled = _doppler_ssh(token, spec["project"])
                if _looks_like_key(pulled):
                    raw = pulled
                    source = "doppler"
        if _looks_like_key(raw):
            _write(dest, raw)
            rows.append({"name": name, "source": source, "bytes": dest.stat().st_size, "written": True})
            ok += 1
        else:
            present = dest.is_file() and dest.stat().st_size > 80
            rows.append({"name": name, "source": source, "written": False, "existing_file": present})
            if present:
                ok += 1
    print(json.dumps({"ok_files": ok, "nodes": rows}, indent=2))
    return 0 if ok >= 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
