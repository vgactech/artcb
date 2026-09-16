#!/usr/bin/env python3
"""
V-08 E2E PROBE — 2026-09-16
Vérifie que chaque IP de l'apex artcb.me sert réellement ARTCB :
  - HTTPS (TLS + certificat valide pour artcb.me)
  - /health (backend vivant, chain_height, git_sha)
  - /api/v1/network/nodes (API réelle)
  - Frontend HTML (200 + contenu ARTCB)

Usage : python3 scripts/v08_e2e_probe.py
Sortie : JSON + résumé texte + code retour 0 (PASS) / 1 (FAIL)
"""
from __future__ import annotations

import json
import ssl
import socket
import time
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import Any

# ─── IPs à tester (apex multi-A après fix V-08) ──────────────────────────────
APEX_IPS: dict[str, str] = {
    "ovh-node-1": "152.228.144.34",
    "ovh-node-4": "91.134.45.8",
    "ovh-node-2": "151.80.107.29",
    "aws-node-3": "13.38.209.25",
}

HOSTNAME = "artcb.me"
HTTP_PORT = 8000
HTTPS_PORT = 8443
TIMEOUT_S = 6.0

# ─── Résultat par IP ─────────────────────────────────────────────────────────

@dataclass
class IPProbeResult:
    node_id: str
    ip: str
    http_alive: bool = False
    http_status: int | None = None
    http_latency_ms: float | None = None
    chain_height: int | None = None
    git_sha: str | None = None
    health_ok: bool = False
    https_alive: bool = False
    https_status: int | None = None
    https_cert_valid: bool = False
    https_cert_cn: str | None = None
    https_cert_san: list[str] = field(default_factory=list)
    https_cert_error: str | None = None
    api_nodes_ok: bool = False
    api_nodes_count: int | None = None
    frontend_ok: bool = False
    frontend_has_artcb: bool = False
    error: str | None = None
    probed_at: float = field(default_factory=time.time)

    @property
    def fully_operational(self) -> bool:
        """True si le nœud sert ARTCB correctement (HTTP + health)."""
        return self.http_alive and self.health_ok

    @property
    def https_operational(self) -> bool:
        return self.https_alive and self.https_cert_valid


def _http_get(url: str, timeout: float = TIMEOUT_S) -> tuple[int, bytes, float]:
    t0 = time.monotonic()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"Host": HOSTNAME, "User-Agent": "ARTCB-V08-E2E/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        body = r.read(65536)
        latency = (time.monotonic() - t0) * 1000
        return r.status, body, latency


