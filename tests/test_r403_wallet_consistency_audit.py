"""
Tests R403 — Audit de cohérence wallet multi-nœuds ARTCB.
Tous les tests s'exécutent sans réseau (mocks urllib).

T01–T04 : probe_wallet_list / probe_wallet_exists
T05–T07 : probe_auth_me
T08–T09 : probe_chain_tip
T10–T11 : probe_device_binding_admin
T12–T15 : analyze_consistency (cohérence, incohérences, wallet_state_local)
T16–T17 : run_audit (intégration avec mocks)
T18–T19 : CLI main() exit codes

CERTIFIED_100=false | MODE DEBUG
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import io

# Ajoute la racine au path
sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.artcb_r403_wallet_consistency_audit as r403

# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_urlopen(status: int, body: object):
    """Renvoie un context manager simulant urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = json.dumps(body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _mock_http_error(code: int, body: object):
    import urllib.error
    err = urllib.error.HTTPError(
        url="https://fake", code=code, msg="Error",
        hdrs=None, fp=io.BytesIO(json.dumps(body).encode())
    )
    return err


# ── T01–T04 : probe_wallet_list / probe_wallet_exists ─────────────────────────

class TestProbeWalletList(unittest.TestCase):

    def test_T01_wallet_list_200(self):
        """T01 — probe_wallet_list 200 renvoie liste de wallets."""
        wallets = [{"name": "alice", "address": "artcb1abc"}, {"name": "bob", "address": "artcb1xyz"}]
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(200, wallets)):
            result = r403.probe_wallet_list("1.2.3.4", timeout=5.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["http_code"], 200)
        self.assertEqual(len(result["wallets"]), 2)

    def test_T02_wallet_list_network_error(self):
        """T02 — probe_wallet_list connexion refusée renvoie ok=False."""
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = r403.probe_wallet_list("1.2.3.4", timeout=5.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["http_code"], 0)
        self.assertIsNotNone(result["error"])

    def test_T03_wallet_exists_found(self):
        """T03 — probe_wallet_exists retrouve le wallet ciblé."""
        wallets = [{"name": "vgactech0", "address": "artcb1abc"}]
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(200, wallets)):
            result = r403.probe_wallet_exists("1.2.3.4", "vgactech0", timeout=5.0)
        self.assertTrue(result["wallet_found"])
        self.assertEqual(result["wallet_meta"]["address"], "artcb1abc")

    def test_T04_wallet_exists_not_found(self):
        """T04 — probe_wallet_exists renvoie wallet_found=False si absent de la liste."""
        wallets = [{"name": "other_wallet", "address": "artcb1other"}]
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(200, wallets)):
            result = r403.probe_wallet_exists("1.2.3.4", "vgactech0", timeout=5.0)
        self.assertFalse(result["wallet_found"])
        self.assertIsNone(result["wallet_meta"])


# ── T05–T07 : probe_auth_me ────────────────────────────────────────────────────

class TestProbeAuthMe(unittest.TestCase):

    def test_T05_auth_me_valid_session(self):
        """T05 — probe_auth_me 200 avec wallet_name et address."""
        body = {"wallet_name": "vgactech0", "address": "artcb1abc", "expires_at": "..."}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(200, body)):
            result = r403.probe_auth_me("1.2.3.4", "tok123", timeout=5.0)
        self.assertTrue(result["session_valid"])
        self.assertEqual(result["wallet_name"], "vgactech0")
        self.assertEqual(result["address"], "artcb1abc")

    def test_T06_auth_me_401(self):
        """T06 — probe_auth_me 401 → session_valid=False."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=_mock_http_error(401, {"detail": "Unauthorized"})):
            result = r403.probe_auth_me("1.2.3.4", "bad_tok", timeout=5.0)
        self.assertFalse(result["session_valid"])
        self.assertEqual(result["http_code"], 401)

    def test_T07_auth_me_wallet_not_found(self):
        """T07 — probe_auth_me 404 → session_valid=False, nœud n'a pas le wallet."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=_mock_http_error(404, {"detail": "wallet_not_found"})):
            result = r403.probe_auth_me("1.2.3.4", "tok123", timeout=5.0)
        self.assertFalse(result["session_valid"])
        self.assertEqual(result["http_code"], 404)


# ── T08–T09 : probe_chain_tip ─────────────────────────────────────────────────

class TestProbeChainTip(unittest.TestCase):

    def test_T08_chain_tip_ok(self):
        """T08 — probe_chain_tip renvoie height et last_hash."""
        body = {"height": 1150, "last_hash": "abcdef1234567890"}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(200, body)):
            result = r403.probe_chain_tip("1.2.3.4", timeout=5.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["height"], 1150)
        self.assertEqual(result["last_hash"], "abcdef1234567890")

    def test_T09_chain_tip_down(self):
        """T09 — probe_chain_tip connexion refusée → ok=False."""
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            result = r403.probe_chain_tip("1.2.3.4", timeout=5.0)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["height"])


