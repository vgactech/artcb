#!/usr/bin/env python3
"""Create one Doppler project per real ARTCB node (OVH1, OVH2, AWS3).

The Cursor service token ``artcb-node-1`` cannot create projects (403).
Pass ``DOPPLER_PERSONAL_TOKEN`` (personal / workplace) to actually create them.

Never prints secret values. Never writes secrets into the git tree.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.live import parse_env_file  # noqa: E402
from artcb.node_registry import (  # noqa: E402
    NODES,
    SHARED_DOPPLER_CONFIG,
    SHARED_DOPPLER_PROJECT,
    local_env_path,
    public_registry,
    secret_belongs_on_node,
    secret_must_stay_shared,
)


def _token() -> str:
    return (
        (os.environ.get("DOPPLER_PERSONAL_TOKEN") or "").strip()
        or (os.environ.get("DOPPLER_TOKEN") or "").strip()
    )


def _api(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, Any]:
    tok = token or _token()
    if not tok:
        return 0, {"error": "no_doppler_token"}
    data = None if body is None else json.dumps(body).encode()
    req = Request(
        "https://api.doppler.com" + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed: Any = json.loads(detail) if detail else {"detail": detail}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


def token_identity() -> dict[str, Any]:
    code, payload = _api("GET", "/v3/me")
    token = payload.get("token") if isinstance(payload, dict) else {}
    if not isinstance(token, dict):
        token = payload if isinstance(payload, dict) else {}
    return {
        "http": code,
        "name": token.get("name"),
        "type": token.get("type"),
        "workplace": (token.get("workplace") or {}).get("name")
        if isinstance(token.get("workplace"), dict)
        else None,
        "can_create_projects": token.get("type") in {"personal", "cli", "service_account"},
    }


def list_projects() -> tuple[int, list[str]]:
    code, payload = _api("GET", "/v3/projects")
    names = []
    if isinstance(payload, dict):
        for p in payload.get("projects") or []:
            slug = p.get("slug") or p.get("name")
            if slug:
                names.append(str(slug))
    return code, names


def create_project(slug: str, description: str) -> dict[str, Any]:
    code, payload = _api(
        "POST",
        "/v3/projects",
        {"name": slug, "description": description},
    )
    return {"http": code, "ok": code in {200, 201}, "slug": slug, "body_keys": sorted((payload or {}).keys()) if isinstance(payload, dict) else []}


def ensure_config(project: str, name: str = "prd") -> dict[str, Any]:
    code, payload = _api("GET", f"/v3/configs?project={project}")
    configs = []
    if isinstance(payload, dict):
        configs = [c.get("name") for c in (payload.get("configs") or [])]
    if name in configs:
        return {"http": code, "ok": True, "existed": True, "name": name}
    # Default environment is usually "dev" on a new project; try creating prd config.
    code2, payload2 = _api(
        "POST",
        "/v3/configs",
        {"project": project, "environment": "prd", "name": name},
    )
    if code2 not in {200, 201}:
        code3, payload3 = _api(
            "POST",
            "/v3/configs",
            {"project": project, "environment": "dev", "name": name},
        )
        return {"http": code3, "ok": code3 in {200, 201}, "existed": False, "name": name}
    _ = payload2
    return {"http": code2, "ok": True, "existed": False, "name": name}


def set_secrets(project: str, config: str, secrets: dict[str, str]) -> dict[str, Any]:
    if not secrets:
        return {"ok": True, "wrote": 0}
    code, payload = _api(
        "POST",
        "/v3/configs/config/secrets",
        {"project": project, "config": config, "secrets": secrets},
    )
    return {
        "http": code,
        "ok": code in {200, 201},
        "wrote": len(secrets) if code in {200, 201} else 0,
        "names": sorted(secrets),
    }


def secrets_from_local(node_id: str) -> dict[str, str]:
    path = local_env_path(node_id)
    parsed = parse_env_file(path)
    out = {}
    for name, value in parsed.items():
        if name.endswith("PASSWORD") or name.endswith("SECRET") or "KEY" in name or name.endswith("TOKEN"):
            if not value:
                continue
        if secret_must_stay_shared(name):
            continue
        if secret_belongs_on_node(node_id, name) or name in {
            "OVH_NIC",
            "OVH_API_APP_NAME",
            "OVH_CONTACT_EMAIL",
            "AWS_ACCOUNT_ID",
            "AWS_IAM_USER",
            "AWS_CONSOLE_URL",
            "AWS_CLI_PROFILE",
        }:
            out[name] = value
    # Console passwords are local-only — never upload unless explicitly named.
    out.pop("AWS_CONSOLE_PASSWORD", None)
    return out


def copy_allowlist_from_shared(node_id: str) -> dict[str, str]:
    """Copy *names* that belong on this node from the shared project (values not logged)."""
    token = _token()
    code, payload = _api(
        "GET",
        f"/v3/configs/config/secrets?project={SHARED_DOPPLER_PROJECT}&config={SHARED_DOPPLER_CONFIG}",
        token=token,
    )
    if code != 200 or not isinstance(payload, dict):
        return {}
    secrets = payload.get("secrets") or {}
    out: dict[str, str] = {}
    for name, meta in secrets.items():
        if secret_must_stay_shared(name):
            continue
        if not secret_belongs_on_node(node_id, name):
            continue
        if not isinstance(meta, dict):
            continue
        raw = str(meta.get("computed") or meta.get("raw") or "").strip()
        if raw:
            out[name] = raw
    return out


def provision() -> dict[str, Any]:
    ident = token_identity()
    listed_code, existing = list_projects()
    results: dict[str, Any] = {
        "token": ident,
        "projects_list_http": listed_code,
        "projects_before": existing,
        "created": {},
        "blocked": None,
        "shared_project_kept": SHARED_DOPPLER_PROJECT,
        "registry": public_registry(),
    }
    if ident.get("type") == "service_token" or not ident.get("can_create_projects"):
        results["blocked"] = (
            "Doppler service token cannot create projects (403). "
            "Set DOPPLER_PERSONAL_TOKEN (personal/workplace) then re-run."
        )
        # Attempt anyway so the 403 is recorded as evidence.
    for spec in NODES.values():
        created = create_project(
            spec.doppler_project,
            f"ARTCB {spec.display_name} ({spec.provider}) — isolated from other real nodes",
        )
        results["created"][spec.node_id] = created
        if not created["ok"]:
            continue
        cfg = ensure_config(spec.doppler_project, spec.doppler_config)
        created["config"] = cfg
        if not cfg.get("ok"):
            # new projects often ship with config "dev"
            cfg_dev = ensure_config(spec.doppler_project, "dev")
            created["config_dev"] = cfg_dev
            config_name = "dev" if cfg_dev.get("ok") else spec.doppler_config
        else:
            config_name = spec.doppler_config
        bundle = {}
        if spec.node_id == "ovh-node-1":
            bundle.update(copy_allowlist_from_shared(spec.node_id))
        bundle.update(secrets_from_local(spec.node_id))
        wrote = set_secrets(spec.doppler_project, config_name, bundle)
        created["secrets_written"] = {"ok": wrote["ok"], "count": wrote["wrote"], "names": wrote["names"]}
    _, after = list_projects()
    results["projects_after"] = after
    return results


def main() -> int:
    report = provision()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    created = report.get("created") or {}
    if all(v.get("ok") for v in created.values()) and created:
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