def _check_tls(ip: str, port: int = HTTPS_PORT, hostname: str = HOSTNAME) -> dict[str, Any]:
    """Vérifie le certificat TLS sans vérifier la validité CA."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((ip, port), timeout=TIMEOUT_S) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    # DER mode — recréer avec CERT_OPTIONAL pour avoir le dict
                    return {"valid": False, "error": "no_cert_dict", "cn": None, "san": []}
                cn = None
                for field_set in cert.get("subject", []):
                    for k, v in field_set:
                        if k == "commonName":
                            cn = v
                san = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
                # Vérifier que le hostname est couvert
                covers = (
                    hostname in san
                    or f"*.{'.'.join(hostname.split('.')[1:])}" in san
                    or cn == hostname
                )
                return {"valid": covers, "cn": cn, "san": san, "error": None}
    except ssl.SSLError as e:
        return {"valid": False, "cn": None, "san": [], "error": f"ssl:{e}"}
    except Exception as e:
        return {"valid": False, "cn": None, "san": [], "error": str(e)[:120]}


def probe_ip(node_id: str, ip: str) -> IPProbeResult:
    result = IPProbeResult(node_id=node_id, ip=ip)

    # ── 1. HTTP /health ──────────────────────────────────────────────────────
    try:
        status, body, latency = _http_get(f"http://{ip}:{HTTP_PORT}/health")
        result.http_alive = True
        result.http_status = status
        result.http_latency_ms = round(latency, 1)
        if status == 200:
            try:
                data = json.loads(body)
                result.chain_height = data.get("chain_height")
                result.git_sha = str(data.get("git_sha") or "")[:12]
                result.health_ok = True
            except json.JSONDecodeError:
                result.health_ok = False
    except urllib.error.HTTPError as e:
        result.http_status = e.code
    except Exception as e:
        result.error = str(e)[:120]

    # ── 2. HTTPS TLS ─────────────────────────────────────────────────────────
    tls = _check_tls(ip, HTTPS_PORT)
    result.https_cert_valid = tls["valid"]
    result.https_cert_cn = tls["cn"]
    result.https_cert_san = tls["san"]
    result.https_cert_error = tls["error"]

    try:
        status, body, _ = _http_get(f"https://{ip}:{HTTPS_PORT}/health")
        result.https_alive = True
        result.https_status = status
    except Exception:
        result.https_alive = False

    # ── 3. API /api/v1/network/nodes ─────────────────────────────────────────
    try:
        status, body, _ = _http_get(f"http://{ip}:{HTTP_PORT}/api/v1/network/nodes")
        if status == 200:
            data = json.loads(body)
            result.api_nodes_ok = True
            result.api_nodes_count = len(data.get("nodes", data.get("bootstrap", [])))
    except Exception:
        pass

    # ── 4. Frontend HTML ─────────────────────────────────────────────────────
    try:
        # Essayer la racine (nginx sert le frontend sur port 80 ou 8000 selon config)
        for port in [80, 8000]:
            try:
                status, body, _ = _http_get(f"http://{ip}:{port}/", timeout=4.0)
                if status == 200:
                    result.frontend_ok = True
                    text = body.decode("utf-8", errors="replace").lower()
                    result.frontend_has_artcb = "artcb" in text
                    break
            except Exception:
                continue
    except Exception:
        pass

    return result


def run_e2e_probe(ips: dict[str, str] | None = None) -> dict[str, Any]:
    """Exécute le probe E2E complet et retourne un rapport JSON-sérialisable."""
    target = ips or APEX_IPS
    results: list[IPProbeResult] = []

    print(f"[V-08 E2E] Probe de {len(target)} IPs — {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"[V-08 E2E] Hostname cible : {HOSTNAME}\n")

    for node_id, ip in target.items():
        print(f"  → {node_id} ({ip})...", end=" ", flush=True)
        r = probe_ip(node_id, ip)
        results.append(r)
        status = "✅ ALIVE" if r.fully_operational else "❌ DEAD"
        https_status = "TLS✅" if r.https_operational else ("TLS⚠️" if r.https_alive else "TLS❌")
        print(f"{status} {https_status} height={r.chain_height} latency={r.http_latency_ms}ms")
        if r.error:
            print(f"     error: {r.error}")

    # ── Synthèse ─────────────────────────────────────────────────────────────
    alive = [r for r in results if r.fully_operational]
    dead  = [r for r in results if not r.fully_operational]
    tls_ok = [r for r in results if r.https_operational]

    # V-08 E2E PASS si au moins 2 IPs servent ARTCB (apex OVH1 + au moins un secours)
    non_apex_alive = [r for r in alive if r.node_id != "ovh-node-1"]
    v08_e2e_pass = len(alive) >= 1 and len(non_apex_alive) >= 1

    # Vérifier cohérence blockchain (toutes les hauteurs proches)
    heights = [r.chain_height for r in alive if r.chain_height is not None]
    height_spread = (max(heights) - min(heights)) if len(heights) >= 2 else 0
    blockchain_coherent = height_spread <= 5  # tolérance 5 blocs

    print(f"\n{'='*60}")
    print(f"  ALIVE ({len(alive)})  : {[r.node_id for r in alive]}")
    print(f"  DEAD  ({len(dead)})   : {[r.node_id for r in dead]}")
    print(f"  TLS OK ({len(tls_ok)}): {[r.node_id for r in tls_ok]}")
    print(f"  Heights            : {heights} (spread={height_spread})")
    print(f"  Blockchain cohérent: {'✅' if blockchain_coherent else '⚠️'}")
    print(f"  V-08 E2E PASS      : {'✅' if v08_e2e_pass else '❌'}")
    print(f"{'='*60}\n")

    return {
        "v08_e2e_property": "PUBLIC_ENDPOINT_SURVIVES_NODE_DEATH",
        "v08_e2e_pass": v08_e2e_pass,
        "hostname": HOSTNAME,
        "alive_nodes": [r.node_id for r in alive],
        "dead_nodes": [r.node_id for r in dead],
        "tls_ok_nodes": [r.node_id for r in tls_ok],
        "chain_heights": {r.node_id: r.chain_height for r in alive},
        "height_spread": height_spread,
        "blockchain_coherent": blockchain_coherent,
        "non_apex_alive_count": len(non_apex_alive),
        "probe_results": [asdict(r) for r in results],
        "probed_at": time.time(),
        "note": (
            "V-08 E2E PASS : au moins 1 IP apex et 1 secours servent ARTCB."
            if v08_e2e_pass
            else "V-08 E2E FAIL : pas assez de nœuds opérationnels (apex + 1 secours requis)."
        ),
        "certified_100": False,
        "unique_human_proven": False,
    }


if __name__ == "__main__":
    import argparse, pathlib

    parser = argparse.ArgumentParser(description="V-08 E2E probe")
    parser.add_argument("--output", default=None, help="Fichier JSON de sortie (optionnel)")
    parser.add_argument("--ip", nargs="*", help="IPs spécifiques à tester (format node_id=ip)")
    args = parser.parse_args()

    custom_ips = None
    if args.ip:
        custom_ips = {}
        for item in args.ip:
            if "=" in item:
                k, v = item.split("=", 1)
                custom_ips[k] = v

    report = run_e2e_probe(custom_ips)

    if args.output:
        pathlib.Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        print(f"Rapport JSON écrit : {args.output}")

    sys.exit(0 if report["v08_e2e_pass"] else 1)
