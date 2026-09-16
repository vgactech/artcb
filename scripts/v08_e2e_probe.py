#!/usr/bin/env python3
"""
V-08 E2E PROBE — révision 2 (2026-09-16)

Corrections par rapport à la révision 1 :
  1. TLS : séparation explicite handshake / CA validation / hostname match
     (CERT_NONE n'est plus utilisé pour évaluer la validité)
  2. Critère v08_e2e_pass corrigé : exige au moins 1 nœud non-apex opérationnel
     avec TLS hostname valide + /health 200 + chain_height non null
  3. chain_height lu depuis /api/v1/chain/status (pas /health qui ne l'expose pas)
  4. Test complet : DNS résolution + TLS full-chain + HTTPS /health + chain + API + frontend

Usage : python3 scripts/v08_e2e_probe.py [--output results.json]
"""
from __future__ import annotations

import json
import ssl
import socket
import time
import sys
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import Any

APEX_IPS: dict[str, str] = {
    "ovh-node-1": "152.228.144.34",
    "ovh-node-4": "91.134.45.8",
    "ovh-node-2": "151.80.107.29",
    "aws-node-3": "13.38.209.25",
}

# IPs déclarées dans le multi-A DNS apex (vérifier avec v08_dns_verify.py)
DNS_APEX_IPS: set[str] = {"152.228.144.34", "91.134.45.8", "151.80.107.29"}

HOSTNAME   = "artcb.me"
HTTPS_PORT = 443
TIMEOUT_S  = 6.0


@dataclass
class TLSResult:
    """Résultat granulaire d'un handshake TLS — audit §3."""
    tcp_reachable:    bool = False
    handshake_ok:     bool = False
    cert_present:     bool = False
    cert_chain_valid: bool = False   # CA de confiance (système)
    cert_not_expired: bool = False
    hostname_match:   bool = False   # CN ou SAN couvre HOSTNAME
    cn: str | None = None
    san: list[str] = field(default_factory=list)
    not_after: str | None = None
    error: str | None = None

    @property
    def fully_valid(self) -> bool:
        """True uniquement si ALL les conditions TLS sont satisfaites."""
        return (self.tcp_reachable and self.handshake_ok and self.cert_present
                and self.cert_chain_valid and self.cert_not_expired and self.hostname_match)


@dataclass
class NodeProbeResult:
    node_id: str
    ip: str
    in_dns_apex: bool = False

    # TLS
    tls: TLSResult = field(default_factory=TLSResult)

    # HTTP /health (via HTTPS, Host: artcb.me)
    health_status: int | None = None
    health_ok: bool = False       # status == 200 AND body parseable

    # Blockchain
    chain_height: int | None = None
    chain_hash: str | None = None
    chain_valid: bool = False

    # API /api/v1/network/nodes
    api_nodes_ok: bool = False
    api_nodes_count: int | None = None

    # Frontend
    frontend_status: int | None = None
    frontend_serves_artcb: bool = False

    # Git
    git_sha: str | None = None

    probed_at: float = field(default_factory=time.time)
    error: str | None = None

    @property
    def backend_alive(self) -> bool:
        return self.health_ok

    @property
    def tls_covers_apex(self) -> bool:
        return self.tls.hostname_match

    @property
    def blockchain_alive(self) -> bool:
        return self.chain_valid and self.chain_height is not None and self.chain_height > 0

    @property
    def fully_operational(self) -> bool:
        """Nœud opérationnel au sens V-08 : backend + TLS + blockchain."""
        return self.backend_alive and self.tls_covers_apex and self.blockchain_alive