# ── T10–T11 : probe_device_binding_admin ──────────────────────────────────────

class TestProbeDeviceBinding(unittest.TestCase):

    def test_T10_binding_found(self):
        """T10 — probe_device_binding_admin 200 → binding_found=True."""
        body = {"fingerprint": "97a0b640", "wallet_name": "vgactech0"}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(200, body)):
            result = r403.probe_device_binding_admin("1.2.3.4", "97a0b640", timeout=5.0)
        self.assertTrue(result["binding_found"])
        self.assertTrue(result["endpoint_exists"])

    def test_T11_binding_endpoint_absent(self):
        """T11 — probe_device_binding_admin 404 → endpoint_exists=False (endpoint pas implémenté)."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=_mock_http_error(404, {})):
            result = r403.probe_device_binding_admin("1.2.3.4", "97a0b640", timeout=5.0)
        self.assertFalse(result["binding_found"])
        self.assertFalse(result["endpoint_exists"])


# ── T12–T15 : analyze_consistency ────────────────────────────────────────────

class TestAnalyzeConsistency(unittest.TestCase):

    def _make_node_result(self, node_id: str, wallet_found: bool,
                          address: str, height: int, last_hash: str,
                          session_valid: bool | None = None) -> dict:
        r: dict = {
            "node_id": node_id,
            "wallet_check": {
                "wallet_found": wallet_found,
                "wallet_meta": {"name": "vgactech0", "address": address} if wallet_found else None,
            },
            "chain_tip": {
                "ok": True,
                "height": height,
                "last_hash": last_hash,
            },
        }
        if session_valid is not None:
            r["auth_me"] = {"session_valid": session_valid}
        return r

    def test_T12_all_consistent(self):
        """T12 — 3 nœuds, wallet présent partout, même adresse → CONSISTENT."""
        nodes = [
            self._make_node_result("N2", True, "artcb1abc", 1150, "aabbcc"),
            self._make_node_result("N4", True, "artcb1abc", 1150, "aabbcc"),
            self._make_node_result("N3", True, "artcb1abc", 1149, "aabbcc"),
        ]
        analysis = r403.analyze_consistency(nodes, "vgactech0")
        self.assertEqual(analysis["verdict"], "CONSISTENT")
        self.assertEqual(analysis["wallet_consistent"], True)
        self.assertEqual(analysis["wallet_state_local"], False)

    def test_T13_wallet_state_local(self):
        """T13 — wallet présent N2 seulement → WALLET_STATE_LOCAL détecté."""
        nodes = [
            self._make_node_result("N2", True, "artcb1abc", 1150, "aabbcc"),
            self._make_node_result("N4", False, "", 1150, "aabbcc"),
            self._make_node_result("N3", False, "", 1150, "aabbcc"),
        ]
        analysis = r403.analyze_consistency(nodes, "vgactech0")
        self.assertEqual(analysis["verdict"], "INCONSISTENT")
        self.assertTrue(analysis["wallet_state_local"])
        self.assertIn("N2", analysis["wallet_found_on"])
        self.assertIn("WALLET_STATE_LOCAL", str(analysis["issues"]))

    def test_T14_chain_fork(self):
        """T14 — 2 last_hash distincts → CHAIN_FORK détecté."""
        nodes = [
            self._make_node_result("N2", True, "artcb1abc", 1150, "hash_A"),
            self._make_node_result("N4", True, "artcb1abc", 1150, "hash_A"),
            self._make_node_result("N3", True, "artcb1abc", 1150, "hash_B"),  # fork
        ]
        analysis = r403.analyze_consistency(nodes, "vgactech0")
        self.assertEqual(analysis["verdict"], "INCONSISTENT")
        self.assertFalse(analysis["chain_hash_consistent"])
        self.assertIn("CHAIN_FORK", str(analysis["issues"]))

    def test_T15_session_inconsistent(self):
        """T15 — session valide N2 seulement → SESSION_INCONSISTENT détecté."""
        nodes = [
            self._make_node_result("N2", True, "artcb1abc", 1150, "aabbcc", session_valid=True),
            self._make_node_result("N4", True, "artcb1abc", 1150, "aabbcc", session_valid=False),
            self._make_node_result("N3", True, "artcb1abc", 1150, "aabbcc", session_valid=False),
        ]
        analysis = r403.analyze_consistency(nodes, "vgactech0")
        self.assertEqual(analysis["verdict"], "INCONSISTENT")
        self.assertFalse(analysis["session_consistent"])
        self.assertIn("SESSION_INCONSISTENT", str(analysis["issues"]))


# ── T16–T17 : run_audit intégration ──────────────────────────────────────────

class TestRunAudit(unittest.TestCase):

    def _side_effects_consistent(self):
        """Toutes les sondes retournent wallet présent + chaîne cohérente."""
        wallets = [{"name": "vgactech0", "address": "artcb1abc"}]
        tip = {"height": 1150, "last_hash": "aabbcc"}
        # Alternance wallet_list puis chain_tip par nœud
        responses = []
        for _ in range(3):
            responses.append(_mock_urlopen(200, wallets))  # wallet list
            responses.append(_mock_urlopen(200, tip))       # chain tip
        return responses

    def test_T16_run_audit_consistent(self):
        """T16 — run_audit retourne CONSISTENT si wallet présent sur tous les nœuds."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            original_logs = r403.LOGS_DIR
            r403.LOGS_DIR = Path(tmpdir)
            try:
                call_count = [0]
                responses = self._side_effects_consistent()
                def fake_urlopen(req, timeout=None, context=None):
                    resp = responses[call_count[0] % len(responses)]
                    call_count[0] += 1
                    return resp
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    report = r403.run_audit("vgactech0", None, None, timeout=5.0)
                self.assertEqual(report["consistency"]["verdict"], "CONSISTENT")
                # Vérifier que le log forensic a été créé
                logs = list(Path(tmpdir).glob("R403_consistency_*.json"))
                self.assertEqual(len(logs), 1)
            finally:
                r403.LOGS_DIR = original_logs

    def test_T17_run_audit_logs_forensic_content(self):
        """T17 — Le log forensic contient wallet_name, ts_ns, nodes, consistency."""
        import tempfile
        responses = self._side_effects_consistent()
        call_count = [0]
        def fake_urlopen(req, timeout=None, context=None):
            resp = responses[call_count[0] % len(responses)]
            call_count[0] += 1
            return resp
        with tempfile.TemporaryDirectory() as tmpdir:
            r403.LOGS_DIR = Path(tmpdir)
            try:
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    report = r403.run_audit("vgactech0", None, None, timeout=5.0)
                logs = list(Path(tmpdir).glob("R403_consistency_*.json"))
                self.assertEqual(len(logs), 1)
                log_content = json.loads(logs[0].read_text())
                self.assertEqual(log_content["report"], "R403")
                self.assertIn("ts_start_ns", log_content)
                self.assertIn("consistency", log_content)
                self.assertEqual(len(log_content["nodes"]), 3)
            finally:
                r403.LOGS_DIR = Path("logs")


