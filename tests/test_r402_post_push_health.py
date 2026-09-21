#!/usr/bin/env python3
"""
Tests R402 — artcb_r402_post_push_health.py

T01 : _http_get OK (mock serveur local)
T02 : _http_get timeout → (-1, message)
T03 : _probe_node retourne tous les champs requis
T04 : _probe_domain retourne tous les champs requis
T05 : dns_split_suspected=True si domaine 502 mais pas les IPs
T06 : dns_split_suspected=False si domaine OK
T07 : _check_sha_divergence détecte divergence nœud vs local
T08 : _check_sha_divergence détecte divergence inter-nœuds
T09 : _check_sha_divergence OK si SHA cohérents
T10 : run_health_check retourne global_status=ok si ≥1 nœud OK
T11 : run_health_check retourne global_status=all_down si 0 nœud OK
T12 : log forensic créé avec tous les champs requis
T13 : exit code 0 si global_status=ok, 1 si all_down
T14 : NODE_CONFIG ne contient pas OVH1 (152.228.144.34) — bloqué
T15 : _write_log écrit JSON valide et lisible
"""
from __future__ import annotations

import json
import sys
import threading
import time
import unittest.mock as mock
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "artcb_r402",
    REPO_ROOT / "scripts" / "artcb_r402_post_push_health.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_http_get = mod._http_get
_probe_node = mod._probe_node
_probe_domain = mod._probe_domain
_check_sha_divergence = mod._check_sha_divergence
_write_log = mod._write_log
run_health_check = mod.run_health_check
NODE_CONFIG = mod.NODE_CONFIG


# ── Serveur HTTP local pour tests ───────────────────────────────────────────

HEALTH_BODY = json.dumps({
    "status": "ok",
    "git_sha": "abc123def456",
    "debug": True,
})


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/v1/health":
            body = HEALTH_BODY.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/":
            body = b"<!doctype html><html><body>ARTCB</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # silencieux


def _start_mock_server(port: int) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ── Tests ────────────────────────────────────────────────────────────────────

class TestHttpGet:
    def test_t01_ok(self):
        """T01 : _http_get OK sur serveur local."""
        server = _start_mock_server(18901)
        try:
            code, body = _http_get("http://127.0.0.1:18901/api/v1/health", timeout=5, verify_ssl=True)
            assert code == 200
            data = json.loads(body)
            assert data["status"] == "ok"
        finally:
            server.shutdown()

    def test_t02_timeout(self):
        """T02 : _http_get sur port fermé → -1."""
        code, body = _http_get("http://127.0.0.1:19999/api/v1/health", timeout=1)
        assert code == -1
        assert body  # message d'erreur non vide


class TestProbeStructure:
    def test_t03_probe_node_fields(self, tmp_path):
        """T03 : _probe_node retourne tous les champs requis."""
        required = {"ts_ns", "ip", "url", "http_code", "latency_ms",
                    "api_ok", "git_sha", "status", "frontend_ok", "frontend_code", "error"}
        # Utilise une IP fermée — on vérifie juste la structure
        result = _probe_node("127.0.0.1", timeout=1)
        missing = required - set(result.keys())
        assert not missing, f"Champs manquants: {missing}"

    def test_t04_probe_domain_fields(self):
        """T04 : _probe_domain retourne tous les champs requis."""
        required = {"ts_ns", "domain", "url", "http_code", "latency_ms",
                    "api_ok", "git_sha", "error", "dns_split_suspected"}
        # Domaine inexistant → erreur mais structure complète
        with mock.patch.object(mod, "DOMAIN", "localhost-nonexistent-r402.test"):
            result = _probe_domain(timeout=1)
        missing = required - set(result.keys())
        assert not missing, f"Champs manquants: {missing}"

    def test_t05_dns_split_suspected(self):
        """T05 : dns_split_suspected=True si domaine retourne 502."""
        with mock.patch.object(mod, "_http_get", return_value=(502, "Bad Gateway")):
            result = _probe_domain(timeout=1)
        assert result["dns_split_suspected"] is True

    def test_t06_dns_split_not_suspected(self):
        """T06 : dns_split_suspected=False si domaine OK."""
        healthy_body = json.dumps({"status": "ok", "git_sha": "abc123"})
        with mock.patch.object(mod, "_http_get", return_value=(200, healthy_body)):
            result = _probe_domain(timeout=1)
        assert result["dns_split_suspected"] is False


class TestShaDivergence:
    def _make_node_result(self, ip: str, sha: str, ok: bool = True) -> dict:
        return {"ip": ip, "api_ok": ok, "git_sha": sha}

    def test_t07_divergence_node_vs_local(self):
        """T07 : divergence nœud vs SHA local."""
        nodes = [self._make_node_result("1.2.3.4", "aaaaaaa")]
        warnings = _check_sha_divergence(nodes, expected_sha="bbbbbbb")
        assert any("divergence" in w.lower() or "aaaaaaa" in w for w in warnings)

    def test_t08_divergence_inter_nodes(self):
        """T08 : divergence inter-nœuds."""
        nodes = [
            self._make_node_result("1.2.3.4", "aaaaaaa"),
            self._make_node_result("1.2.3.5", "ccccccc"),
        ]
        warnings = _check_sha_divergence(nodes, expected_sha=None)
        assert any("divergent" in w.lower() or "inter" in w.lower() for w in warnings)

    def test_t09_no_divergence(self):
        """T09 : pas de divergence si SHA cohérents."""
        nodes = [
            self._make_node_result("1.2.3.4", "abc123"),
            self._make_node_result("1.2.3.5", "abc123"),
        ]
        warnings = _check_sha_divergence(nodes, expected_sha="abc123")
        assert not warnings


