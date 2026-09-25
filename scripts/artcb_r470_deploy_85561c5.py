#!/usr/bin/env python3
"""R470 — Deploy 85561c5 on N2/N4 (SSH) + N3 (SSM via AWS).

Objective:
  git pull (fast-forward to 85561c5) + pip install + systemctl restart artcb
  on nodes N2 (OVH2 151.80.107.29), N4 (OVH4 91.134.45.8), N3 (AWS3 SSM).

Usage:
  python3 scripts/artcb_r470_deploy_85561c5.py

Pre-requisites:
  - SSH keys present at ~/.ssh/artcb_ovh_node_2 and ~/.ssh/artcb_ovh_node_4
  - Doppler project artcb3 configured (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
  - AWS SSM instance i-06c9404e42798ff76 reachable

Safety:
  - Never connects to OVH1 (D-036/D-040 — blocked per user decision)
  - Fail-open per node: failure on one node does not stop others
  - No wallet wipe, no chain reset
"""

import base64
import json
import os
import subprocess
import sys
import time

TARGET_SHA = "85561c5"
DEBUG = True

# ── SSH/SSM helpers ───────────────────────────────────────────────────────────

def get_doppler(key: str, project: str, config: str = "dev") -> str:
    r = subprocess.run(
        ["doppler", "secrets", "get", key, "--plain", "--project", project, "--config", config],
        capture_output=True, text=True,
    )
    val = r.stdout.strip()
    if DEBUG:
        masked = val[:4] + "…" if val else "(empty)"
        print(f"  [doppler] {key}={masked}", flush=True)
    return val


def load_key(path: str) -> str:
    p = os.path.expanduser(path)
    if os.path.exists(p):
        with open(p) as f:
            return f.read()
    print(f"  [WARN] SSH key absent: {p}", flush=True)
    return ""


def ssm_run(ssm_client, instance_id: str, cmd: str, timeout: int = 120) -> dict:
    resp = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [cmd]},
        TimeoutSeconds=timeout,
    )
    cid = resp["Command"]["CommandId"]
    for i in range(40):
        time.sleep(4)
        out = ssm_client.get_command_invocation(CommandId=cid, InstanceId=instance_id)
        status = out["Status"]
        if status in ("Success", "Failed", "TimedOut", "Cancelled"):
            return {
                "status": status,
                "stdout": out.get("StandardOutputContent", ""),
                "stderr": out.get("StandardErrorContent", ""),
            }
        if i % 5 == 0:
            print(f"    SSM status: {status}", flush=True)
    return {"status": "Timeout", "stdout": "", "stderr": ""}


# ── Deploy command (shared between SSH direct and SSH-via-SSM) ─────────────────

def make_deploy_cmd(node_ip: str, node_name: str, ssh_key: str) -> str:
    """Build the shell command executed on the relay (SSM) or directly (SSH)."""
    key_b64 = base64.b64encode(ssh_key.encode()).decode()
    return f"""
KEY_B64='{key_b64}'
KEYFILE=$(mktemp /tmp/artcb_r470_XXXXXX)
echo "$KEY_B64" | base64 -d > "$KEYFILE"
chmod 600 "$KEYFILE"

echo "=== R470 DEPLOY {node_name} ({node_ip}) ==="

ssh -i "$KEYFILE" \\
    -o StrictHostKeyChecking=no \\
    -o ConnectTimeout=15 \\
    -o BatchMode=yes \\
    ubuntu@{node_ip} "
echo '--- [1/5] SHA avant ---'
curl -s --connect-timeout 8 http://127.0.0.1:8000/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"SHA_BEFORE:\", d.get(\"git_sha\",\"?\"))' 2>/dev/null || echo 'HEALTH_BEFORE=DOWN'

echo '--- [2/5] git pull ---'
cd /home/ubuntu/artcb && git fetch origin main && git merge --ff-only origin/main && echo GIT_PULL_OK && git log --oneline -1

echo '--- [3/5] pip install ---'
cd /home/ubuntu/artcb && pip install -r requirements.txt --quiet 2>&1 | tail -3 && echo PIP_OK

echo '--- [4/5] systemctl restart ---'
sudo -n systemctl restart artcb && echo RESTART_OK || echo RESTART_FAILED

echo '--- [5/5] SHA apres (attente 6s) ---'
sleep 6
curl -s --connect-timeout 10 http://127.0.0.1:8000/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"SHA_AFTER:\", d.get(\"git_sha\",\"?\"), \"| height:\", d.get(\"height\",\"?\"), \"| status:\", d.get(\"status\",\"?\"))' 2>/dev/null || curl -sk --connect-timeout 10 https://127.0.0.1:8443/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"SHA_AFTER_TLS:\", d.get(\"git_sha\",\"?\"))' 2>/dev/null || echo 'HEALTH_AFTER=DOWN'
" 2>&1

rm -f "$KEYFILE"
"""


