#!/usr/bin/env python3
"""R313 — force correct A records for artcb.* when LAN DNS is poisoned.

System resolver on this Mac returns 172.24.16.51 / ::1 for artcb.me
(nameservers 172.28.2.38 / 172.29.2.38). Public truth (DoH) is the OVH/AWS IPs.

Call install() early in any process that must reach https://artcb.me.
"""

from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.request
from pathlib import Path

# Seed from live DoH 2026-09-10T23:20:00Z — refresh via refresh_from_doh().
DEFAULT_MAP: dict[str, str] = {
    "artcb.me": "152.228.144.34",
    "n1.artcb.me": "152.228.144.34",
    "n2.artcb.me": "151.80.107.29",
    "n3.artcb.me": "13.38.209.25",
    "n4.artcb.me": "91.134.45.8",
}

CACHE = Path.home() / ".artcb" / "dns_override.json"
_installed = False
_orig_getaddrinfo = socket.getaddrinfo


def _load() -> dict[str, str]:
    out = dict(DEFAULT_MAP)
    if CACHE.is_file():
        try:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, str) and v.count(".") == 3:
                        out[k.lower()] = v
        except Exception:  # noqa: BLE001
            pass
    return out


def refresh_from_doh(timeout: float = 12.0) -> dict[str, str]:
    mapping = dict(DEFAULT_MAP)
    for name in list(DEFAULT_MAP):
        url = f"https://cloudflare-dns.com/dns-query?name={name}&type=A"
        req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
            for ans in body.get("Answer") or []:
                if ans.get("type") == 1 and ans.get("data"):
                    mapping[name] = str(ans["data"])
                    break
        except Exception:  # noqa: BLE001
            continue
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps({"ts_ns": time.time_ns(), **mapping}, indent=2) + "\n",
        encoding="utf-8",
    )
    return mapping


def install() -> None:
    global _installed
    if _installed:
        return
    mapping = {k.lower(): v for k, v in _load().items()}

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        h = (host or "").lower()
        if h in mapping:
            host = mapping[h]
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    _installed = True


def health_probe(url: str = "https://artcb.me/health", timeout: float = 15.0) -> dict:
    install()
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=ssl.create_default_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "http": resp.status, "body_prefix": raw[:120]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}:{exc}"[:240]}
