#!/usr/bin/env python3
"""R314 — register official seeds as HTTPS:443 P2P peers on mac-node-local.

Why not IPv4:8000 from this Mac: LAN egress to public :22/:8000/:8443 times out.
HTTPS via artcb.me / n2|n3|n4.artcb.me (DNS fix + Cloudflare/SNI) works.

Inbound P2P/PBFT to the Mac still needs a measured public tunnel (R287).
This script only enables outbound Mac → seeds over HTTPS.

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_mac_p2p_https_peers.py
  PYTHONPATH=src:scripts python3 scripts/artcb_mac_p2p_https_peers.py --sync
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

try:
    from artcb_dns_fix import install as _dns_install
except Exception:  # noqa: BLE001
    def _dns_install() -> None:
        return None

SEEDS = (
    ("artcb.me", 443, "https://artcb.me"),
    ("n2.artcb.me", 443, "https://n2.artcb.me"),
    ("n3.artcb.me", 443, "https://n3.artcb.me"),
    ("n4.artcb.me", 443, "https://n4.artcb.me"),
)


def _key() -> str:
    k = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(k) >= 16:
        return k
    env = Path.home() / ".artcb" / "cursor_agent.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ARTCB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _call(method: str, url: str, data: dict | None = None, timeout: float = 120.0) -> dict:
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", default="http://127.0.0.1:8001")
    ap.add_argument("--sync", action="store_true", help="POST /p2p/sync/{peer} for each HTTPS peer")
    args = ap.parse_args()
    _dns_install()
    if len(_key()) < 16:
        print(json.dumps({"ok": False, "reason": "api_key_missing"}))
        return 2
    rows = []
    for host, port, base in SEEDS:
        status = _call("GET", f"{base}/api/v1/p2p/status")
        body = {
            "host": host,
            "port": port,
            "kem_public_key_hex": status.get("kem_public_key_hex"),
            "label": f"https_{host}",
            "capability_card": status.get("capability_card"),
        }
        try:
            out = _call("POST", f"{args.mac.rstrip('/')}/api/v1/p2p/peers", body)
            rows.append({"host": host, "ok": True, "peer_id": (out.get("peer") or {}).get("peer_id")})
        except urllib.error.HTTPError as exc:
            rows.append({"host": host, "ok": False, "http": exc.code, "detail": exc.read()[:200].decode()})
    sync_rows = []
    if args.sync:
        peers = _call("GET", f"{args.mac.rstrip('/')}/api/v1/p2p/peers").get("peers") or []
        for p in peers:
            if int(p.get("port") or 0) != 443:
                continue
            pid = p.get("peer_id")
            try:
                out = _call("POST", f"{args.mac.rstrip('/')}/api/v1/p2p/sync/{pid}?from_index=0", timeout=300)
                sync_rows.append({"peer_id": pid, "ok": True, "pull": out.get("pull"), "push": out.get("push")})
            except Exception as exc:  # noqa: BLE001
                sync_rows.append({"peer_id": pid, "ok": False, "error": f"{type(exc).__name__}:{exc}"[:200]})
    ctx = _call("GET", f"{args.mac.rstrip('/')}/api/v1/ai/context")
    print(
        json.dumps(
            {
                "ok": all(r.get("ok") for r in rows),
                "added": rows,
                "sync": sync_rows,
                "mac_chain_height": ctx.get("chain_height"),
                "note": (
                    "Outbound HTTPS P2P only. IPv4:8000 from this Mac times out. "
                    "Inbound Mac still needs public tunnel. Anonymous public pull "
                    "≠ full official-replica tip×5. CERTIFIED_100=false."
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