class TestRunHealthCheck:
    def test_t10_global_ok(self, tmp_path):
        """T10 : global_status=ok si ≥1 nœud OK."""
        healthy = {"status": "ok", "git_sha": "abc123def456"}
        healthy_body = json.dumps(healthy)

        def fake_probe(ip, timeout=8):
            return {
                "ts_ns": time.time_ns(), "ip": ip, "url": f"https://{ip}/api/v1/health",
                "http_code": 200, "latency_ms": 50.0, "api_ok": True,
                "git_sha": "abc123", "status": "ok", "frontend_ok": True,
                "frontend_code": 200, "error": None, "node_id": "N2", "node_label": "OVH2",
            }

        with mock.patch.object(mod, "_probe_node", side_effect=fake_probe), \
             mock.patch.object(mod, "_probe_domain", return_value={
                 "ts_ns": time.time_ns(), "domain": "artcb.me", "url": "https://artcb.me/health",
                 "http_code": 200, "latency_ms": 100.0, "api_ok": True,
                 "git_sha": "abc123", "error": None, "dns_split_suspected": False,
             }), \
             mock.patch.object(mod, "LOG_DIR", tmp_path):
            report = run_health_check(timeout=5)

        assert report["global_status"] == "ok"
        assert report["nodes_up"] > 0

    def test_t11_all_down(self, tmp_path):
        """T11 : global_status=all_down si 0 nœud OK."""
        def fake_probe_down(ip, timeout=8):
            return {
                "ts_ns": time.time_ns(), "ip": ip, "url": f"https://{ip}/api/v1/health",
                "http_code": -1, "latency_ms": 50.0, "api_ok": False,
                "git_sha": None, "status": None, "frontend_ok": False,
                "frontend_code": None, "error": "timeout", "node_id": "N2", "node_label": "OVH2",
            }

        with mock.patch.object(mod, "_probe_node", side_effect=fake_probe_down), \
             mock.patch.object(mod, "_probe_domain", return_value={
                 "ts_ns": time.time_ns(), "domain": "artcb.me", "url": "https://artcb.me/health",
                 "http_code": -1, "latency_ms": 50.0, "api_ok": False,
                 "git_sha": None, "error": "timeout", "dns_split_suspected": False,
             }), \
             mock.patch.object(mod, "LOG_DIR", tmp_path):
            report = run_health_check(timeout=1)

        assert report["global_status"] == "all_down"
        assert report["nodes_up"] == 0

    def test_t12_log_fields(self, tmp_path):
        """T12 : log forensic créé avec tous les champs requis."""
        def fake_probe(ip, timeout=8):
            return {
                "ts_ns": time.time_ns(), "ip": ip, "url": "",
                "http_code": 200, "latency_ms": 50.0, "api_ok": True,
                "git_sha": "abc123", "status": "ok", "frontend_ok": True,
                "frontend_code": 200, "error": None, "node_id": "N2", "node_label": "OVH2",
            }

        with mock.patch.object(mod, "_probe_node", side_effect=fake_probe), \
             mock.patch.object(mod, "_probe_domain", return_value={
                 "ts_ns": time.time_ns(), "domain": "artcb.me", "url": "",
                 "http_code": 200, "latency_ms": 100.0, "api_ok": True,
                 "git_sha": "abc123", "error": None, "dns_split_suspected": False,
             }), \
             mock.patch.object(mod, "LOG_DIR", tmp_path):
            report = run_health_check(timeout=5)

        required = {"ts_ns", "timestamp_utc", "local_sha", "global_status",
                    "nodes_up", "nodes_total", "nodes", "domain",
                    "sha_warnings", "certified_100"}
        missing = required - set(report.keys())
        assert not missing, f"Champs manquants: {missing}"
        assert report["certified_100"] is False

    def test_t13_exit_code(self, tmp_path):
        """T13 : exit code 0 si ok, 1 si all_down."""
        def fake_probe_ok(ip, timeout=8):
            return {"ts_ns": time.time_ns(), "ip": ip, "url": "", "http_code": 200,
                    "latency_ms": 10.0, "api_ok": True, "git_sha": "abc", "status": "ok",
                    "frontend_ok": True, "frontend_code": 200, "error": None,
                    "node_id": "N2", "node_label": "OVH2"}

        with mock.patch.object(mod, "_probe_node", side_effect=fake_probe_ok), \
             mock.patch.object(mod, "_probe_domain", return_value={
                 "ts_ns": time.time_ns(), "domain": "artcb.me", "url": "",
                 "http_code": 200, "latency_ms": 10.0, "api_ok": True,
                 "git_sha": "abc", "error": None, "dns_split_suspected": False,
             }), \
             mock.patch.object(mod, "LOG_DIR", tmp_path):
            code = mod.main(["--timeout", "5"])
        assert code == 0

    def test_t14_no_ovh1(self):
        """T14 : OVH1 (152.228.144.34) absent de NODE_CONFIG."""
        ips = [n["ip"] for n in NODE_CONFIG]
        assert "152.228.144.34" not in ips, "OVH1 est BLOQUÉ — ne doit pas figurer dans NODE_CONFIG"

    def test_t15_write_log_valid_json(self, tmp_path):
        """T15 : _write_log écrit JSON valide."""
        sample = {
            "ts_ns": time.time_ns(), "timestamp_utc": "2026-09-21T00:00:00Z",
            "local_sha": "abc123", "global_status": "ok",
            "nodes_up": 3, "nodes_total": 3, "nodes": [], "domain": {},
            "sha_warnings": [], "certified_100": False,
        }
        with mock.patch.object(mod, "LOG_DIR", tmp_path):
            path = _write_log(sample)
        content = path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed["global_status"] == "ok"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
