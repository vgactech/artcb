#!/usr/bin/env python3
"""Provision (or reuse) OVH Public Cloud instance for ovh-node-4.

Project 926bb1d6755e4f2c98ae9db06ef44e4f (nic xy4589-ovh). GRA11 d2-8.
Credentials from Doppler artcb-4 / local ~/.artcb/nodes/ovh-node-4.env.
Never prints secrets. Never writes secrets into git. Does not touch OVH1 or OVH2.
Never falls back to process OVH_* (those belong to other nodes / Cursor).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import parse_env_file  # noqa: E402
from artcb.node_registry import NODES, local_env_path  # noqa: E402

PROJECT_ID = "926bb1d6755e4f2c98ae9db06ef44e4f"
REGION = "GRA11"
FLAVOR_NAME = "d2-8"
IMAGE_NAME = "Ubuntu 24.04"
INSTANCE_NAME = "node-artcb-ovh-4"
SSH_KEY_NAME = "artcb-ovh-node-4"
OVH_BASE = "https://eu.api.ovh.com/1.0"
FORBIDDEN_IPS = frozenset({"152.228.144.34", "151.80.107.29"})


def _creds() -> dict[str, str]:
    local = parse_env_file(local_env_path("ovh-node-4"))
    out = {
        "OVH_APPLICATION_KEY": local.get("OVH_APPLICATION_KEY") or "",
        "OVH_APPLICATION_SECRET": local.get("OVH_APPLICATION_SECRET") or "",
        "OVH_CONSUMER_KEY": local.get("OVH_CONSUMER_KEY") or "",
    }
    token = (
        (os.environ.get("KEY_API_ARTCB_DOPPLER_4") or "").strip()
        or local.get("KEY_API_ARTCB_DOPPLER_4")
        or local.get("DOPPLER_TOKEN")
        or ""
    ).strip()
    if token:
        req = Request(
            "https://api.doppler.com/v3/configs/config/secrets?project=artcb-4&config=dev",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode())
            secrets = payload.get("secrets") or {}
            for name in ("OVH_APPLICATION_KEY", "OVH_APPLICATION_SECRET", "OVH_CONSUMER_KEY"):
                meta = secrets.get(name) or {}
                raw = str(meta.get("computed") or meta.get("raw") or "").strip() if isinstance(meta, dict) else ""
                if raw:
                    out[name] = raw
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
    return out


def ovh(method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
    creds = _creds()
    ak, as_, ck = creds["OVH_APPLICATION_KEY"], creds["OVH_APPLICATION_SECRET"], creds["OVH_CONSUMER_KEY"]
    if not (ak and as_ and ck):
        return 0, {"error": "missing_ovh4_creds"}
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
            parsed: Any = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


def ensure_ssh_key() -> dict[str, Any]:
    priv = Path.home() / ".ssh" / "artcb_ovh_node_4"
    pub = Path.home() / ".ssh" / "artcb_ovh_node_4.pub"
    Path.home().joinpath(".ssh").mkdir(mode=0o700, exist_ok=True)
    if not priv.is_file():
        proc = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(priv), "-N", "", "-C", "artcb-ovh-node-4"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return {"ok": False, "reason": "ssh-keygen_failed"}
        priv.chmod(0o600)
    repo_pub = ROOT / "deploy" / "artcb_ovh_node_4.pub"
    if pub.is_file():
        repo_pub.write_text(pub.read_text(encoding="utf-8"), encoding="utf-8")
    material = pub.read_text(encoding="utf-8").strip()
    code, keys = ovh("GET", f"/cloud/project/{PROJECT_ID}/sshkey")
    existing_id = None
    if isinstance(keys, list):
        for k in keys:
            if k.get("name") == SSH_KEY_NAME:
                existing_id = k.get("id")
                break
    if existing_id:
        return {"ok": True, "ssh_key_id": existing_id, "created": False}
    ccode, created = ovh(
        "POST",
        f"/cloud/project/{PROJECT_ID}/sshkey",
        {"name": SSH_KEY_NAME, "publicKey": material},
    )
    kid = created.get("id") if isinstance(created, dict) else None
    return {
        "ok": bool(kid),
        "ssh_key_id": kid,
        "created": True,
        "http": ccode,
        "body_keys": sorted((created or {}).keys()) if isinstance(created, dict) else [],
    }


def _pick_flavor_image() -> tuple[str | None, str | None]:
    _fcode, flavors = ovh("GET", f"/cloud/project/{PROJECT_ID}/flavor?region={REGION}")
    flavor_id = None
    if isinstance(flavors, list):
        for f in flavors:
            if f.get("name") == FLAVOR_NAME and f.get("available"):
                flavor_id = f.get("id")
                break
    _icode, images = ovh("GET", f"/cloud/project/{PROJECT_ID}/image?region={REGION}&osType=linux")
    image_id = None
    if isinstance(images, list):
        for im in images:
            if im.get("name") == IMAGE_NAME and im.get("status") == "active":
                image_id = im.get("id")
                break
    return flavor_id, image_id


def existing_instance() -> dict[str, Any] | None:
    code, inst = ovh("GET", f"/cloud/project/{PROJECT_ID}/instance")
    if code != 200 or not isinstance(inst, list):
        return None
    for it in inst:
        if it.get("name") in {INSTANCE_NAME, "node artcb ovh 4", "node artcb 4"}:
            return it
        if it.get("id") and (it.get("name") or "").startswith("node-artcb-ovh-4"):
            return it
    return None


def _public_ip(it: dict[str, Any]) -> str | None:
    addrs = it.get("ipAddresses") or []
    ipv4 = None
    if isinstance(addrs, list):
        for a in addrs:
            if not isinstance(a, dict):
                continue
            ip = a.get("ip")
            ver = a.get("version")
            typ = (a.get("type") or "").lower()
            if ip and (ver in (4, "4") or (ip and "." in str(ip) and ":" not in str(ip))):
                if str(ip) in FORBIDDEN_IPS:
                    continue
                if typ in {"public", "", "ext-net"} or ipv4 is None:
                    ipv4 = str(ip)
    return ipv4


def wait_active(instance_id: str, timeout: int = 360) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        code, it = ovh("GET", f"/cloud/project/{PROJECT_ID}/instance/{instance_id}")
        if isinstance(it, dict):
            last = {
                "http": code,
                "id": it.get("id"),
                "name": it.get("name"),
                "status": it.get("status"),
                "region": it.get("region"),
                "public_ip": _public_ip(it),
            }
            if it.get("status") == "ACTIVE" and last.get("public_ip"):
                return last
        time.sleep(8)
    last["wait_timeout"] = True
    return last


def _append_local(ip: str, instance_id: str) -> None:
    if ip in FORBIDDEN_IPS:
        raise SystemExit("refusing to bind ovh-node-4 to OVH1/OVH2 IP")
    path = local_env_path("ovh-node-4")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = parse_env_file(path)
    existing["OVH_CLOUD_PROJECT_ID"] = PROJECT_ID
    existing["OVH_SERVER_IP"] = ip
    existing["OVH_INSTANCE_ID"] = instance_id
    existing["OVH_SERVER_USER"] = "ubuntu"
    existing["OVH_REGION"] = REGION
    existing["OVH_NIC"] = "xy4589-ovh"
    existing["DOPPLER_PROJECT"] = "artcb-4"
    existing["DOPPLER_CONFIG"] = "dev"
    lines = [f"{k}={v}" for k, v in existing.items() if v]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def diagnose() -> dict[str, Any]:
    spec = NODES["ovh-node-4"]
    me_code, me = ovh("GET", "/me")
    p_code, projects = ovh("GET", "/cloud/project")
    i_code, inst = ovh("GET", f"/cloud/project/{PROJECT_ID}/instance")
    me_pub = {}
    if isinstance(me, dict):
        me_pub = {"nichandle": me.get("nichandle"), "email": me.get("email"), "state": me.get("state")}
    return {
        "node_id": spec.node_id,
        "doppler_project": spec.doppler_project,
        "project_id": PROJECT_ID,
        "region": REGION,
        "flavor": FLAVOR_NAME,
        "me_http": me_code,
        "me": me_pub,
        "projects_http": p_code,
        "project_listed": PROJECT_ID in (projects or []) if isinstance(projects, list) else False,
        "instances_http": i_code,
        "instance_count": len(inst) if isinstance(inst, list) else None,
        "secrets_printed": False,
        "launched": False,
        "ovh1_untouched": True,
        "ovh2_untouched": True,
        "used_process_ovh_env": False,
    }


def launch(diag: dict[str, Any]) -> dict[str, Any]:
    found = existing_instance()
    if found and found.get("id"):
        waited = wait_active(found["id"])
        ip = waited.get("public_ip") or _public_ip(found)
        if ip:
            _append_local(str(ip), str(found["id"]))
        diag.update(
            {
                "launched": False,
                "reused": True,
                "instance_id": found.get("id"),
                "public_ip": ip,
                "status": waited.get("status") or found.get("status"),
            }
        )
        return diag
    key = ensure_ssh_key()
    if not key.get("ok"):
        diag.update({"launched": False, "reason": "ssh_key_failed", "ssh_key": {k: v for k, v in key.items() if k != "publicKey"}})
        return diag
    flavor_id, image_id = _pick_flavor_image()
    if not flavor_id or not image_id:
        diag.update({"launched": False, "reason": "flavor_or_image_missing", "flavor_id": flavor_id, "image_id": image_id})
        return diag
    body = {
        "flavorId": flavor_id,
        "imageId": image_id,
        "monthlyBilling": False,
        "name": INSTANCE_NAME,
        "region": REGION,
        "sshKeyId": key["ssh_key_id"],
    }
    code, created = ovh("POST", f"/cloud/project/{PROJECT_ID}/instance", body)
    iid = created.get("id") if isinstance(created, dict) else None
    if not iid:
        diag.update(
            {
                "launched": False,
                "reason": "run_instance_failed",
                "http": code,
                "body_keys": sorted(created.keys()) if isinstance(created, dict) else [],
                "error": (created.get("message") or created.get("errorCode")) if isinstance(created, dict) else None,
            }
        )
        return diag
    waited = wait_active(iid)
    ip = waited.get("public_ip")
    if ip:
        _append_local(str(ip), str(iid))
    diag.update(
        {
            "launched": True,
            "reused": False,
            "instance_id": iid,
            "public_ip": ip,
            "status": waited.get("status"),
            "flavor_id": flavor_id,
            "image_id": image_id,
            "ssh_key_id": key.get("ssh_key_id"),
            "create_http": code,
        }
    )
    return diag


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    diag = diagnose()
    if args.yes and diag.get("me_http") == 200 and diag.get("project_listed"):
        diag = launch(diag)
    print(json.dumps(diag, indent=2, sort_keys=True, default=str))
    if diag.get("launched") or diag.get("reused"):
        return 0
    return 0 if diag.get("me_http") == 200 else 3


if __name__ == "__main__":
    raise SystemExit(main())
