#!/usr/bin/env python3
"""R315 — ``artcb doctor`` (first slice): differential diagnosis for a node.

Checks OS/deps/TPM presence, DNS/HTTPS, P2P outbound modes, and chain
alignment vs a seed. Does not wipe. Does not claim CERTIFIED_100.

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_doctor.py
  PYTHONPATH=src:scripts python3 scripts/artcb_doctor.py --mac http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
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


CHECKS: list[dict] = []


def _row(name: str, status: str, *, detail: str = "", impact: str = "", action: str = "") -> None:
    CHECKS.append(
        {
            "name": name,
            "status": status,
            "detail": detail,
            "impact": impact,
            "action": action,
        }
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


def _http_ok(url: str, *, timeout: float = 15.0, auth: bool = False) -> tuple[bool, str]:
    headers = {"Accept": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {_key()}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}:{str(exc)[:120]}"


def _tcp(host: str, port: int, *, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "connected"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}:{str(exc)[:80]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="ARTCB node differential diagnosis")
    ap.add_argument("--mac", default="http://127.0.0.1:8001")
    ap.add_argument("--seed", default="https://artcb.me")
    ap.add_argument("--out", default="logs/315_doctor_latest.json")
    args = ap.parse_args()
    t0 = time.time_ns()
    _dns_install()

    _row("operating_system", "PASS", detail=f"{platform.system()} {platform.release()} {platform.machine()}")

    # Dependencies / TPM class (honest)
    libtpms = shutil.which("libtpms") or (
        Path("/usr/local/Cellar/libtpms").is_dir() or Path("/opt/homebrew/Cellar/libtpms").is_dir()
    )
    swtpm_bin = shutil.which("swtpm")
    swtpm_cellar = Path("/usr/local/Cellar/swtpm").is_dir() or Path("/opt/homebrew/Cellar/swtpm").is_dir()
    tpm0 = Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists()
    if tpm0:
        _row("tpm_detection", "INFO", detail="device node present", impact="classify separately; not auto L4")
    elif swtpm_bin or swtpm_cellar:
        _row(
            "tpm_detection",
            "PASS",
            detail="SOFTWARE_TPM tooling present (swtpm)",
            impact="tests/dev only — not HARDWARE_TPM",
        )
    elif libtpms:
        _row(
            "tpm_detection",
            "FAIL",
            detail="libtpms present; swtpm missing",
            impact="SOFTWARE_TPM incomplete",
            action="finish brew install swtpm; never recast as hardware TPM",
        )
    else:
        _row("tpm_detection", "FAIL", detail="no /dev/tpm0, no swtpm", impact="ABSENT_TPM / SOFTWARE_TPM needed for sim")

    if len(_key()) >= 16:
        _row("api_key", "PASS", detail="present (value not printed)")
    else:
        _row("api_key", "FAIL", detail="ARTCB_API_KEY missing", action="export key / cursor_agent.env")

    # Prefer a public HTTPS endpoint that answers 200 (1.1.1.1 often 403 on GET /).
    ok, detail = _http_ok("https://cloudflare.com/cdn-cgi/trace", timeout=8.0)
    if not ok:
        ok2, d2 = _tcp("1.1.1.1", 443, timeout=5.0)
        ok, detail = ok2, f"trace_fail={detail}; tcp_443={d2}"
    _row("internet", "PASS" if ok else "FAIL", detail=detail)

    ok, detail = _http_ok(f"{args.seed.rstrip('/')}/health", timeout=20.0)
    _row(
        "artcb_https",
        "PASS" if ok else "FAIL",
        detail=detail,
        impact="" if ok else "cannot reach seed HTTPS",
        action="" if ok else "check DNS poison / captive portal / artcb_dns_fix",
    )

    # Transport layers (R316): API :8000 ≠ native P2P :18444 ≠ HTTPS :443 relay
    _row(
        "transport_model",
        "INFO",
        detail="API HTTP :8000 | native P2P :18444 | HTTPS :443 relay | overlay future",
        impact="IPv4:8000 timeout ≠ proof that native P2P protocol is :8000",
    )
    ok8000, d8000 = _tcp("152.228.144.34", 8000, timeout=4.0)
    _row(
        "api_tcp_outbound_8000",
        "PASS" if ok8000 else "FAIL",
        detail=d8000,
        impact="" if ok8000 else "seed API IPv4:8000 blocked (hybrid sync path)",
        action="" if ok8000 else "use HTTPS *.artcb.me:443 (R314) — not a native :18444 failure alone",
    )
    ok18444, d18444 = _tcp("152.228.144.34", 18444, timeout=4.0)
    _row(
        "p2p_native_tcp_18444",
        "PASS" if ok18444 else "FAIL",
        detail=d18444,
        impact="" if ok18444 else "native P2P port not reachable from this network",
        action="multi-transport: IPv6 → IPv4:18444 → overlay → HTTPS relay",
    )
    # IPv6 presence (not proof of inbound reachability)
    try:
        infos = socket.getaddrinfo("artcb.me", 443, socket.AF_INET6, socket.SOCK_STREAM)
        _row(
            "ipv6_dns_aaaa",
            "PASS" if infos else "FAIL",
            detail=f"aaaa_records={len(infos)}",
            impact="AAAA present ≠ inbound P2P open",
        )
    except Exception as exc:  # noqa: BLE001
        _row("ipv6_dns_aaaa", "FAIL", detail=f"{type(exc).__name__}:{exc}", impact="no IPv6 path measured")

    ok443, d443 = _http_ok(f"{args.seed.rstrip('/')}/api/v1/p2p/status", auth=True, timeout=25.0)
    _row(
        "https_relay_outbound_443",
        "PASS" if ok443 else "FAIL",
        detail=d443,
        impact="" if ok443 else "HTTPS seed unreachable",
    )
    _row(
        "p2p_inbound",
        "FAIL",
        detail="no measured public tunnel to this host (R287)",
        impact="Does NOT block outbound sync; blocks seed→Mac PBFT fan-in",
        action="Continue HTTPS_RELAY; overlay/VPN multi-VPS later — never IP=identity",
    )

    # ~~R315 names kept as aliases in profile below~~
    # Local node
    ok, detail = _http_ok(f"{args.mac.rstrip('/')}/health", timeout=8.0)
    _row("local_node_health", "PASS" if ok else "FAIL", detail=detail)

    fork = None
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"src:scripts:{env.get('PYTHONPATH','')}"
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "artcb_r315_fork_diagnose.py"),
                "--mac",
                args.mac,
                "--seed",
                args.seed,
                "--out",
                "logs/315_fork_diagnose_latest.json",
            ],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        fork_path = ROOT / "logs" / "315_fork_diagnose_latest.json"
        if fork_path.is_file():
            fork = json.loads(fork_path.read_text(encoding="utf-8"))
        verdict = (fork or {}).get("verdict") or "UNKNOWN"
        status = "PASS" if verdict in ("BEHIND_SAME_CHAIN", "EMPTY_CAN_BOOTSTRAP") else "FAIL"
        _row(
            "blockchain_sync",
            status,
            detail=f"verdict={verdict} tip_index={(fork or {}).get('local_tip_index')}",
            impact="anonymous public P2P cannot heal a private divergent tip",
            action="quarantine local divergent book then official/bootstrap catch-up — never wipe seeds",
        )
        if proc.returncode not in (0, 1):
            _row("fork_diagnose_runner", "FAIL", detail=proc.stderr[-300:] or proc.stdout[-300:])
    except Exception as exc:  # noqa: BLE001
        _row("blockchain_sync", "FAIL", detail=f"{type(exc).__name__}:{exc}")

    _row(
        "pbft_eligibility",
        "INFO",
        detail="membership JSON ≠ measured reachability; inbound FAIL ⇒ not a full validator dependency",
        impact="CERTIFIED_100 remains false until tip×N + quorum measured",
    )

    # Network capability profile
    profile = {
        "internet": next((c["status"] == "PASS" for c in CHECKS if c["name"] == "internet"), False),
        "https_outbound": next((c["status"] == "PASS" for c in CHECKS if c["name"] == "artcb_https"), False),
        "api_tcp_8000": next((c["status"] == "PASS" for c in CHECKS if c["name"] == "api_tcp_outbound_8000"), False),
        "p2p_native_18444": next((c["status"] == "PASS" for c in CHECKS if c["name"] == "p2p_native_tcp_18444"), False),
        # ~~R315 key~~ kept for readers:
        "p2p_tcp_outbound": next((c["status"] == "PASS" for c in CHECKS if c["name"] == "api_tcp_outbound_8000"), False),
        "p2p_https_outbound": next((c["status"] == "PASS" for c in CHECKS if c["name"] == "https_relay_outbound_443"), False),
        "p2p_inbound": False,
        "nat": "restricted_or_unknown",
        "mode": (
            "HTTPS_RELAY"
            if (not ok8000 and ok443)
            else ("DIRECT_API_OR_P2P" if (ok8000 or ok18444) else "OFFLINE_OR_DEGRADED")
        ),
    }

    report = {
        "ts_ns": time.time_ns(),
        "dur_ns": time.time_ns() - t0,
        "certified_100": False,
        "checks": CHECKS,
        "network_capability_profile": profile,
        "fork": {
            "verdict": (fork or {}).get("verdict"),
            "block0": (fork or {}).get("block0"),
            "decide_tally": (fork or {}).get("decide_tally"),
            "path": "logs/315_fork_diagnose_latest.json",
        },
        "states": {
            "identity": "stable_expected",
            "network": profile["mode"],
            "sync": (fork or {}).get("verdict") or "UNKNOWN",
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Human summary
    print("ARTCB DOCTOR")
    print("─" * 40)
    for i, c in enumerate(CHECKS, 1):
        print(f"[{i}/{len(CHECKS)}] {c['name']:<28} {c['status']}")
        if c.get("detail"):
            print(f"         {c['detail']}")
        if c["status"] == "FAIL" and c.get("impact"):
            print(f"         impact: {c['impact']}")
        if c.get("action"):
            print(f"         action: {c['action']}")
    print("─" * 40)
    print(f"mode={profile['mode']}  certified_100=false  out={out}")
    fails = sum(1 for c in CHECKS if c["status"] == "FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
