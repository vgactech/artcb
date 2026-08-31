"""Live OVH node resolution for Cursor / CI agents.

Never logs or prints secret values. Key sources, in order:

1. Process env ``ARTCB_API_KEY`` / ``ARTCB_NODE_API_KEY`` (Cursor secrets)
2. Doppler ``ARTCB_API_KEY`` (same project as ``DOPPLER_TOKEN``)
3. Local file ``~/.artcb/cursor_agent.env`` (copied from the node)
4. SSH ``ubuntu@152.228.144.34`` file ``/home/ubuntu/.artcb/cursor_agent.env``

Default public URL (not a secret): ``https://152.228.144.34:8443`` (Bearer).
Health without a key may use ``http://152.228.144.34:8000``.
Doppler: shared app secrets stay in ``artcb-blockchain``; each real node has its
own project (see ``artcb.node_registry``).
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import stat
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from artcb.node_registry import (
    SHARED_DOPPLER_CONFIG,
    SHARED_DOPPLER_PROJECT,
    doppler_project_for,
    doppler_token_env_for,
    get_node,
)

logger = logging.getLogger("artcb.live")

DEFAULT_LIVE_URL = "http://152.228.144.34:8000"
DEFAULT_LIVE_HTTPS_URL = "https://152.228.144.34:8443"
DEFAULT_SSH_HOST = "152.228.144.34"
DEFAULT_SSH_USER = "ubuntu"
KNOWN_HOSTS = Path(__file__).resolve().parents[2] / "deploy" / "ovh_artcb_node_1.known_hosts"
PINNED_TLS_CERT = Path(__file__).resolve().parents[2] / "deploy" / "ovh_artcb_node_1.crt"
REMOTE_ENV_PATH = "/home/ubuntu/.artcb/cursor_agent.env"
DOPPLER_PROJECT = SHARED_DOPPLER_PROJECT
DOPPLER_CONFIG = SHARED_DOPPLER_CONFIG
KEY_ENV_NAMES = ("ARTCB_API_KEY", "ARTCB_NODE_API_KEY")
URL_ENV_NAMES = ("ARTCB_API_URL", "ARTCB_NODE_URL")


def local_env_path() -> Path:
    return Path.home() / ".artcb" / "cursor_agent.env"


def resolve_api_url() -> str:
    for name in URL_ENV_NAMES:
        raw = (os.environ.get(name) or "").strip()
        if raw:
            return raw.rstrip("/")
    # Bearer must not go over cleartext HTTP. Default to pinned HTTPS.
    return DEFAULT_LIVE_HTTPS_URL.rstrip("/")


def _key_from_mapping(mapping: dict[str, str]) -> str:
    for name in KEY_ENV_NAMES:
        raw = (mapping.get(name) or "").strip()
        if raw.startswith("artcb_"):
            return raw
    return ""


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def resolve_api_key() -> str:
    found = _key_from_mapping({n: os.environ.get(n, "") for n in KEY_ENV_NAMES})
    if found:
        return found
    local = parse_env_file(local_env_path())
    return _key_from_mapping(local)


def apply_key_to_environ(key: str) -> None:
    if not key.startswith("artcb_"):
        raise ValueError("ARTCB API key must start with artcb_")
    os.environ["ARTCB_API_KEY"] = key


def auth_headers(api_key: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = api_key or resolve_api_key()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def resolve_doppler_project() -> str:
    """Shared project unless ARTCB_NODE_ID / DOPPLER_PROJECT selects a node vault."""
    explicit = (os.environ.get("DOPPLER_PROJECT") or "").strip()
    if explicit:
        return explicit
    node_id = (os.environ.get("ARTCB_NODE_ID") or "").strip()
    if node_id:
        try:
            return doppler_project_for(node_id)
        except KeyError:
            pass
    return DOPPLER_PROJECT


def resolve_doppler_token() -> str:
    """Service token for the selected node vault. Never logs the value."""
    node_id = (os.environ.get("ARTCB_NODE_ID") or "").strip()
    if node_id:
        try:
            env_name = doppler_token_env_for(node_id)
            raw = (os.environ.get(env_name) or "").strip()
            if raw:
                return raw
        except KeyError:
            pass
    return (os.environ.get("DOPPLER_TOKEN") or "").strip()


def resolve_doppler_config() -> str:
    node_id = (os.environ.get("ARTCB_NODE_ID") or "").strip()
    if node_id:
        try:
            return get_node(node_id).doppler_config
        except KeyError:
            pass
    return os.environ.get("DOPPLER_CONFIG", DOPPLER_CONFIG) or DOPPLER_CONFIG


def fetch_doppler_secret(name: str) -> str:
    token = resolve_doppler_token()
    if not token:
        return ""
    project = resolve_doppler_project()
    config = os.environ.get("DOPPLER_CONFIG") or resolve_doppler_config()
    url = (
        "https://api.doppler.com/v3/configs/config/secret"
        f"?project={project}&config={config}&name={name}"
    )
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return ""
    value = (
        (payload.get("value") or {}).get("computed")
        or (payload.get("value") or {}).get("raw")
        or payload.get("computed")
        or ""
    )
    return str(value).strip()


def write_doppler_secrets(secrets: dict[str, str]) -> dict[str, Any]:
    """Best-effort write. Never uploads AWS_CONSOLE_PASSWORD."""
    secrets = {k: v for k, v in secrets.items() if k != "AWS_CONSOLE_PASSWORD" and not k.startswith("DOPPLER_")}
    token = resolve_doppler_token()
    if not token:
        return {"ok": False, "reason": "DOPPLER_TOKEN absent"}
    project = resolve_doppler_project()
    config = os.environ.get("DOPPLER_CONFIG") or resolve_doppler_config()
    body = json.dumps({"project": project, "config": config, "secrets": secrets}).encode()
    last_reason = "unknown"
    for method in ("POST", "PUT"):
        req = Request(
            "https://api.doppler.com/v3/configs/config/secrets",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "method": method, "success": bool(payload.get("success", True))}
        except HTTPError as exc:
            last_reason = f"{method} HTTP {exc.code}"
            continue
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_reason = f"{method} {type(exc).__name__}"
            continue
    return {"ok": False, "reason": last_reason}


def write_local_env(mapping: dict[str, str]) -> Path:
    dest = local_env_path()
    dest.parent.mkdir(mode=0o700, exist_ok=True)
    lines = [f"{k}={v}" for k, v in mapping.items() if v]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dest.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return dest


def ensure_ovh_ssh_key() -> Path | None:
    dest = Path.home() / ".ssh" / "artcb_ovh_deploy"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    script = Path(__file__).resolve().parents[2] / "scripts" / "load_ovh_ssh_from_doppler.py"
    if not script.is_file():
        return dest if dest.is_file() else None
    try:
        subprocess.run(["python3", str(script)], check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return dest if dest.is_file() else None
    return dest if dest.is_file() else None


def pull_remote_agent_env() -> dict[str, str]:
    """Copy the node-side env file over SSH. Never prints values."""
    key_path = ensure_ovh_ssh_key()
    if key_path is None:
        return {}
    dest = local_env_path()
    dest.parent.mkdir(mode=0o700, exist_ok=True)
    cmd = [
        "scp",
        "-i",
        str(key_path),
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS}" if KNOWN_HOSTS.is_file() else "StrictHostKeyChecking=accept-new",
        "-o",
        "StrictHostKeyChecking=yes" if KNOWN_HOSTS.is_file() else "StrictHostKeyChecking=accept-new",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        f"{DEFAULT_SSH_USER}@{DEFAULT_SSH_HOST}:{REMOTE_ENV_PATH}",
        str(dest),
    ]
    try:
        completed = subprocess.run(cmd, check=False, timeout=30, capture_output=True, text=True)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if completed.returncode != 0:
        logger.info("scp cursor_agent.env failed rc=%s", completed.returncode)
        return {}
    dest.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return parse_env_file(dest)


def tls_context(url: str) -> ssl.SSLContext | None:
    if not url.startswith("https://"):
        return None
    ctx = ssl.create_default_context()
    if PINNED_TLS_CERT.is_file():
        ctx.load_verify_locations(cafile=str(PINNED_TLS_CERT))
        ctx.check_hostname = False
    return ctx


class LiveSecurityError(RuntimeError):
    """Live operation refused (HTTP bearer, localhost while required, missing bootstrap)."""


def assert_live_transport(url: str, *, sending_bearer: bool) -> None:
    """Refuse sending an API key over cleartext HTTP unless explicitly allowed."""
    allow = os.environ.get("ARTCB_ALLOW_INSECURE_HTTP", "").lower() in {"1", "true", "yes"}
    if sending_bearer and url.startswith("http://") and not allow:
        raise LiveSecurityError(
            f"Refuse Bearer over HTTP ({url}). Use HTTPS or set ARTCB_ALLOW_INSECURE_HTTP=1 for localhost/dev."
        )
    required = os.environ.get("ARTCB_LIVE_REQUIRED", "").lower() in {"1", "true", "yes"}
    if required and ("localhost" in url or "127.0.0.1" in url):
        raise LiveSecurityError(f"ARTCB_LIVE_REQUIRED forbids localhost URL {url}")


def write_bootstrap_stamp(payload: dict[str, Any]) -> Path:
    dest = Path.home() / ".artcb" / "bootstrap_ok.json"
    dest.parent.mkdir(mode=0o700, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dest.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return dest


def http_json(method: str, url: str, *, api_key: str | None = None, body: dict | None = None) -> tuple[int, Any]:
    token = api_key or resolve_api_key()
    if token:
        try:
            assert_live_transport(url, sending_bearer=True)
        except LiveSecurityError as exc:
            return 0, {"error": "LiveSecurityError", "detail": str(exc)}
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, method=method, headers=auth_headers(token or None))
    ctx = tls_context(url)
    try:
        with urlopen(req, timeout=20, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail[:200]}
        return exc.code, parsed
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}