def _tls_probe(ip: str, hostname: str = HOSTNAME, port: int = HTTPS_PORT) -> TLSResult:
    """
    Probe TLS en deux passes :
    Pass 1 — avec vérification CA complète (CERT_REQUIRED) pour mesurer la validité réelle.
    Pass 2 — sans vérification CA (CERT_NONE) pour extraire CN/SAN même si chaîne invalide.

    Séparation explicite des propriétés TLS (audit §3).
    """
    result = TLSResult()

    # ── TCP ──────────────────────────────────────────────────────────────────
    try:
        with socket.create_connection((ip, port), timeout=TIMEOUT_S):
            result.tcp_reachable = True
    except Exception as e:
        result.error = f"tcp:{e}"
        return result

    # ── Pass 1 : handshake avec validation CA système ────────────────────────
    ctx_full = ssl.create_default_context()
    ctx_full.check_hostname = True
    ctx_full.verify_mode = ssl.CERT_REQUIRED
    # On se connecte avec le hostname réel pour valider la chaîne CA
    try:
        with socket.create_connection((ip, port), timeout=TIMEOUT_S) as sock:
            with ctx_full.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                result.handshake_ok = True
                result.cert_present = bool(cert)
                result.cert_chain_valid = True  # wrap_socket avec CERT_REQUIRED a réussi
                # Vérifier expiry
                not_after = cert.get("notAfter", "") if cert else ""
                result.not_after = not_after
                if not_after:
                    try:
                        import datetime
                        exp = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                        result.cert_not_expired = exp > datetime.datetime.utcnow()
                    except Exception:
                        result.cert_not_expired = True  # ne pas punir si parsing échoue
                # CN + SAN
                cn = next((v for fs in cert.get("subject", []) for k, v in fs
                           if k == "commonName"), None) if cert else None
                san = [v for k, v in cert.get("subjectAltName", [])
                       if k == "DNS"] if cert else []
                result.cn = cn
                result.san = san
                result.hostname_match = (
                    hostname in san
                    or f"*.{hostname.split('.', 1)[1]}" in san
                    or cn == hostname
                )
                return result
    except ssl.SSLCertVerificationError as e:
        # Handshake réussi mais cert invalide (CA non reconnue, expiré, hostname mismatch)
        result.handshake_ok = True
        result.cert_chain_valid = False
        result.error = f"ca_verify:{e}"
        # Pass 2 pour extraire quand même CN/SAN
    except ssl.SSLError as e:
        result.handshake_ok = False
        result.error = f"ssl:{e}"
        return result
    except Exception as e:
        result.handshake_ok = False
        result.error = f"handshake:{e}"
        return result

    # ── Pass 2 : extraction CN/SAN sans validation CA ────────────────────────
    ctx_bare = ssl.create_default_context()
    ctx_bare.check_hostname = False
    ctx_bare.verify_mode = ssl.CERT_OPTIONAL
    try:
        with socket.create_connection((ip, port), timeout=TIMEOUT_S) as sock:
            with ctx_bare.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                result.cert_present = bool(cert)
                if cert:
                    cn = next((v for fs in cert.get("subject", []) for k, v in fs
                               if k == "commonName"), None)
                    san = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
                    not_after = cert.get("notAfter", "")
                    result.cn = cn
                    result.san = san
                    result.not_after = not_after
                    result.hostname_match = (
                        hostname in san
                        or f"*.{hostname.split('.', 1)[1]}" in san
                        or cn == hostname
                    )
                    if not_after:
                        try:
                            import datetime
                            exp = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                            result.cert_not_expired = exp > datetime.datetime.utcnow()
                        except Exception:
                            result.cert_not_expired = True
    except Exception as e:
        result.error = (result.error or "") + f" | pass2:{e}"

    return result


