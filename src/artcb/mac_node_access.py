"""mac-node-local SSH/Doppler access — fail-closed, never prints key material.

Observer/dev only. Not an official PBFT replica.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import stat
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from artcb.node_registry import NODES, OFFICIAL_COMPUTE_IPV4, OFFICIAL_COMPUTE_NODE_IDS, SHARED_DOPPLER_PROJECT

MAC_NODE_ID = "mac-node-local"
KEY_PATH_DEFAULT = Path("/tmp/cursor_mac")
SHARED_CONFIG_CURSOR_CLOUD = "dev"
TOKEN_ENV = "KEY_API_ARTCB_DOPPLER_MAC"
SSH_SECRET_NAME = "CURSOR_SSH_PRIVATE_KEY"


def mac_spec():
    return NODES[MAC_NODE_ID]


def is_rfc1918(host: str) -> bool:
    raw = (host or "").strip()
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return bool(addr.is_private)


def mac_is_official_compute() -> bool:
    spec = mac_spec()
    return spec.node_id in OFFICIAL_COMPUTE_NODE_IDS or (spec.ssh_host or "") in OFFICIAL_COMPUTE_IPV4


def token_present() -> bool:
    return bool((os.environ.get(TOKEN_ENV) or "").strip())


def _doppler_get(url: str, token: str, timeout: float = 20) -> tuple[int, Any]:
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read()[:400].decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return int(exc.code), parsed
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return 0, {"error": type(exc).__name__}


def doppler_secret_names(token: str, project: str, config: str) -> dict[str, Any]:
    url = (
        "https://api.doppler.com/v3/configs/config/secrets/names"
        f"?project={quote(project)}&config={quote(config)}"
    )
    status, payload = _doppler_get(url, token)
    names = payload.get("names") if isinstance(payload, dict) else None
    if not isinstance(names, list):
        names = []
    return {
        "http": status,
        "n_names": len(names),
        "has_key_api_artcb_doppler_mac": TOKEN_ENV in names,
        "has_cursor_ssh_private_key": SSH_SECRET_NAME in names,
        "error": None if status == 200 else payload,
    }


def fetch_named_secret(token: str, project: str, config: str, name: str) -> tuple[int, str]:
    """Return (http_status, value). Value is never logged by callers."""
    url = (
        "https://api.doppler.com/v3/configs/config/secret"
        f"?project={quote(project)}&config={quote(config)}&name={quote(name)}"
    )
    status, payload = _doppler_get(url, token)
    if status != 200 or not isinstance(payload, dict):
        return status, ""
    value = (
        (payload.get("value") or {}).get("computed")
        or (payload.get("value") or {}).get("raw")
        or payload.get("computed")
        or ""
    )
    return status, str(value).strip()


def looks_like_private_key(raw: str) -> bool:
    return "BEGIN" in raw and "PRIVATE" in raw and "END" in raw


def write_key_file(raw: str, dest: Path = KEY_PATH_DEFAULT) -> dict[str, Any]:
    dest.parent.mkdir(mode=0o700, exist_ok=True)
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    dest.write_text(text, encoding="utf-8")
    dest.chmod(stat.S_IRUSR | stat.S_IWUSR)
    mode = dest.stat().st_mode & 0o777
    return {"path": str(dest), "bytes": dest.stat().st_size, "mode": oct(mode), "written": True}


def probe_tcp(host: str, port: int, timeout: float = 5.0) -> dict[str, Any]:
    sock = socket.socket()
    sock.settimeout(timeout)
    t0 = time.time()
    try:
        sock.connect((host, port))
        return {"host": host, "port": port, "ok": True, "error": None, "dur_s": round(time.time() - t0, 3)}
    except Exception as exc:
        return {
            "host": host,
            "port": port,
            "ok": False,
            "error": type(exc).__name__,
            "dur_s": round(time.time() - t0, 3),
        }
    finally:
        sock.close()


def try_ssh(dest: Path, user: str, host: str, timeout: int = 8) -> dict[str, Any]:
    cmd = [
        "ssh",
        "-i",
        str(dest),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"ConnectTimeout={timeout}",
        f"{user}@{host}",
        "printf ssh_ok",
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 4)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        # Never leak key material if ssh echoes paths only.
        return {
            "attempted": True,
            "returncode": proc.returncode,
            "dur_s": round(time.time() - t0, 3),
            "stdout_ok": out == "ssh_ok",
            "stderr_class": _classify_ssh_stderr(err),
        }
    except subprocess.TimeoutExpired:
        return {"attempted": True, "returncode": None, "dur_s": round(time.time() - t0, 3), "stdout_ok": False, "stderr_class": "TimeoutExpired"}
    except FileNotFoundError:
        return {"attempted": False, "returncode": None, "dur_s": 0, "stdout_ok": False, "stderr_class": "ssh_binary_absent"}


def _classify_ssh_stderr(err: str) -> str:
    low = err.lower()
    if "timed out" in low or "timeout" in low:
        return "timeout"
    if "connection refused" in low:
        return "refused"
    if "permission denied" in low:
        return "permission_denied"
    if "could not resolve" in low or "name or service not known" in low:
        return "dns"
    if not err:
        return "empty"
    return "other"


def json_contains_private_key(payload: Any) -> bool:
    blob = json.dumps(payload, default=str)
    return "BEGIN" in blob and "PRIVATE" in blob


def probe_mac_access(
    *,
    write_key: bool = True,
    dest: Path = KEY_PATH_DEFAULT,
    tcp_timeout: float = 5.0,
) -> dict[str, Any]:
    spec = mac_spec()
    host = spec.ssh_host or ""
    result: dict[str, Any] = {
        "node_id": spec.node_id,
        "official_compute": mac_is_official_compute(),
        "rfc1918": is_rfc1918(host),
        "ssh_host": host,
        "ssh_user": spec.ssh_user,
        "health_http": spec.health_http,
        "doppler_project": spec.doppler_project,
        "doppler_config": spec.doppler_config,
        "token_env": TOKEN_ENV,
        "token_present": token_present(),
        "shared_doppler_project": SHARED_DOPPLER_PROJECT,
        "shared_doppler_config_probed": SHARED_CONFIG_CURSOR_CLOUD,
        "certified_100": False,
        "ssh": {"attempted": False},
        "key_file": {"written": False},
        "tcp": {},
        "doppler": {},
        "verdict": {},
    }
    tcp22 = probe_tcp(host, 22, timeout=tcp_timeout)
    tcp8001 = probe_tcp(host, 8001, timeout=tcp_timeout)
    result["tcp"] = {"ssh_22": tcp22, "health_8001": tcp8001}

    shared_token = (os.environ.get("DOPPLER_TOKEN") or "").strip()
    if shared_token:
        result["doppler"]["artcb_blockchain_dev"] = doppler_secret_names(
            shared_token, SHARED_DOPPLER_PROJECT, SHARED_CONFIG_CURSOR_CLOUD
        )
        result["doppler"]["artcb_blockchain_prd"] = doppler_secret_names(
            shared_token, SHARED_DOPPLER_PROJECT, "prd"
        )
    else:
        result["doppler"]["artcb_blockchain_dev"] = {"http": 0, "error": "DOPPLER_TOKEN_absent"}

    mac_token = (os.environ.get(TOKEN_ENV) or "").strip()
    if mac_token:
        result["doppler"]["artcb_1_prd"] = doppler_secret_names(mac_token, spec.doppler_project, spec.doppler_config)
        http_st, pem = fetch_named_secret(mac_token, spec.doppler_project, spec.doppler_config, SSH_SECRET_NAME)
        result["doppler"]["cursor_ssh_private_key_http"] = http_st
        result["doppler"]["cursor_ssh_private_key_looks_like_key"] = looks_like_private_key(pem)
        if write_key and looks_like_private_key(pem):
            result["key_file"] = write_key_file(pem, dest)
            result["ssh"] = try_ssh(dest, spec.ssh_user, host)
        elif write_key:
            result["key_file"] = {"written": False, "reason": "secret_missing_or_not_a_key"}
    else:
        result["doppler"]["artcb_1_prd"] = {"http": 0, "error": f"{TOKEN_ENV}_absent"}
        result["key_file"] = {"written": False, "reason": f"{TOKEN_ENV}_absent"}

    token_ok = bool(result["token_present"])
    names_dev = result["doppler"].get("artcb_blockchain_dev") or {}
    token_in_shared_dev = bool(names_dev.get("has_key_api_artcb_doppler_mac"))
    lan_ok = bool(tcp22["ok"] and tcp8001["ok"])
    ssh_ok = bool((result.get("ssh") or {}).get("stdout_ok"))
    result["verdict"] = {
        "credentials_path": "PASS" if token_ok and looks_like_key_written(result) else "FAIL",
        "token_in_cursor_env": "PASS" if token_ok else "FAIL",
        "token_in_artcb_blockchain_dev": "PASS" if token_in_shared_dev else "FAIL",
        "lan_path": "PASS" if lan_ok else "NOT_REACHABLE",
        "ssh_login": "PASS" if ssh_ok else "FAIL",
        "mac_health_sha": None,
        "note": (
            "Do not invent a Mac health SHA. Cursor cloud DOPPLER_TOKEN is "
            "artcb-blockchain/dev. KEY_API_ARTCB_DOPPLER_MAC must be a Cursor "
            "environment secret like _2/_3/_4. 10.234.49.2 is RFC1918."
        ),
    }
    if json_contains_private_key(result):
        raise RuntimeError("probe JSON leaked private-key material — abort")
    return result


def looks_like_key_written(result: dict[str, Any]) -> bool:
    kf = result.get("key_file") or {}
    return bool(kf.get("written")) and int(kf.get("bytes") or 0) > 80
