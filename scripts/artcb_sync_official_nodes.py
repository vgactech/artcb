#!/usr/bin/env python3
"""Push follow-main onto the four official VMs and collect a live matrix.

Keep-book only: never install.sh, genesis, init-node, rescue, or wipe blocks.jsonl.
Never prints PEM / Doppler tokens.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.devnet_validation import OPERATOR_MAINNET_CERTIFICATION_GO, certification_gate  # noqa: E402
from artcb.node_registry import (  # noqa: E402
    NODES,
    OFFICIAL_COMPUTE_NODE_IDS,
    PUBLIC_HEALTH_URLS,
)

CTX = ssl._create_unverified_context()
SSH_KEYS = {
    "ovh-node-1": Path.home() / ".ssh" / "artcb_ovh_deploy",
    "ovh-node-2": Path.home() / ".ssh" / "artcb_ovh_node_2",
    "aws-node-3": Path.home() / ".ssh" / "artcb_aws_node_3",
    "ovh-node-4": Path.home() / ".ssh" / "artcb_ovh_node_4",
}
KNOWN = {
    "ovh-node-1": ROOT / "deploy" / "ovh_artcb_node_1.known_hosts",
    "ovh-node-2": ROOT / "deploy" / "ovh_artcb_node_2.known_hosts",
    "aws-node-3": ROOT / "deploy" / "aws_artcb_node_3.known_hosts",
    "ovh-node-4": ROOT / "deploy" / "ovh_artcb_node_4.known_hosts",
}
SHIP_FILES = (
    "scripts/artcb_follow_main.sh",
    "scripts/artcb-follow-main.service",
    "scripts/artcb-follow-main.timer",
    "scripts/install_follow_main.sh",
)


def _http(url: str, timeout: int = 12) -> dict:
    t0 = time.perf_counter()
    req = Request(url, headers={"Accept": "application/json"})
    ctx = CTX if url.startswith("https") else None
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = resp.status
        parsed = json.loads(body) if body.strip().startswith("{") else {"raw": body[:300]}
        keep = {
            k: parsed.get(k)
            for k in (
                "git_sha",
                "git_branch",
                "status",
                "certified_distributed_mainnet",
                "network_id",
                "peer_count",
                "chain_valid",
                "last_hash",
                "height",
                "chain_height",
            )
            if k in parsed
        }
        pqc = parsed.get("pqc")
        if isinstance(pqc, dict):
            keep["pqc_algorithm"] = pqc.get("algorithm")
        return {"url": url, "http": code, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1), **keep}
    except HTTPError as exc:
        return {"url": url, "http": exc.code, "error": "HTTPError", "rtt_ms": round((time.perf_counter() - t0) * 1000, 1)}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "url": url,
            "http": 0,
            "error": type(exc).__name__,
            "rtt_ms": round((time.perf_counter() - t0) * 1000, 1),
        }


def _ssh_base(node_id: str) -> list[str] | None:
    spec = NODES[node_id]
    key = SSH_KEYS[node_id]
    if not key.is_file() or key.stat().st_size < 80:
        return None
    known = KNOWN[node_id]
    known_opts = (
        ["-o", f"UserKnownHostsFile={known}", "-o", "StrictHostKeyChecking=yes"]
        if known.is_file()
        else ["-o", "StrictHostKeyChecking=accept-new"]
    )
    return [
        "-i",
        str(key),
        *known_opts,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        f"{spec.ssh_user}@{spec.ssh_host}",
    ]


def _ssh(node_id: str, remote: str, timeout: int = 180) -> dict:
    base = _ssh_base(node_id)
    if base is None:
        return {"node_id": node_id, "returncode": 2, "stdout": "", "stderr": "missing_ssh_key"}
    proc = subprocess.run(
        ["ssh", *base, remote],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "node_id": node_id,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-8000:],
        "stderr": (proc.stderr or "")[-800:],
    }


def _scp(node_id: str, local: Path, remote: str) -> dict:
    base = _ssh_base(node_id)
    if base is None:
        return {"node_id": node_id, "returncode": 2, "stderr": "missing_ssh_key"}
    # scp uses the same -i / known_hosts / BatchMode flags, host is last-but-one token.
    host = base[-1]
    flags = base[:-1]
    proc = subprocess.run(
        ["scp", *flags, str(local), f"{host}:{remote}"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    return {"node_id": node_id, "file": str(local.name), "returncode": proc.returncode, "stderr": (proc.stderr or "")[-400:]}


def probe_node(node_id: str) -> dict:
    spec = NODES[node_id]
    row: dict = {"node_id": node_id, "ssh_host": spec.ssh_host, "doppler": spec.doppler_project}
    if spec.health_http:
        row["health_http"] = _http(f"{spec.health_http}/health")
    if spec.api_https:
        row["health_https"] = _http(f"{spec.api_https}/health")
    pub = PUBLIC_HEALTH_URLS.get(node_id)
    if pub:
        row["health_domain"] = _http(pub)
    return row


def install_follow_on_node(node_id: str) -> dict:
    spec = NODES[node_id]
    shipped = []
    for rel in SHIP_FILES:
        shipped.append(_scp(node_id, ROOT / rel, f"/home/ubuntu/artcb/{rel}"))
    marker = (
        f"echo {node_id} | sudo tee /etc/artcb/official_node >/dev/null; "
        "sudo chmod 644 /etc/artcb/official_node; "
        "chmod +x /home/ubuntu/artcb/scripts/artcb_follow_main.sh "
        "/home/ubuntu/artcb/scripts/install_follow_main.sh; "
        f"ARTCB_NODE_ID={node_id} ARTCB_FOLLOW_MODE=official "
        "bash /home/ubuntu/artcb/scripts/install_follow_main.sh; "
        "systemctl is-enabled artcb-follow-main.timer || true; "
        "systemctl list-timers artcb-follow-main.timer --no-pager || true"
    )
    inst = _ssh(node_id, marker, timeout=90)
    run = _ssh(
        node_id,
        "ARTCB_FOLLOW_MODE=official bash /home/ubuntu/artcb/scripts/artcb_follow_main.sh",
        timeout=240,
    )
    book = _ssh(
        node_id,
        "set -e; cd /home/ubuntu/artcb; "
        "echo HOST=$(hostname); echo HEAD=$(git rev-parse HEAD); "
        "echo BR=$(git rev-parse --abbrev-ref HEAD); "
        "echo BOOK=$(wc -l < data/chain/blocks.jsonl); "
        "echo OFFICIAL=$(cat /etc/artcb/official_node 2>/dev/null || echo missing); "
        "echo TIMER=$(systemctl is-enabled artcb-follow-main.timer 2>/dev/null || echo absent); "
        "echo FETCH_TEST; GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c http.version=HTTP/1.1 "
        "ls-remote https://github.com/vgactech/artcb.git refs/heads/main >/tmp/artcb_ls_remote.txt 2>/tmp/artcb_ls_remote.err; "
        "echo LS_RC=$?; tail -c 200 /tmp/artcb_ls_remote.err; echo; "
        "head -c 80 /tmp/artcb_ls_remote.txt",
        timeout=60,
    )
    return {
        "node_id": node_id,
        "ssh_host": spec.ssh_host,
        "shipped": shipped,
        "install": inst,
        "follow_run": run,
        "book": book,
    }


def github_main_sha() -> str:
    req = Request(
        "https://api.github.com/repos/vgactech/artcb/commits/main",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "artcb-sync-official"},
    )
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8")).get("sha") or ""


def main() -> int:
    do_install = "--install" in sys.argv
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "logs"
    out_dir.mkdir(exist_ok=True)
    before = {nid: probe_node(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    actions = []
    if do_install:
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            actions.append(install_follow_on_node(nid))
            time.sleep(2)
    after = {nid: probe_node(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    try:
        gh_sha = github_main_sha()
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        gh_sha = f"error:{type(exc).__name__}"
    payload = {
        "stamp": stamp,
        "install": do_install,
        "github_main_sha": gh_sha,
        "local_origin_main": subprocess.check_output(
            ["git", "rev-parse", "origin/main"], cwd=ROOT, text=True
        ).strip(),
        "certification": certification_gate(),
        "operator_go": OPERATOR_MAINNET_CERTIFICATION_GO,
        "before": before,
        "actions": actions,
        "after": after,
        "forbidden": [
            "install.sh not executed as deploy",
            "init_genesis.py not executed",
            "blocks.jsonl not emptied",
            "PR #51 rescue not merged",
            "certified_distributed_mainnet stays false",
        ],
    }
    dest = out_dir / f"207_follow_main_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    latest = out_dir / "207_follow_main_latest.json"
    latest.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"wrote": str(dest), "install": do_install, "github_main_sha": gh_sha}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
