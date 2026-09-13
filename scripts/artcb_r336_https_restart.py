#!/usr/bin/env python3
"""R336 — call HTTPS fanout-restart on artcb.me then compare key fingerprints.

No SSH. Uses open :443 only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from artcb_dns_fix import install as _dns

    _dns()
except Exception:
    pass

SEEDS = {
    "ovh-node-1": "https://artcb.me",
    "ovh-node-2": "https://n2.artcb.me",
    "aws-node-3": "https://n3.artcb.me",
    "ovh-node-4": "https://n4.artcb.me",
}


def _ovh1_key() -> str:
    k = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(k) >= 16:
        return k
    env = Path.home() / ".artcb" / "cursor_agent.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ARTCB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _local_sha16(node_id: str) -> str | None:
    p = Path.home() / ".artcb" / "nodes" / f"{node_id}.env"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("ARTCB_API_KEY="):
            raw = line.split("=", 1)[1].strip()
            return hashlib.sha256(raw.encode()).hexdigest()[:16]
    return None


def http_json(method: str, url: str, *, key: str = "", headers: dict | None = None, timeout: float = 60.0):
    hdrs = {"Accept": "application/json", **(headers or {})}
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    data = b"{}" if method == "POST" else None
    if method == "POST":
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.status), json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        try:
            return int(e.code), json.loads(body)
        except Exception:
            return int(e.code), {"detail": body}
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:200]}


def main() -> int:
    key = _ovh1_key()
    out: dict = {"ts": time.time(), "sha_local": {}, "fingerprint": {}, "restart": None}
    for nid in ("ovh-node-2", "aws-node-3", "ovh-node-4"):
        out["sha_local"][nid] = _local_sha16(nid)

    code, body = http_json("POST", "https://artcb.me/api/v1/ops/fanout-restart", key=key)
    out["restart"] = {"http": code, "body": body}
    print(json.dumps({"restart": out["restart"]}, indent=2)[:2000])

    # wait for systemd bounce
    time.sleep(12)
    for nid, base in SEEDS.items():
        if nid == "ovh-node-1":
            continue
        # try local node key first
        local_key = ""
        p = Path.home() / ".artcb" / "nodes" / f"{nid}.env"
        if p.is_file():
            for line in p.read_text().splitlines():
                if line.startswith("ARTCB_API_KEY="):
                    local_key = line.split("=", 1)[1].strip()
        c, b = http_json("GET", f"{base}/api/v1/ops/key-fingerprint", key=local_key or key)
        out["fingerprint"][nid] = {"http": c, "body": b}
        match = None
        if isinstance(b, dict) and (b.get("key") or {}).get("sha256_16"):
            match = (b["key"]["sha256_16"] == out["sha_local"].get(nid))
        out["fingerprint"][nid]["matches_local_cache"] = match

    text = json.dumps(out, indent=2, ensure_ascii=False)
    dest = ROOT / "logs" / "R336" / "ops_restart.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"wrote {dest}", file=sys.stderr)
    fps = out["fingerprint"]
    ok = bool((out["restart"].get("body") or {}).get("fanout_restart_pass")) and any(
        v.get("matches_local_cache") for v in fps.values()
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
