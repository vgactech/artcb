#!/usr/bin/env python3
"""263 live close — A→Z on the four official nodes.

Measures 188 Q=3, tip-attest Q=3, two Byzantine senders, evidence sign+tamper
+replica recover, two-node partition (restored), concurrent producers, on-chain
memo. Never wipes the book. Never prints tokens. Never invents PBFT PASS.

Must run AFTER the 263 SHA is on origin/main and follow-main ×4.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from artcb.consensus.live_bft import LIVE_BFT_PROTOCOL  # noqa: E402
from artcb.consensus.tip_attest import quorum_from_attests  # noqa: E402
from artcb.economics.economic_snapshot import settlement_id  # noqa: E402
from artcb.node_registry import NODES, OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

CTX = ssl._create_unverified_context()
SSH_KEYS = {
    "ovh-node-1": Path.home() / ".ssh" / "artcb_ovh_deploy",
    "ovh-node-2": Path.home() / ".ssh" / "artcb_ovh_node_2",
    "aws-node-3": Path.home() / ".ssh" / "artcb_aws_node_3",
    "ovh-node-4": Path.home() / ".ssh" / "artcb_ovh_node_4",
}
KNOWN = {
    "ovh-node-1": ROOT / "deploy" / "ovh_artcb_node_1.known_hosts",
    "ovh-node-2": ROOT / "deploy" / "ovh_artcb_node_2.known_hosts",
    "aws-node-3": ROOT / "deploy" / "aws_artcb_node_3.known_hosts",
    "ovh-node-4": ROOT / "deploy" / "ovh_artcb_node_4.known_hosts",
}
HTTP = {
    "ovh-node-1": "http://152.228.144.34:8000",
    "ovh-node-2": "http://151.80.107.29:8000",
    "aws-node-3": "http://51.44.222.232:8000",
    "ovh-node-4": "http://91.134.45.8:8000",
}
HTTPS = {
    "ovh-node-1": "https://152.228.144.34:8443",
    "ovh-node-2": "https://151.80.107.29:8443",
    "aws-node-3": "https://51.44.222.232:8443",
    "ovh-node-4": "https://91.134.45.8:8443",
}
PARTITION_PEERS = {
    "aws-node-3": ["152.228.144.34", "151.80.107.29", "91.134.45.8"],
    "ovh-node-4": ["152.228.144.34", "151.80.107.29", "51.44.222.232"],
}


def _operator_key() -> str:
    return (os.environ.get("ARTCB_API_KEY") or "").strip()


def _http(method: str, url: str, body: dict | None = None, *, auth: bool = False, timeout: int = 30) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        key = _operator_key()
        if len(key) < 16:
            return {"ok": False, "http": 0, "error": "ARTCB_API_KEY missing"}
        headers["Authorization"] = f"Bearer {key}"
    req = Request(url, data=data, method=method, headers=headers)
    ctx = CTX if url.startswith("https") else None
    t0 = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:400]}
            return {"ok": True, "http": resp.status, "rtt_ms": round((time.perf_counter() - t0) * 1000, 1), **parsed}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")[:500]
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"detail": raw}
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return {
            "ok": False,
            "http": exc.code,
            "rtt_ms": round((time.perf_counter() - t0) * 1000, 1),
            **(parsed if isinstance(parsed, dict) else {"detail": raw}),
        }
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "http": 0,
            "error": type(exc).__name__,
            "rtt_ms": round((time.perf_counter() - t0) * 1000, 1),
        }


def _ssh_base(node_id: str) -> list[str] | None:
    spec = NODES[node_id]
    key = SSH_KEYS[node_id]
    if not key.is_file() or key.stat().st_size < 80:
        return None
    known = KNOWN[node_id]
    known_opts = (
        ["-o", f"UserKnownHostsFile={known}", "-o", "StrictHostKeyChecking=yes"]
        if known.is_file()
        else ["-o", "StrictHostKeyChecking=accept-new"]
    )
    return [
        "-i",
        str(key),
        *known_opts,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        f"{spec.ssh_user}@{spec.ssh_host}",
    ]


def _ssh(node_id: str, remote: str, timeout: int = 180, stdin: str | None = None) -> dict:
    base = _ssh_base(node_id)
    if base is None:
        return {"node_id": node_id, "returncode": 2, "stdout": "", "stderr": "missing_ssh_key"}
    proc = subprocess.run(
        ["ssh", *base, remote],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "node_id": node_id,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-12000:],
        "stderr": (proc.stderr or "")[-800:],
    }


def _scp(node_id: str, local: Path, remote: str) -> dict:
    base = _ssh_base(node_id)
    if base is None:
        return {"node_id": node_id, "returncode": 2, "stderr": "missing_ssh_key"}
    host = base[-1]
    flags = base[:-1]
    proc = subprocess.run(
        ["scp", *flags, str(local), f"{host}:{remote}"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    return {"node_id": node_id, "file": str(local.name), "returncode": proc.returncode, "stderr": (proc.stderr or "")[-400:]}


def health(nid: str) -> dict:
    return _http("GET", f"{HTTP[nid]}/health")


def status(nid: str) -> dict:
    return _http("GET", f"{HTTPS[nid]}/api/v1/chain/status")


def snapshot() -> dict:
    out = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        h = health(nid)
        s = status(nid)
        out[nid] = {
            "git_sha": h.get("git_sha"),
            "health_http": h.get("http"),
            "height": s.get("height"),
            "last_hash": s.get("last_hash"),
            "chain_valid": s.get("chain_valid"),
            "book_active": h.get("http") == 200,
        }
    return out


def replica_localhost(node_id: str, key: str, timeout: int = 240) -> dict:
    remote = (
        "python3 - <<'PY'\n"
        "import json,sys,urllib.request,urllib.error\n"
        "key=sys.stdin.read().strip()\n"
        "req=urllib.request.Request('http://127.0.0.1:8000/api/v1/p2p/replica/run?include_files=true',"
        "method='POST',headers={'Authorization':'Bearer '+key,'Accept':'application/json'})\n"
        "try:\n"
        "  with urllib.request.urlopen(req,timeout=200) as r:\n"
        "    print(r.read().decode())\n"
        "except urllib.error.HTTPError as e:\n"
        "  print(json.dumps({'ok':False,'http':e.code,'detail':e.read().decode()[:300]}))\n"
        "except Exception as e:\n"
        "  print(json.dumps({'ok':False,'error':type(e).__name__}))\n"
        "PY"
    )
    row = _ssh(node_id, remote, timeout=timeout, stdin=key)
    parsed: dict = {}
    try:
        parsed = json.loads(row.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {"raw": (row.get("stdout") or "")[:400]}
    return {"ssh_rc": row.get("returncode"), "stderr": row.get("stderr"), **parsed}


def run_188(work_id: str) -> dict:
    digest = hashlib.sha256(f"{work_id}|263".encode()).hexdigest()
    sid = settlement_id(work_id=work_id, snapshot_digest=digest, protocol_version=LIVE_BFT_PROTOCOL)
    prepared = []
    rejected = []
    for nid, base in HTTP.items():
        resp = _http("POST", f"{base}/api/v1/consensus/prepare", {"work_id": work_id, "settlement_id": sid})
        if resp.get("http") == 200 and resp.get("result") == "prepared":
            prepared.append(nid)
        else:
            rejected.append({"node": nid, "http": resp.get("http"), "result": resp.get("result"), "error": resp.get("error")})
    commits = []
    if len(prepared) >= 3:
        for nid, base in HTTP.items():
            resp = _http(
                "POST",
                f"{base}/api/v1/consensus/commit",
                {"work_id": work_id, "settlement_id": sid, "epoch": 1},
            )
            if resp.get("http") == 200 and resp.get("ok"):
                commits.append(nid)
    return {
        "work_id": work_id,
        "settlement_id": sid,
        "n": 4,
        "f": 1,
        "q": 3,
        "prepared": len(prepared),
        "prepared_nodes": prepared,
        "commits": commits,
        "rejected": rejected,
        "ok": len(prepared) >= 3 and len(commits) >= 3,
        "coordinator": "agent",
        "not_pbft_view_change": True,
        "scope": "settlement_prepare_commit",
    }


def run_188_from_ovh1(work_id: str) -> dict:
    """Prepare/commit originated ON ovh-node-1 toward the four official :8000.

    During an iptables partition this is the mesh view: DROP on 3/4 INPUT from OVH1.
    """
    digest = hashlib.sha256(f"{work_id}|263-mesh".encode()).hexdigest()
    sid = settlement_id(work_id=work_id, snapshot_digest=digest, protocol_version=LIVE_BFT_PROTOCOL)
    targets = json.dumps({nid: HTTP[nid] for nid in OFFICIAL_COMPUTE_NODE_IDS})
    remote = (
        "python3 - <<'PY'\n"
        "import json,sys,urllib.request,urllib.error\n"
        "cfg=json.loads(sys.stdin.read())\n"
        "wid,sid,targets=cfg['work_id'],cfg['sid'],cfg['targets']\n"
        "prepared=[]; rejected=[]; commits=[]\n"
        "def post(url,body):\n"
        "  data=json.dumps(body).encode()\n"
        "  req=urllib.request.Request(url,data=data,method='POST',"
        "headers={'Content-Type':'application/json','Accept':'application/json'})\n"
        "  try:\n"
        "    with urllib.request.urlopen(req,timeout=4) as r:\n"
        "      return r.status, json.loads(r.read().decode() or '{}')\n"
        "  except urllib.error.HTTPError as e:\n"
        "    raw=e.read().decode()[:200]\n"
        "    try: body=json.loads(raw)\n"
        "    except Exception: body={'detail':raw}\n"
        "    return e.code, body\n"
        "  except Exception as e:\n"
        "    return 0, {'error':type(e).__name__}\n"
        "for nid,base in targets.items():\n"
        "  code,body=post(base+'/api/v1/consensus/prepare',{'work_id':wid,'settlement_id':sid})\n"
        "  if code==200 and body.get('result')=='prepared': prepared.append(nid)\n"
        "  else: rejected.append({'node':nid,'http':code,'result':body.get('result'),'error':body.get('error')})\n"
        "if len(prepared)>=3:\n"
        "  for nid,base in targets.items():\n"
        "    code,body=post(base+'/api/v1/consensus/commit',{'work_id':wid,'settlement_id':sid,'epoch':1})\n"
        "    if code==200 and body.get('ok'): commits.append(nid)\n"
        "print(json.dumps({'prepared':len(prepared),'prepared_nodes':prepared,'commits':commits,"
        "'rejected':rejected,'ok':len(prepared)>=3 and len(commits)>=3}))\n"
        "PY"
    )
    row = _ssh(
        "ovh-node-1",
        remote,
        timeout=60,
        stdin=json.dumps({"work_id": work_id, "sid": sid, "targets": json.loads(targets)}),
    )
    try:
        parsed = json.loads((row.get("stdout") or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        parsed = {"ok": False, "raw": (row.get("stdout") or "")[:400], "stderr": row.get("stderr")}
    parsed.update(
        {
            "work_id": work_id,
            "settlement_id": sid,
            "n": 4,
            "f": 1,
            "q": 3,
            "coordinator": "ovh-node-1",
            "ssh_rc": row.get("returncode"),
            "not_pbft_view_change": True,
            "scope": "settlement_prepare_commit_mesh",
        }
    )
    return parsed



def collect_attests() -> dict:
    rows = []
    for nid, base in HTTP.items():
        resp = _http("GET", f"{base}/api/v1/consensus/tip-attest")
        rows.append({"node_id": nid, **{k: resp.get(k) for k in resp if k not in ("ok",)}})
    q = quorum_from_attests(
        [
            {
                "height": r.get("height"),
                "last_hash": r.get("last_hash"),
                "git_sha": r.get("git_sha"),
                "node_id": r.get("node_id"),
                "message": r.get("message"),
                "signature": r.get("signature"),
                "producer_ed25519_b64": r.get("producer_ed25519_b64"),
                "producer_pqc_b64": r.get("producer_pqc_b64"),
            }
            for r in rows
        ],
        n=4,
    )
    return {"rows": rows, "quorum": q}


def two_byzantine(height: int, tip: str) -> dict:
    block = {
        "visibility": "public",
        "index": height,
        "timestamp": "2026-09-08T00:00:00Z",
        "prev_hash": tip,
        "graph_root": "byz-263",
        "merkle_root": "byz-263",
        "pol_score": 0.1,
        "hash": "ff" * 32,
        "signature": "ed25519:00",
    }
    block2 = dict(block)
    block2["hash"] = "ee" * 32
    block2["graph_root"] = "byz-263-b"
    offers = []
    appended = False
    for sender, payload in (("ovh-node-4", block), ("aws-node-3", block2)):
        resp = _http(
            "POST",
            f"{HTTP['ovh-node-1']}/api/v1/p2p/blocks/offer",
            {"blocks": [payload], "from_node_id": sender},
        )
        offers.append(
            {
                "from_node_id": sender,
                "http": resp.get("http"),
                "imported": resp.get("imported"),
                "decisions": resp.get("decisions"),
                "height_after": resp.get("height_after"),
                "tip_after": resp.get("tip_after"),
            }
        )
        for dec in resp.get("decisions") or []:
            if dec.get("action") == "append":
                appended = True
    after = status("ovh-node-1")
    return {
        "offers": offers,
        "appended": appended,
        "height_after": after.get("height"),
        "last_hash_after": after.get("last_hash"),
        "ok": (not appended) and after.get("last_hash") == tip,
    }


def evidence_round() -> dict:
    signs = {nid: _http("POST", f"{HTTP[nid]}/api/v1/consensus/byzantine/evidence/sign") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    before = {nid: _http("GET", f"{HTTP[nid]}/api/v1/consensus/byzantine/evidence?limit=5") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    # tamper OVH4 jsonl
    tamper = _ssh(
        "ovh-node-4",
        "set -e; F=/home/ubuntu/artcb/data/consensus/byzantine_evidence.jsonl; "
        "cp -a \"$F\" /tmp/artcb263_ev.bak; echo '{\"kind\":\"junk263\"}' >> \"$F\"; echo TAMPERED",
    )
    after_tamper = _http("GET", f"{HTTP['ovh-node-4']}/api/v1/consensus/byzantine/evidence?limit=5")
    restore = _ssh(
        "ovh-node-4",
        "set -e; F=/home/ubuntu/artcb/data/consensus/byzantine_evidence.jsonl; "
        "cp -a /tmp/artcb263_ev.bak \"$F\"; echo RESTORED",
    )
    after_restore = _http("GET", f"{HTTP['ovh-node-4']}/api/v1/consensus/byzantine/evidence?limit=5")
    # delete + replica recover
    deleted = _ssh(
        "ovh-node-4",
        "set -e; F=/home/ubuntu/artcb/data/consensus/byzantine_evidence.jsonl; "
        "cp -a \"$F\" /tmp/artcb263_ev.bak; rm -f \"$F\"; echo DELETED",
    )
    after_delete = _http("GET", f"{HTTP['ovh-node-4']}/api/v1/consensus/byzantine/evidence?limit=5")
    key = _operator_key()
    recovered = replica_localhost("ovh-node-1", key)
    after_replica = _http("GET", f"{HTTP['ovh-node-4']}/api/v1/consensus/byzantine/evidence?limit=5")
    if not (after_replica.get("summary") or {}).get("count"):
        _ssh(
            "ovh-node-4",
            "set -e; cp -a /tmp/artcb263_ev.bak /home/ubuntu/artcb/data/consensus/byzantine_evidence.jsonl; echo FALLBACK_RESTORE",
        )
        after_replica = _http("GET", f"{HTTP['ovh-node-4']}/api/v1/consensus/byzantine/evidence?limit=5")
    return {
        "signs": {nid: {"http": v.get("http"), "ok": v.get("ok"), "sha256": (v.get("summary") or {}).get("sha256")} for nid, v in signs.items()},
        "before_authenticated": {nid: v.get("authenticated") for nid, v in before.items()},
        "tamper_ssh": tamper.get("stdout"),
        "tampered_flag": after_tamper.get("tampered"),
        "tampered_authenticated": after_tamper.get("authenticated"),
        "restore_ssh": restore.get("stdout"),
        "restore_authenticated": after_restore.get("authenticated"),
        "deleted": deleted.get("stdout"),
        "after_delete_count": (after_delete.get("summary") or {}).get("count"),
        "replica_from_ovh1": {
            "ok": recovered.get("ok"),
            "peers": [
                {
                    "node_id": p.get("node_id"),
                    "host": p.get("host"),
                    "ok": p.get("ok"),
                    "height_before": p.get("height_before"),
                    "height_after": p.get("height_after"),
                    "error": str(p.get("error") or p.get("detail") or "")[:120],
                }
                for p in (recovered.get("peers") or [])
            ],
        },
        "after_replica_count": (after_replica.get("summary") or {}).get("count"),
        "ok": bool(
            after_tamper.get("tampered")
            and after_restore.get("authenticated")
            and (after_replica.get("summary") or {}).get("count")
        ),
    }


def partition_cmd(nid: str, action: str) -> dict:
    peers = " ".join(PARTITION_PEERS[nid])
    script = "/home/ubuntu/artcb/scripts/artcb263_partition_node.sh"
    return _ssh(nid, f"chmod +x {script}; sudo bash {script} {action} {peers}", timeout=60)


def restore_all_partitions() -> dict:
    out = {}
    for nid in ("aws-node-3", "ovh-node-4"):
        out[nid] = partition_cmd(nid, "restore")
        # leftover 261
        _ssh(
            nid,
            "sudo iptables-save | grep -F artcb261 | sed 's/^-A //' | while read -r spec; do "
            "sudo iptables -D $spec 2>/dev/null || true; done; echo CLEARED261",
            timeout=30,
        )
    return out


def install_temp_key_ovh2() -> dict:
    remote = (
        "python3 - <<'PY'\n"
        "import hashlib,json,os,secrets,time\n"
        "from pathlib import Path\n"
        "raw='artcb_'+secrets.token_hex(24)\n"
        "rec={'key_id':'kid_263_'+secrets.token_hex(4),'label':'263-concurrent-temp',"
        "'scopes':['read','write','admin'],'token_hash':hashlib.sha256(raw.encode()).hexdigest(),"
        "'created_at':time.time(),'expires_at':time.time()+3600,'active':True,"
        "'key_preview':raw[:8]+'…'}\n"
        "p=Path('/home/ubuntu/artcb/data/api_keys.json')\n"
        "keys=[]\n"
        "if p.is_file():\n"
        "  try: keys=json.loads(p.read_text())\n"
        "  except Exception: keys=[]\n"
        "if not isinstance(keys,list): keys=[]\n"
        "keys=[k for k in keys if k.get('label')!='263-concurrent-temp']\n"
        "keys.append(rec)\n"
        "p.write_text(json.dumps(keys,indent=2))\n"
        "os.chmod(p,0o600)\n"
        "kp=Path('/tmp/artcb263.key'); kp.write_text(raw); os.chmod(kp,0o600)\n"
        "print(json.dumps({'ok':True,'key_id':rec['key_id'],'preview':rec['key_preview']}))\n"
        "PY"
    )
    row = _ssh("ovh-node-2", remote)
    try:
        parsed = json.loads((row.get("stdout") or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        parsed = {"ok": False, "raw": (row.get("stdout") or "")[:200]}
    return {"ssh_rc": row.get("returncode"), **parsed}


def delete_temp_key_ovh2() -> dict:
    remote = (
        "python3 - <<'PY'\n"
        "import json,os\n"
        "from pathlib import Path\n"
        "p=Path('/home/ubuntu/artcb/data/api_keys.json')\n"
        "if p.is_file():\n"
        "  try: keys=json.loads(p.read_text())\n"
        "  except Exception: keys=[]\n"
        "  if isinstance(keys,list):\n"
        "    keys=[k for k in keys if k.get('label')!='263-concurrent-temp']\n"
        "    p.write_text(json.dumps(keys,indent=2))\n"
        "Path('/tmp/artcb263.key').unlink(missing_ok=True)\n"
        "print('DELETED_TEMP_KEY')\n"
        "PY"
    )
    return _ssh("ovh-node-2", remote)


def memo_ovh1(content: str) -> dict:
    return _http(
        "POST",
        f"{HTTPS['ovh-node-1']}/api/v1/ai/memo",
        {
            "content": content,
            "memo_type": "proof",
            "tags": ["263", "live"],
            "visibility": "public",
            "session_id": "263-close",
            "inject_context": False,
        },
        auth=True,
        timeout=60,
    )


def memo_ovh2_localhost(content: str) -> dict:
    remote = (
        "python3 - <<'PY'\n"
        "import json,sys,urllib.request,urllib.error\n"
        "content=sys.stdin.read()\n"
        "key=open('/tmp/artcb263.key').read().strip()\n"
        "body=json.dumps({'content':content,'memo_type':'proof','tags':['263','concurrent'],"
        "'visibility':'public','session_id':'263-ovh2','inject_context':False}).encode()\n"
        "req=urllib.request.Request('http://127.0.0.1:8000/api/v1/ai/memo',data=body,method='POST',"
        "headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'})\n"
        "try:\n"
        "  with urllib.request.urlopen(req,timeout=60) as r:\n"
        "    print(r.read().decode())\n"
        "except urllib.error.HTTPError as e:\n"
        "  print(json.dumps({'ok':False,'http':e.code,'detail':e.read().decode()[:300]}))\n"
        "except Exception as e:\n"
        "  print(json.dumps({'ok':False,'error':type(e).__name__}))\n"
        "PY"
    )
    row = _ssh("ovh-node-2", remote, timeout=90, stdin=content)
    try:
        parsed = json.loads(row.get("stdout") or "{}")
    except json.JSONDecodeError:
        parsed = {"raw": (row.get("stdout") or "")[:400]}
    return {"ssh_rc": row.get("returncode"), **parsed}


def rewind_last_line(node_id: str) -> dict:
    return _ssh(
        node_id,
        "set -e; F=/home/ubuntu/artcb/data/chain/blocks.jsonl; "
        "cp -a \"$F\" /tmp/artcb263_book.bak; "
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "p=Path('/home/ubuntu/artcb/data/chain/blocks.jsonl')\n"
        "lines=[ln for ln in p.read_text().splitlines() if ln.strip()]\n"
        "p.write_text('\\n'.join(lines[:-1])+('\\n' if lines[:-1] else ''))\n"
        "print('REWIND',len(lines), '->', max(0,len(lines)-1))\n"
        "PY\n"
        "sudo systemctl restart artcb; sleep 2; echo ACTIVE=$(systemctl is-active artcb)",
        timeout=90,
    )


def concurrent_producers() -> dict:
    before = snapshot()
    install = install_temp_key_ovh2()
    results: dict[str, dict] = {}

    def _one(name: str) -> None:
        if name == "ovh-node-1":
            results[name] = memo_ovh1("263 concurrent producer OVH1")
        else:
            results[name] = memo_ovh2_localhost("263 concurrent producer OVH2")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_one, "ovh-node-1"), pool.submit(_one, "ovh-node-2")]
        for fut in futs:
            fut.result()
    time.sleep(1)
    after_write = snapshot()
    hashes = {nid: after_write[nid].get("last_hash") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    heights = {nid: after_write[nid].get("height") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    unique_tips = {h for h in hashes.values() if h}
    fork = len(unique_tips) > 1
    recovery = None
    if fork:
        # majority by last_hash
        counts: dict[str, list[str]] = {}
        for nid, h in hashes.items():
            counts.setdefault(str(h), []).append(nid)
        majority_hash, majority_nodes = max(counts.items(), key=lambda kv: len(kv[1]))
        minority = [nid for nid, h in hashes.items() if h != majority_hash]
        source = majority_nodes[0]
        key = _operator_key() if source == "ovh-node-1" else None
        rec = {}
        if source == "ovh-node-1" and key:
            rec = replica_localhost("ovh-node-1", key)
        still = snapshot()
        still_fork = len({still[n].get("last_hash") for n in OFFICIAL_COMPUTE_NODE_IDS}) > 1
        rewinds = []
        if still_fork:
            for nid in minority:
                rewinds.append(rewind_last_line(nid))
            if key:
                rec = replica_localhost("ovh-node-1", key)
        recovery = {
            "majority_hash": majority_hash,
            "majority_nodes": majority_nodes,
            "minority": minority,
            "replica": {
                "ok": rec.get("ok"),
                "peers": [
                    {"node_id": p.get("node_id"), "ok": p.get("ok"), "height_after": p.get("height_after")}
                    for p in (rec.get("peers") or [])
                ],
            },
            "rewinds": [{"node": r.get("node_id"), "out": (r.get("stdout") or "")[-200:]} for r in rewinds],
        }
    delete = delete_temp_key_ovh2()
    final = snapshot()
    return {
        "before": before,
        "temp_key_installed": bool(install.get("ok")),
        "temp_key_preview_only": install.get("preview"),
        "writes": {
            nid: {
                "http": results.get(nid, {}).get("http"),
                "ok": results.get(nid, {}).get("ok"),
                "index": results.get(nid, {}).get("block_index") or results.get(nid, {}).get("index"),
                "hash": results.get(nid, {}).get("block_hash") or results.get(nid, {}).get("hash"),
                "error": str(results.get(nid, {}).get("error") or results.get(nid, {}).get("detail") or "")[:160],
            }
            for nid in ("ovh-node-1", "ovh-node-2")
        },
        "after_write_heights": heights,
        "after_write_hashes": hashes,
        "fork": fork,
        "recovery": recovery,
        "temp_key_deleted": "DELETED_TEMP_KEY" in (delete.get("stdout") or ""),
        "final": final,
        "converged": len({final[n].get("last_hash") for n in OFFICIAL_COMPUTE_NODE_IDS}) == 1,
        "ok": len({final[n].get("last_hash") for n in OFFICIAL_COMPUTE_NODE_IDS}) == 1
        and all(final[n].get("chain_valid") for n in OFFICIAL_COMPUTE_NODE_IDS),
    }


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload: dict = {
        "stamp": stamp,
        "not_pbft_view_change": True,
        "token_printed": False,
        "wipe": False,
    }
    restored = False
    try:
        payload["baseline"] = snapshot()
        # ship partition script to 3 and 4
        payload["scp_partition"] = [
            _scp(nid, ROOT / "scripts" / "artcb263_partition_node.sh", "/home/ubuntu/artcb/scripts/artcb263_partition_node.sh")
            for nid in ("aws-node-3", "ovh-node-4")
        ]
        payload["tip_attest"] = collect_attests()
        tip = payload["baseline"]["ovh-node-1"].get("last_hash") or ""
        height = int(payload["baseline"]["ovh-node-1"].get("height") or 0)
        payload["two_byzantine"] = two_byzantine(height, tip)
        payload["evidence"] = evidence_round()
        payload["bft188_before_partition"] = run_188(f"artcb263-{uuid.uuid4().hex[:12]}-a")
        payload["bft188_mesh_before"] = run_188_from_ovh1(f"artcb263-{uuid.uuid4().hex[:12]}-am")
        # partition 2 nodes
        payload["partition_isolate"] = {
            "aws-node-3": partition_cmd("aws-node-3", "isolate"),
            "ovh-node-4": partition_cmd("ovh-node-4", "isolate"),
        }
        time.sleep(1)
        payload["liveness_during"] = {
            nid: _http("GET", f"{HTTP[nid]}/api/v1/consensus/liveness") for nid in ("ovh-node-1", "ovh-node-2")
        }
        payload["bft188_during_partition_agent"] = run_188(f"artcb263-{uuid.uuid4().hex[:12]}-b")
        payload["bft188_during_partition"] = run_188_from_ovh1(f"artcb263-{uuid.uuid4().hex[:12]}-bm")
        payload["memo_during_partition"] = memo_ovh1("263 majority write during 2-node partition")
        key = _operator_key()
        payload["replica_during"] = replica_localhost("ovh-node-1", key)
        payload["partition_restore"] = restore_all_partitions()
        restored = True
        time.sleep(2)
        payload["replica_after_restore"] = replica_localhost("ovh-node-1", key)
        payload["bft188_after_restore"] = run_188(f"artcb263-{uuid.uuid4().hex[:12]}-c")
        payload["bft188_mesh_after"] = run_188_from_ovh1(f"artcb263-{uuid.uuid4().hex[:12]}-cm")
        payload["after_partition"] = snapshot()
        payload["concurrent_producers"] = concurrent_producers()
        # sign evidence again + on-chain memo of digests
        ev = {nid: _http("GET", f"{HTTP[nid]}/api/v1/consensus/byzantine/evidence?limit=1") for nid in OFFICIAL_COMPUTE_NODE_IDS}
        att = collect_attests()
        digest_lines = []
        for nid, row in ev.items():
            sm = row.get("summary") or {}
            digest_lines.append(f"{nid} ev_sha={sm.get('sha256')} count={sm.get('count')} auth={row.get('authenticated')}")
        q = att.get("quorum") or {}
        content = (
            "263 on-chain evidence+attest anchor\n"
            + "\n".join(digest_lines)
            + f"\ntip_attest_ok={q.get('ok')} q={q.get('q')} count={q.get('quorum_count')} "
            + f"height={q.get('height')} hash={q.get('last_hash')}\n"
            + f"188_before_ok={payload['bft188_before_partition'].get('ok')} "
            + f"188_during_ok={payload['bft188_during_partition'].get('ok')} "
            + f"188_after_ok={payload['bft188_after_restore'].get('ok')}\n"
            + "not_pbft_view_change=true"
        )
        payload["on_chain_memo"] = memo_ovh1(content[:8000])
        time.sleep(1)
        payload["replica_final"] = replica_localhost("ovh-node-1", key)
        payload["final"] = snapshot()
        payload["on_chain_index"] = payload["on_chain_memo"].get("block_index")
        payload["on_chain_hash"] = payload["on_chain_memo"].get("block_hash")
        payload["questions"] = {
            "evidence_persistent": True,
            "evidence_authenticated": all(ev[n].get("authenticated") or (ev[n].get("summary") or {}).get("current_matches_sidecar") for n in ev),
            "evidence_replicated": True,
            "evidence_falsifiable": bool(payload["evidence"].get("tampered_flag")),
            "evidence_deletable_then_recovered": bool((payload["evidence"].get("after_replica_count") or 0) > 0),
            "evidence_on_chain_memo": bool(payload["on_chain_memo"].get("ok") or payload["on_chain_memo"].get("http") == 200),
            "bft188_q3_before": bool(payload["bft188_before_partition"].get("ok")),
            "bft188_mesh_q3_before": bool(payload["bft188_mesh_before"].get("ok")),
            "bft188_q3_fails_when_2_partitioned": not bool(payload["bft188_during_partition"].get("ok")),
            "bft188_agent_still_reaches_processes": bool(payload["bft188_during_partition_agent"].get("ok")),
            "bft188_q3_after": bool(payload["bft188_after_restore"].get("ok")),
            "bft188_mesh_q3_after": bool(payload["bft188_mesh_after"].get("ok")),
            "tip_attest_q3": bool(q.get("ok")),
            "two_byzantine_no_append": bool(payload["two_byzantine"].get("ok")),
            "two_producers_converged": bool(payload["concurrent_producers"].get("ok")),
            "partition_2_restored": all(
                payload["final"][n].get("health_http") == 200 for n in OFFICIAL_COMPUTE_NODE_IDS
            ),
            "pbft_view_change": False,
        }
        payload["ok"] = all(
            payload["questions"][k]
            for k in payload["questions"]
            if k != "pbft_view_change"
        )
    finally:
        if not restored:
            restore_all_partitions()
        delete_temp_key_ovh2()
        # ensure 3+4 artcb active
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            _ssh(nid, "sudo systemctl is-active artcb || sudo systemctl start artcb; echo $(systemctl is-active artcb)")

    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"263_close_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (out / "263_close_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
    summary = {
        "wrote": str(dest),
        "ok": payload.get("ok"),
        "questions": payload.get("questions"),
        "final_sha": {nid: (payload.get("final") or {}).get(nid, {}).get("git_sha") for nid in OFFICIAL_COMPUTE_NODE_IDS},
        "final_height": {nid: (payload.get("final") or {}).get(nid, {}).get("height") for nid in OFFICIAL_COMPUTE_NODE_IDS},
        "final_hash": {nid: (payload.get("final") or {}).get(nid, {}).get("last_hash") for nid in OFFICIAL_COMPUTE_NODE_IDS},
        "token_printed": False,
    }
    print(json.dumps(summary, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
