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


def _token_for_node(node_id: str) -> str:
    spec = NODES[node_id]
    return (os.environ.get(spec.doppler_token_env) or "").strip() or _token()


RESERVED_SECRET_NAMES = frozenset({"DOPPLER_PROJECT", "DOPPLER_CONFIG", "DOPPLER_ENVIRONMENT", "AWS_CONSOLE_PASSWORD"})


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


def set_secrets(project: str, config: str, secrets: dict[str, str], token: str | None = None) -> dict[str, Any]:
    secrets = {k: v for k, v in secrets.items() if k not in RESERVED_SECRET_NAMES and v}
    if not secrets:
        return {"ok": True, "wrote": 0, "names": []}
    code, payload = _api(
        "POST",
        "/v3/configs/config/secrets",
        {"project": project, "config": config, "secrets": secrets},
        token=token,
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


def project_reachable(project: str, token: str) -> dict[str, Any]:
    code, payload = _api("GET", f"/v3/projects/project?project={project}", token=token)
    configs_code, configs_body = _api("GET", f"/v3/configs?project={project}", token=token)
    names = []
    if isinstance(configs_body, dict):
        names = [c.get("name") for c in (configs_body.get("configs") or []) if c.get("name")]
    return {
        "http": code,
        "ok": code == 200,
        "configs_http": configs_code,
        "configs": names,
    }


def bind_existing(spec, token: str) -> dict[str, Any]:
    """Write allowlisted local secrets into an already-created Doppler project."""
    reach = project_reachable(spec.doppler_project, token)
    if not reach["ok"]:
        return {"ok": False, "reachable": reach, "reason": "project_not_visible_to_token"}
    config_name = spec.doppler_config
    if config_name not in (reach.get("configs") or []) and "dev" in (reach.get("configs") or []):
        config_name = "dev"
    bundle: dict[str, str] = {}
    if spec.node_id == "ovh-node-1":
        bundle.update(copy_allowlist_from_shared(spec.node_id))
    bundle.update(secrets_from_local(spec.node_id))
    wrote = set_secrets(spec.doppler_project, config_name, bundle, token=token)
    names_code, names_body = _api(
        "GET",
        f"/v3/configs/config/secrets/names?project={spec.doppler_project}&config={config_name}",
        token=token,
    )
    listed = names_body.get("names") if isinstance(names_body, dict) else []
    return {
        "ok": wrote.get("ok", False) or names_code == 200,
        "reachable": reach,
        "config": config_name,
        "secrets_written": {"ok": wrote["ok"], "count": wrote["wrote"], "names": wrote["names"]},
        "secret_names_http": names_code,
        "secret_names": listed if isinstance(listed, list) else [],
        "stripe_present": any(n in {"KEY_API_STRIPE", "BOB_API_KEY"} for n in (listed or [])),
    }


def provision() -> dict[str, Any]:
    ident = token_identity()
    listed_code, existing = list_projects()
    results: dict[str, Any] = {
        "token": ident,
        "projects_list_http": listed_code,
        "projects_before": existing,
        "created": {},
        "bound": {},
        "blocked": None,
        "shared_project_kept": SHARED_DOPPLER_PROJECT,
        "registry": public_registry(),
    }
    if ident.get("type") == "service_token" or not ident.get("can_create_projects"):
        results["blocked"] = (
            "Doppler service token cannot create NEW projects (403). "
            "Binding user-created slugs artcb-2 / artcb3 via Cursor service tokens. "
            "Dedicated artcb-ovh-node-1 still needs DOPPLER_PERSONAL_TOKEN."
        )
    for spec in NODES.values():
        node_token = _token_for_node(spec.node_id)
        created = create_project(
            spec.doppler_project,
            f"ARTCB {spec.display_name} ({spec.provider}) — isolated from other real nodes",
        )
        results["created"][spec.node_id] = created
        bound = bind_existing(spec, node_token)
        results["bound"][spec.node_id] = bound
        if created["ok"]:
            cfg = ensure_config(spec.doppler_project, spec.doppler_config)
            created["config"] = cfg
            config_name = spec.doppler_config if cfg.get("ok") else "dev"
            bundle = {}
            if spec.node_id == "ovh-node-1":
                bundle.update(copy_allowlist_from_shared(spec.node_id))
            bundle.update(secrets_from_local(spec.node_id))
            wrote = set_secrets(spec.doppler_project, config_name, bundle)
            created["secrets_written"] = {"ok": wrote["ok"], "count": wrote["wrote"], "names": wrote["names"]}
    _, after = list_projects()
    results["projects_after"] = after
    results["isolation"] = {
        "ovh1_vault": NODES["ovh-node-1"].doppler_project,
        "ovh2_vault": NODES["ovh-node-2"].doppler_project,
        "aws3_vault": NODES["aws-node-3"].doppler_project,
        "ovh2_bound": bool((results["bound"].get("ovh-node-2") or {}).get("ok")),
        "aws3_bound": bool((results["bound"].get("aws-node-3") or {}).get("ok")),
        "ovh2_has_stripe": bool((results["bound"].get("ovh-node-2") or {}).get("stripe_present")),
        "aws3_has_stripe": bool((results["bound"].get("aws-node-3") or {}).get("stripe_present")),
    }
    return results


def main() -> int:
    report = provision()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    bound = report.get("bound") or {}
    # Success if OVH2 and AWS3 vaults are reachable (the user-created projects).
    ovh2 = bound.get("ovh-node-2") or {}
    aws3 = bound.get("aws-node-3") or {}
    if ovh2.get("ok") and aws3.get("ok") and not ovh2.get("stripe_present") and not aws3.get("stripe_present"):
        return 0
    created = report.get("created") or {}
    if all(v.get("ok") for v in created.values()) and created:
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