def deploy_ssh_direct(ip: str, name: str, key_path: str) -> dict:
    """Deploy directly via SSH from Mac (for nodes reachable without relay)."""
    ssh_key = load_key(key_path)
    if not ssh_key:
        return {"node": name, "status": "SKIP", "reason": f"key absent: {key_path}"}

    key_b64 = base64.b64encode(ssh_key.encode()).decode()
    cmd = f"""
set -e
KEYFILE=$(mktemp /tmp/artcb_r470_XXXXXX)
echo "{key_b64}" | base64 -d > "$KEYFILE"
chmod 600 "$KEYFILE"

ssh -i "$KEYFILE" \\
    -o StrictHostKeyChecking=no \\
    -o ConnectTimeout=15 \\
    -o BatchMode=yes \\
    ubuntu@{ip} "
echo '--- SHA avant ---'
curl -s --connect-timeout 8 http://127.0.0.1:8000/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\\\"SHA_BEFORE:\\\", d.get(\\\"git_sha\\\",\\\"?\\\"))' 2>/dev/null || echo HEALTH_BEFORE=DOWN
echo '--- git pull ---'
cd /home/ubuntu/artcb && git fetch origin main && git merge --ff-only origin/main && echo GIT_PULL_OK && git log --oneline -1
echo '--- pip install ---'
pip install -r requirements.txt --quiet 2>&1 | tail -3 && echo PIP_OK
echo '--- restart ---'
sudo -n systemctl restart artcb && echo RESTART_OK || echo RESTART_FAILED
echo '--- SHA apres ---'
sleep 6
curl -s --connect-timeout 10 http://127.0.0.1:8000/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\\\"SHA_AFTER:\\\", d.get(\\\"git_sha\\\",\\\"?\\\"), \\\"height:\\\", d.get(\\\"height\\\",\\\"?\\\"))' 2>/dev/null || echo HEALTH_AFTER=DOWN
" 2>&1

rm -f "$KEYFILE"
"""
    result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=90)
    output = result.stdout + result.stderr
    sha_ok = f"SHA_AFTER: {TARGET_SHA}" in output or TARGET_SHA[:7] in output
    return {
        "node": name,
        "status": "OK" if sha_ok else "WARN",
        "sha_ok": sha_ok,
        "output": output[-2000:],
    }


