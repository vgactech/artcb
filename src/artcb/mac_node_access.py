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
TUNNEL_SSH_ENV = "ARTCB_MAC_TUNNEL_SSH_HOST"
TUNNEL_HTTP_ENV = "ARTCB_MAC_TUNNEL_HEALTH_HTTP"


def mac_spec():
    return NODES[MAC_NODE_ID]


def is_rfc1918(host: str) -> bool:
    raw = (host or "").strip()
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return bool(addr.is_private)


def host_from_url_or_host(raw: str) -> str:
    text = (raw or "").strip()
    if "://" in text:
        from urllib.parse import urlparse

        return (urlparse(text).hostname or "").strip().lower()
    if text.count(":") == 1 and text.rsplit(":", 1)[-1].isdigit():
        return text.rsplit(":", 1)[0].strip().lower()
    return text.lower().rstrip(".")


def is_lan_only_host(host: str) -> bool:
    """True for RFC1918, loopback, mDNS .local — not a cloud-reachable path."""
    h = host_from_url_or_host(host)
    if not h:
        return True
    if h in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return True
    if h.endswith(".local") or h.endswith(".lan"):
        return True
    return is_rfc1918(h)


def select_cloud_remote(spec=None, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Pick SSH/health target for a cloud agent. RFC1918 is never a tunnel."""
    spec = spec or mac_spec()
    environ = env if env is not None else os.environ
    lan_ssh = spec.ssh_host or ""
    lan_http = spec.health_http or ""
    tunnel_ssh = (environ.get(TUNNEL_SSH_ENV) or spec.tunnel_ssh_host or "").strip()
    tunnel_http = (environ.get(TUNNEL_HTTP_ENV) or spec.tunnel_health_http or "").strip()
    ssh_host = host_from_url_or_host(tunnel_ssh) if tunnel_ssh else ""
    if ssh_host and is_lan_only_host(ssh_host):
        return {
            "ok": False,
            "reason": "tunnel_host_is_lan_only",
            "ssh_host": None,
            "health_http": None,
            "tunnel_required": True,
            "lan_ssh_host": lan_ssh,
            "rejected": ssh_host,
        }
    if ssh_host:
        http = tunnel_http or None
        return {
            "ok": True,
            "reason": "public_tunnel",
            "ssh_host": ssh_host,
            "health_http": http,
            "tunnel_required": True,
            "lan_ssh_host": lan_ssh,
            "rejected": None,
        }
    if spec.tunnel_required or is_lan_only_host(lan_ssh):
        return {
            "ok": False,
            "reason": "rfc1918_requires_tunnel",
            "ssh_host": None,
            "health_http": None,
            "tunnel_required": True,
            "lan_ssh_host": lan_ssh,
            "rejected": lan_ssh,
        }
    return {
        "ok": True,
        "reason": "direct_public",
        "ssh_host": lan_ssh,
        "health_http": lan_http,
        "tunnel_required": False,
        "lan_ssh_host": lan_ssh,
        "rejected": None,
    }


def list_ngrok_tunnels(api_key: str) -> dict[str, Any]:
    """Public URLs only. Never returns the API key."""
    if not (api_key or "").strip():
        return {"http": 0, "n_tunnels": 0, "n_endpoints": 0, "public_urls": [], "error": "NGROK_API_KEY_absent"}
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Ngrok-Version": "2",
        "Accept": "application/json",
    }
    urls: list[str] = []
    out: dict[str, Any] = {"public_urls": urls, "error": None}

    def _get(path: str) -> tuple[int, Any]:
        req = Request(f"https://api.ngrok.com{path}", headers=headers)
        try:
            with urlopen(req, timeout=20) as resp:
                return int(resp.status), json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            return int(exc.code), {"error": exc.read()[:200].decode("utf-8", errors="replace")}
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return 0, {"error": type(exc).__name__}

    st, tunnels_body = _get("/tunnels")
    out["tunnels_http"] = st
    items = []
    if isinstance(tunnels_body, dict):
        items = tunnels_body.get("tunnels") or []
    out["n_tunnels"] = len(items) if isinstance(items, list) else 0
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict):
            u = item.get("public_url") or item.get("url")
            if u:
                urls.append(str(u))
    st2, eps_body = _get("/endpoints")
    out["endpoints_http"] = st2
    eps = []
    if isinstance(eps_body, dict):
        eps = eps_body.get("endpoints") or []
    out["n_endpoints"] = len(eps) if isinstance(eps, list) else 0
    for item in eps if isinstance(eps, list) else []:
        if isinstance(item, dict):
            u = item.get("url") or item.get("hostport")
            if u:
                urls.append(str(u))
    out["public_urls"] = urls
    out["n_public"] = len(urls)
    return out


def probe_mac_tunnel(*, tcp_timeout: float = 5.0, ngrok_api_key: str | None = None) -> dict[str, Any]:
    spec = mac_spec()
    remote = select_cloud_remote(spec)
    lan_url = spec.health_http or f"http://{spec.ssh_host}:8001"
    ngrok = list_ngrok_tunnels(ngrok_api_key or "")
    tcp = {}
    if remote.get("ok") and remote.get("ssh_host"):
        tcp["tunnel_ssh"] = probe_tcp(str(remote["ssh_host"]), 22, timeout=tcp_timeout)
    result = {
        "node_id": spec.node_id,
        "tunnel_required": True,
        "official_compute": mac_is_official_compute(),
        "certified_100": False,
        "lan_ssh_host": spec.ssh_host,
        "lan_only": is_lan_only_host(spec.ssh_host or ""),
        "lan_health_http": lan_url,
        "remote": remote,
        "ngrok": {
            "tunnels_http": ngrok.get("tunnels_http"),
            "endpoints_http": ngrok.get("endpoints_http"),
            "n_tunnels": ngrok.get("n_tunnels"),
            "n_endpoints": ngrok.get("n_endpoints"),
            "n_public": ngrok.get("n_public"),
            "public_hosts": [host_from_url_or_host(u) for u in ngrok.get("public_urls") or []],
            "error": ngrok.get("error"),
        },
        "tcp": tcp,
        "verdict": {
            "rfc1918_lan": "NOT_REACHABLE_FROM_CLOUD",
            "tunnel": "PASS" if remote.get("ok") else "ABSENT",
            "ngrok_account_tunnels": "ABSENT" if int(ngrok.get("n_public") or 0) == 0 else "PRESENT",
            "mac_health_sha": None,
            "note": (
                "10.234.49.2 is RFC1918. Cloud VMs and Cursor cloud agents need a "
                "tunnel started on the Mac. Starting ngrok on a cloud VM does not "
                "reach the Mac. Do not invent a Mac health SHA."
            ),
        },
    }
    if json_contains_private_key(result):
        raise RuntimeError("tunnel probe JSON leaked secret material — abort")
    return result


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
            remote = select_cloud_remote(spec)
            result["remote"] = remote
            if remote.get("ok") and remote.get("ssh_host"):
                result["ssh"] = try_ssh(dest, spec.ssh_user, str(remote["ssh_host"]))
            else:
                result["ssh"] = {"attempted": False, "stderr_class": remote.get("reason") or "rfc1918_requires_tunnel"}
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
    remote = result.get("remote") or select_cloud_remote(spec)
    result["remote"] = remote
    result["tunnel_required"] = True
    result["verdict"] = {
        "credentials_path": "PASS" if token_ok and looks_like_key_written(result) else "FAIL",
        "token_in_cursor_env": "PASS" if token_ok else "FAIL",
        "token_in_artcb_blockchain_dev": "PASS" if token_in_shared_dev else "FAIL",
        "lan_path": "PASS" if lan_ok else "NOT_REACHABLE",
        "tunnel": "PASS" if remote.get("ok") else "ABSENT",
        "ssh_login": "PASS" if ssh_ok else "FAIL",
        "mac_health_sha": None,
        "note": (
            "Do not invent a Mac health SHA. Cursor cloud DOPPLER_TOKEN is "
            "artcb-blockchain/dev. KEY_API_ARTCB_DOPPLER_MAC must be a Cursor "
            "environment secret like _2/_3/_4. 10.234.49.2 is RFC1918 — a tunnel "
            "started on the Mac is required for cloud access."
        ),
    }
    if json_contains_private_key(result):
        raise RuntimeError("probe JSON leaked private-key material — abort")
    return result


def looks_like_key_written(result: dict[str, Any]) -> bool:
    kf = result.get("key_file") or {}
    return bool(kf.get("written")) and int(kf.get("bytes") or 0) > 80
