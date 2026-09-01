"""Allowlist for public P2P registration — SSRF defense (D-044).

Unauthenticated register-public may only target known infrastructure
hosts. Loopback, link-local, and RFC1918 addresses are rejected unless
ARTCB_ALLOW_LOCAL_PEERS=1 (unit tests).
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

INFRA_IPV4: frozenset[str] = frozenset(
    {
        "152.228.144.34",
        "151.80.107.29",
        "51.44.222.232",
        "91.134.45.8",
    }
)


def allow_local_peers() -> bool:
    return os.getenv("ARTCB_ALLOW_LOCAL_PEERS", "").lower() in {"1", "true", "yes", "on"}


def public_register_url_ok(url: str) -> tuple[bool, str]:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return False, "scheme_forbidden"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "host_missing"
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        if allow_local_peers():
            return True, "local_test"
        return False, "loopback_forbidden"
    if host.endswith(".replit.app") or host.endswith(".repl.co"):
        return True, "replit_public"
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False, "host_not_allowlisted"
    if str(addr) in INFRA_IPV4:
        return True, "allowlist_ip"
    if addr.is_link_local or addr.is_multicast or addr.is_reserved:
        return False, "link_local_or_reserved_forbidden"
    if addr.is_loopback or addr.is_private:
        if allow_local_peers():
            return True, "local_test"
        return False, "private_or_loopback_forbidden"
    return False, "host_not_allowlisted"