def deploy_via_ssm(ssm_client, instance_id: str, relay_ip: str, relay_key_path: str,
                   target_ip: str, target_name: str) -> dict:
    """Deploy via SSM relay → SSH to target node."""
    relay_key = load_key(relay_key_path)
    if not relay_key:
        return {"node": target_name, "status": "SKIP", "reason": f"relay key absent: {relay_key_path}"}

    cmd = make_deploy_cmd(target_ip, target_name, relay_key)
    print(f"\n  Sending SSM command for {target_name} via relay {relay_ip}…", flush=True)
    result = ssm_run(ssm_client, instance_id, cmd, timeout=120)
    output = result["stdout"] + result.get("stderr", "")
    sha_ok = f"SHA_AFTER: {TARGET_SHA}" in output or TARGET_SHA[:7] in output
    print(f"  SSM result: {result['status']} | sha_ok={sha_ok}", flush=True)
    if output.strip():
        print("  --- output ---")
        print(output[-2000:])
    return {
        "node": target_name,
        "status": result["status"],
        "sha_ok": sha_ok,
        "output": output[-2000:],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n{'='*60}")
    print(f"R470 DEPLOY — target SHA: {TARGET_SHA}")
    print(f"Nodes: N2(OVH2) + N4(OVH4) via SSH direct | N3(AWS3) via SSM")
    print(f"OVH1 = BLOQUÉ (D-036) — skip")
    print(f"{'='*60}\n")

    results = []

    # ── N2 (OVH2 — SSH direct depuis Mac) ────────────────────────────────────
    print("\n[N2 OVH2 — SSH direct]")
    r2 = deploy_ssh_direct("151.80.107.29", "N2-OVH2", "~/.ssh/artcb_ovh_node_2")
    results.append(r2)
    print(f"  → {r2['node']} : {r2['status']} | sha_ok={r2.get('sha_ok')}")
    if DEBUG and r2.get("output"):
        print("  --- N2 output ---")
        print(r2["output"][-1500:])

    # ── N4 (OVH4 — SSH direct depuis Mac) ────────────────────────────────────
    print("\n[N4 OVH4 — SSH direct]")
    r4 = deploy_ssh_direct("91.134.45.8", "N4-OVH4", "~/.ssh/artcb_ovh_node_4")
    results.append(r4)
    print(f"  → {r4['node']} : {r4['status']} | sha_ok={r4.get('sha_ok')}")
    if DEBUG and r4.get("output"):
        print("  --- N4 output ---")
        print(r4["output"][-1500:])

    # ── N3 (AWS3 — via SSM) ────────────────────────────────────────────────────
    print("\n[N3 AWS3 — via SSM]")
    try:
        import boto3  # type: ignore
        ak = get_doppler("AWS_ACCESS_KEY_ID", "artcb3")
        asc = get_doppler("AWS_SECRET_ACCESS_KEY", "artcb3")
        if not ak or not asc:
            print("  SKIP N3 — AWS credentials absent (Doppler artcb3 inaccessible)")
            r3 = {"node": "N3-AWS3", "status": "SKIP", "reason": "AWS credentials absent"}
        else:
            session = boto3.Session(
                aws_access_key_id=ak,
                aws_secret_access_key=asc,
                region_name="eu-west-3",
            )
            ssm = session.client("ssm")
            # N3 est accédé via SSM directement (pas de relay SSH intermédiaire)
            ssm_instance = "i-06c9404e42798ff76"
            cmd_n3 = """
echo '--- SHA avant ---'
curl -s --connect-timeout 8 http://127.0.0.1:8000/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print("SHA_BEFORE:", d.get("git_sha","?"))' 2>/dev/null || echo HEALTH_BEFORE=DOWN
echo '--- git pull ---'
cd /home/ubuntu/artcb && git fetch origin main && git merge --ff-only origin/main && echo GIT_PULL_OK && git log --oneline -1
echo '--- pip install ---'
pip install -r requirements.txt --quiet 2>&1 | tail -3 && echo PIP_OK
echo '--- restart ---'
sudo -n systemctl restart artcb && echo RESTART_OK || echo RESTART_FAILED
echo '--- SHA apres ---'
sleep 6
curl -s --connect-timeout 10 http://127.0.0.1:8000/health 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print("SHA_AFTER:", d.get("git_sha","?"), "height:", d.get("height","?"))' 2>/dev/null || echo HEALTH_AFTER=DOWN
"""
            res3 = ssm_run(ssm, ssm_instance, cmd_n3, timeout=120)
            output3 = res3["stdout"] + res3.get("stderr", "")
            sha_ok3 = TARGET_SHA[:7] in output3
            r3 = {"node": "N3-AWS3", "status": res3["status"], "sha_ok": sha_ok3, "output": output3[-2000:]}
            print(f"  → N3-AWS3 : {res3['status']} | sha_ok={sha_ok3}")
            if DEBUG and output3.strip():
                print("  --- N3 output ---")
                print(output3[-1500:])
    except ImportError:
        print("  SKIP N3 — boto3 non installé")
        r3 = {"node": "N3-AWS3", "status": "SKIP", "reason": "boto3 absent"}
    except Exception as exc:
        print(f"  ERROR N3 : {exc}")
        r3 = {"node": "N3-AWS3", "status": "ERROR", "reason": str(exc)}

    results.append(r3)

    # ── Résumé ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"R470 DEPLOY SUMMARY — SHA cible: {TARGET_SHA}")
    print(f"{'='*60}")
    ok_count = 0
    for r in results:
        sha_ok = r.get("sha_ok", False)
        status = r.get("status", "?")
        symbol = "✅" if sha_ok else ("⚠️" if status == "SKIP" else "❌")
        print(f"  {symbol} {r['node']} : {status} | sha_ok={sha_ok}")
        if sha_ok:
            ok_count += 1

    print(f"\nNœuds confirmés sur {TARGET_SHA}: {ok_count}/3")
    print(f"OVH1 = BLOQUÉ (D-036) — non déployé intentionnellement")
    print(f"CERTIFIED_100=false")
    print(f"{'='*60}\n")

    # Sauvegarder le log
    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = f"logs/R470_deploy_{ts}.json"
    os.makedirs("logs", exist_ok=True)
    with open(log_path, "w") as f:
        json.dump({
            "r": "R470",
            "target_sha": TARGET_SHA,
            "timestamp": ts,
            "results": [
                {k: v for k, v in r.items() if k != "output"} for r in results
            ],
            "ok_count": ok_count,
        }, f, indent=2)
    print(f"Log sauvegardé: {log_path}")

    return 0 if ok_count >= 2 else 1  # SUCCESS si ≥ 2/3 nœuds déployés


if __name__ == "__main__":
    sys.exit(main())