# ── T18–T19 : main() exit codes ──────────────────────────────────────────────

class TestMain(unittest.TestCase):

    def test_T18_main_exit_0_consistent(self):
        """T18 — main() retourne 0 si verdict CONSISTENT."""
        wallets = [{"name": "vgactech0", "address": "artcb1abc"}]
        tip = {"height": 1150, "last_hash": "aabbcc"}
        responses = []
        call_count = [0]
        for _ in range(3):
            responses.append(_mock_urlopen(200, wallets))
            responses.append(_mock_urlopen(200, tip))
        def fake_urlopen(req, timeout=None, context=None):
            resp = responses[call_count[0] % len(responses)]
            call_count[0] += 1
            return resp
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            r403.LOGS_DIR = Path(tmpdir)
            try:
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    code = r403.main(["--wallet", "vgactech0", "--timeout", "5"])
                self.assertEqual(code, 0)
            finally:
                r403.LOGS_DIR = Path("logs")

    def test_T19_main_exit_1_inconsistent(self):
        """T19 — main() retourne 1 si verdict INCONSISTENT (wallet_state_local)."""
        # N2 a le wallet, N4 et N3 n'ont pas
        wallets_with = [{"name": "vgactech0", "address": "artcb1abc"}]
        wallets_without: list = []
        tip = {"height": 1150, "last_hash": "aabbcc"}
        responses = [
            _mock_urlopen(200, wallets_with), _mock_urlopen(200, tip),   # N2
            _mock_urlopen(200, wallets_without), _mock_urlopen(200, tip), # N4
            _mock_urlopen(200, wallets_without), _mock_urlopen(200, tip), # N3
        ]
        call_count = [0]
        def fake_urlopen(req, timeout=None, context=None):
            resp = responses[call_count[0] % len(responses)]
            call_count[0] += 1
            return resp
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            r403.LOGS_DIR = Path(tmpdir)
            try:
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    code = r403.main(["--wallet", "vgactech0", "--timeout", "5"])
                self.assertEqual(code, 1)
            finally:
                r403.LOGS_DIR = Path("logs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
