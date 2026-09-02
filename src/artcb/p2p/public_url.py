"""Allowlist for public P2P registration — SSRF defense (D-044 / D-045).

Unauthenticated register-public / announce may only target known-safe hosts.
Loopback, link-local, and RFC1918 addresses are rejected unless
ARTCB_ALLOW_LOCAL_PEERS=1 (unit tests).

No Replit account hostname belongs in git. Any clone whose public URL matches
a platform suffix, a globally-routable IP, or ARTCB_PUBLIC_PEER_HOSTS may
announce itself to the four always-on seeds.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from src.artcb.config import ARTCB_DOMAIN, ARTCB_DOMAIN_LEGACY

INFRA_IPV4: frozenset[str] = frozenset(
    {
        "152.228.144.34",
        "151.80.107.29",
        "51.44.222.232",
        "91.134.45.8",
    }
)

# Host suffixes injected by the hosting platform — never a specific account.
PUBLIC_PLATFORM_SUFFIXES: tuple[str, ...] = (
    ".replit.app",
    ".repl.co",
    ".replit.dev",
    ".onrender.com",
    ".up.railway.app",
    ".railway.app",
)


def allow_local_peers() -> bool:
    return os.getenv("ARTCB_ALLOW_LOCAL_PEERS", "").lower() in {"1", "true", "yes", "on"}


def is_https_platform_host(host: str) -> bool:
    """True for Replit / Render / Railway public hostnames (any account)."""
    h = (host or "").lower().rstrip(".")
    return any(h.endswith(suffix) for suffix in PUBLIC_PLATFORM_SUFFIXES)


def is_official_artcb_host(host: str) -> bool:
    """True for artcb.me (official) and artcb.space (legacy transition)."""
    h = (host or "").lower().rstrip(".")
    for domain in (ARTCB_DOMAIN, ARTCB_DOMAIN_LEGACY):
        if h == domain or h.endswith("." + domain):
            return True
    return False


def extra_public_hosts() -> frozenset[str]:
    """Optional extra DNS names, comma-separated. For a custom domain on a VPS."""
    raw = os.getenv("ARTCB_PUBLIC_PEER_HOSTS", "")
    return frozenset(x.strip().lower().rstrip(".") for x in raw.split(",") if x.strip())


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
    if is_https_platform_host(host):
        return True, "platform_public"
    if is_official_artcb_host(host):
        return True, "official_domain"
    if host in extra_public_hosts():
        return True, "extra_public_host"
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
    if addr.is_global:
        # New VPS / extra OVH clone: announce http://PUBLIC_IP:8000
        return True, "public_ip"
    return False, "host_not_allowlisted"


def peer_host_is_stale_link_local(host: str) -> bool:
    """True for leftover 169.254.x metadata peers (IMDS), not a live node."""
    try:
        addr = ipaddress.ip_address((host or "").split("%")[0])
    except ValueError:
        return "169.254." in (host or "")
    return bool(addr.is_link_local)