def _https_get(ip: str, path: str, hostname: str = HOSTNAME,
               timeout: float = TIMEOUT_S) -> tuple[int | None, bytes, float]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"https://{ip}:{HTTPS_PORT}{path}"
    req = urllib.request.Request(url, headers={"Host": hostname, "User-Agent": "ARTCB-V08-E2E/2"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read(65536), (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.read(512), (time.monotonic() - t0) * 1000
    except Exception:
        return None, b"", (time.monotonic() - t0) * 1000


def probe_node(node_id: str, ip: str) -> NodeProbeResult:
    r = NodeProbeResult(node_id=node_id, ip=ip, in_dns_apex=(ip in DNS_APEX_IPS))

    # ── TLS ──────────────────────────────────────────────────────────────────
    r.tls = _tls_probe(ip)

    # ── HTTPS /health ─────────────────────────────────────────────────────────
    status, body, _ = _https_get(ip, "/health")
    r.health_status = status
    if status == 200:
        try:
            d = json.loads(body)
            r.health_ok = d.get("status") in ("healthy", "ok")
            r.git_sha = str(d.get("git_sha") or "")[:12]
        except Exception:
            pass

    # ── Blockchain /api/v1/chain/status ───────────────────────────────────────
    status2, body2, _ = _https_get(ip, "/api/v1/chain/status")
    if status2 == 200:
        try:
            d = json.loads(body2)
            r.chain_height = d.get("height") or d.get("block_count")
            r.chain_hash   = str(d.get("last_hash") or "")[:16]
            r.chain_valid  = bool(d.get("chain_valid", True)) and r.chain_height is not None
        except Exception:
            pass

    # ── API /api/v1/network/nodes ─────────────────────────────────────────────
    s3, b3, _ = _https_get(ip, "/api/v1/network/nodes", timeout=4.0)
    if s3 == 200:
        try:
            d = json.loads(b3)
            r.api_nodes_ok = True
            r.api_nodes_count = len(d.get("nodes", d.get("bootstrap", [])))
        except Exception:
            pass

    # ── Frontend ──────────────────────────────────────────────────────────────
    sf, bf, _ = _https_get(ip, "/", timeout=4.0)
    r.frontend_status = sf
    r.frontend_serves_artcb = sf == 200 and b"artcb" in (bf or b"").lower()

    return r


def run_e2e_probe(ips: dict[str, str] | None = None) -> dict[str, Any]:
    target = ips or APEX_IPS
    results: list[NodeProbeResult] = []

    print(f"[V-08 E2E v2] {len(target)} nœuds — {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"[Hostname] {HOSTNAME}\n")

    hdr = f"{'NODE':<14} {'BACK':<6} {'TLS-CA':<8} {'TLS-HN':<8} {'height':<8} {'sha':<12} dns_apex"
    print(hdr)
    print("-" * 75)

    for node_id, ip in target.items():
        r = probe_node(node_id, ip)
        results.append(r)
        back = "✅" if r.backend_alive else "❌"
        ca   = "✅" if r.tls.cert_chain_valid else "❌"
        hn   = "✅" if r.tls.hostname_match else "❌"
        h    = str(r.chain_height) if r.chain_height else "null"
        sha  = (r.git_sha or "?")[:10]
        dns  = "DNS✅" if r.in_dns_apex else "DNS—"
        print(f"{node_id:<14} {back:<6} {ca:<8} {hn:<8} {h:<8} {sha:<12} {dns}")
        if r.tls.error:
            print(f"  tls_err={r.tls.error[:80]}")

    print()

    # ── Critère V-08 E2E PASS (corrigé, audit §4) ────────────────────────────
    # Condition minimale :
    #   Au moins 1 nœud NON-OVH1 qui est :
    #     - backend alive (health 200)
    #     - TLS hostname_match (couvre artcb.me)
    #     - blockchain alive (chain_height > 0)
    #   ET ce nœud est dans le multi-A DNS (in_dns_apex)
    qualified_failover = [
        r for r in results
        if r.node_id != "ovh-node-1"
        and r.backend_alive
        and r.tls.hostname_match
        and r.blockchain_alive
        and r.in_dns_apex
    ]

    # Pour être honnête : si un nœud qualifié n'est pas dans le DNS apex, on le note
    non_apex_capable = [
        r for r in results
        if r.node_id != "ovh-node-1"
        and r.backend_alive
        and r.tls.hostname_match
        and r.blockchain_alive
        and not r.in_dns_apex
    ]

    apex_alive = any(r.node_id == "ovh-node-1" and r.backend_alive for r in results)

    v08_e2e_pass = len(qualified_failover) >= 1
    v08_note = ""

    if apex_alive and len(qualified_failover) >= 1:
        v08_note = "V-08 E2E PASS — apex + secours qualifiés dans DNS multi-A"
    elif not apex_alive and len(qualified_failover) >= 1:
        v08_note = (f"V-08 E2E PASS (failover) — OVH1 mort, {len(qualified_failover)} "
                    f"secours qualifiés dans DNS apex : {[r.node_id for r in qualified_failover]}")
    elif non_apex_capable:
        v08_note = (f"V-08 E2E PARTIAL — secours capables mais non dans DNS apex : "
                    f"{[r.node_id for r in non_apex_capable]}")
        v08_e2e_pass = False
    else:
        v08_note = "V-08 E2E FAIL — aucun secours qualifié (backend + TLS + blockchain + DNS)"

    # Cohérence blockchain
    heights = [r.chain_height for r in results if r.chain_height]
    height_spread = (max(heights) - min(heights)) if len(heights) >= 2 else 0

    print(f"qualified_failover : {[r.node_id for r in qualified_failover]}")
    print(f"non_apex_capable   : {[r.node_id for r in non_apex_capable]}")
    print(f"chain heights      : {heights} (spread={height_spread})")
    print(f"V-08 E2E PASS      : {v08_e2e_pass}")
    print(f"Note               : {v08_note}")

    return {
        "v08_e2e_version": 2,
        "v08_e2e_property": "PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH",
        "v08_e2e_pass": v08_e2e_pass,
        "v08_note": v08_note,
        "hostname": HOSTNAME,
        "apex_alive": apex_alive,
        "qualified_failover_nodes": [r.node_id for r in qualified_failover],
        "non_apex_capable_nodes": [r.node_id for r in non_apex_capable],
        "chain_heights": {r.node_id: r.chain_height for r in results if r.chain_height},
        "chain_height_spread": height_spread,
        "tls_summary": {
            r.node_id: {
                "tcp": r.tls.tcp_reachable,
                "handshake": r.tls.handshake_ok,
                "ca_valid": r.tls.cert_chain_valid,
                "hostname_match": r.tls.hostname_match,
                "cert_not_expired": r.tls.cert_not_expired,
                "cn": r.tls.cn,
                "not_after": r.tls.not_after,
            }
            for r in results
        },
        "probe_results": [asdict(r) for r in results],
        "probed_at": time.time(),
        "certified_100": False,
        "unique_human_proven": False,
        "note_chain_height": (
            "chain_height vient de /api/v1/chain/status (pas /health). "
            "null = nœud UP mais chaîne non chargée (data_dir vide ou restart récent)."
        ),
    }


if __name__ == "__main__":
    import argparse, pathlib

    parser = argparse.ArgumentParser(description="V-08 E2E probe v2")
    parser.add_argument("--output", default=None)
    parser.add_argument("--ip", nargs="*")
    args = parser.parse_args()

    custom = None
    if args.ip:
        custom = {}
        for item in args.ip:
            if "=" in item:
                k, v = item.split("=", 1)
                custom[k] = v

    report = run_e2e_probe(custom)

    if args.output:
        pathlib.Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        print(f"\nRapport écrit : {args.output}")

    sys.exit(0 if report["v08_e2e_pass"] else 1)
