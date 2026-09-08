#!/usr/bin/env python3
"""Issue #77 — live P0 after R273 is actually deployed.

Does not recast pre-deploy GAP as PASS. Does not recast N04 50% as PASS.
Does not claim CERTIFIED_100. Does not wipe the book.
Does not treat HTTP 200 not_accepted as an identity reject.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
import run_live271_close_not_proven as l271  # noqa: E402
from artcb.consensus.campaign_artifacts import write_campaign  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
BINDING_REJECT = {
    "invalid_replica_key_binding",
    "invalid_replica_pqc_binding",
    "unregistered_replica_key",
    "replica_key_revoked",
    "unknown_replica_id",
}
IDENTITY_PASSED_LATER = {"not_accepted", "wrong_view", "not_prepared"}
SIGNERS = ("ovh-node-1", "ovh-node-2", "aws-node-3")


def _reason(got: dict) -> str:
    return str(got.get("detail") or got.get("reason") or "")


def _classify(posts: dict[str, dict]) -> tuple[str, list[str], dict[str, str]]:
    passed: list[str] = []
    rejected: dict[str, str] = {}
    for nid, got in posts.items():
        reason = _reason(got)
        if reason in BINDING_REJECT or (got.get("http") == 409 and reason in BINDING_REJECT):
            rejected[nid] = reason
        elif got.get("ok") is True or reason in IDENTITY_PASSED_LATER:
            passed.append(nid)
    return ("BOUND" if rejected and not passed else "GAP" if passed else "NOT_PROVEN"), passed, rejected


def _collect(nid: str) -> dict:
    health = l265._http("GET", f"{HTTP[nid]}/health")
    view = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/view")
    finality = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/pbft/finality")
    attest = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/tip-attest")
    ident = l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/replica-identity")
    return {
        "health": health,
        "pbft": {"view": view, "finality": finality},
        "network": {
            "git_sha": health.get("git_sha"),
            "height": attest.get("height"),
            "last_hash": attest.get("last_hash"),
            "view": view.get("view"),
        },
        "attest": {
            "node_id": attest.get("node_id"),
            "producer_ed25519_b64": attest.get("producer_ed25519_b64"),
            "height": attest.get("height"),
            "last_hash": attest.get("last_hash"),
        },
        "identity": {
            "binding_enforced": ident.get("binding_enforced"),
            "local_replica_id": ident.get("local_replica_id"),
            "test_override": ident.get("test_override"),
            "replicas": ident.get("replicas"),
        },
    }


def _pset_digest(prepared: list) -> str:
    material = json.dumps(prepared, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _forge(signer: str, claimed: str, *, kind: str = "prepare", prepared: list | None = None) -> dict:
    if kind == "view-change-265":
        prepared = list(prepared or [])
        digest = _pset_digest(prepared)
        message_py = f'msg = f"VC265|16|15|{claimed}|{digest}"'
        extra = (
            f'"view": 16, "from_view": 15, "prepared": {json.dumps(prepared)}, '
            f'"pset_digest": {digest!r},'
        )
    else:
        message_py = f'msg = f"P|15|500|{{digest}}|{claimed}"'
        extra = '"view": 15, "seq": 500, "digest": digest,'
    remote = f"""
set -e
sudo -n bash -lc 'set -a; source /etc/artcb/doppler.env; set +a; cd /home/ubuntu/artcb; export PYTHONPATH=src; doppler run -- .venv/bin/python3 -' <<'PY'
import json
from nacl import encoding, signing
from artcb.config import load_settings
from artcb.wallet.encryption import decrypt_private_key, is_encrypted_key_blob
settings = load_settings()
raw = (settings.data_dir / "chain.key").read_bytes()
seed = decrypt_private_key(raw) if is_encrypted_key_blob(raw) else raw[:32]
sk = signing.SigningKey(seed)
ed = sk.verify_key.encode(encoder=encoding.Base64Encoder).decode("ascii")
digest = "aa" * 32
claimed = {claimed!r}
{message_py}
sig = sk.sign(msg.encode("utf-8")).signature
row = {{
    "kind": {kind!r},
    "protocol": "265-pbft-block-finality",
    "message": msg,
    "replica_id": claimed,
    "signature": f"ed25519:{{sig.hex()}}",
    "producer_ed25519_b64": ed,
    "producer_pqc_b64": "",
    {extra}
}}
print(json.dumps(row))
PY
"""
    got = l265._ssh(signer, remote, timeout=60)
    forged = None
    for line in reversed((got.get("stdout") or "").strip().splitlines()):
        if line.startswith("{") and "replica_id" in line:
            try:
                forged = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    return {"ssh_rc": got.get("returncode"), "stderr": (got.get("stderr") or "")[-180:], "row": forged}


def _post_prepare(row: dict) -> dict[str, dict]:
    return {
        nid: l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": row})
        for nid in ("ovh-node-2", "aws-node-3", "ovh-node-4")
    }


def _post_vc(row: dict) -> dict[str, dict]:
    return {
        nid: l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change-265", {"view": 16, "view_change": row})
        for nid in OFFICIAL_COMPUTE_NODE_IDS
    }


def _analyze_http(view_changes: list[dict], target: str = "ovh-node-4") -> dict:
    got = l265._http(
        "POST",
        f"{HTTP[target]}/api/v1/consensus/pbft/analyze-new-view",
        {"view_changes": view_changes},
        timeout=20,
    )
    analysis = got.get("analysis") if isinstance(got.get("analysis"), dict) else {}
    return {
        "http": got.get("http"),
        "ok": got.get("ok"),
        "error": got.get("error") or got.get("detail"),
        "selected_is_none": got.get("selected_is_none"),
        "bound": got.get("bound"),
        "analysis": analysis,
    }


def _select_http(view_changes: list[dict], target: str = "ovh-node-4") -> dict:
    got = l265._http(
        "POST",
        f"{HTTP[target]}/api/v1/consensus/pbft/select-prepared",
        {"view_changes": view_changes},
        timeout=20,
    )
    return {
        "http": got.get("http"),
        "ok": got.get("ok"),
        "chosen_is_none": got.get("chosen") is None,
        "bound": got.get("bound"),
        "analysis": got.get("analysis") if isinstance(got.get("analysis"), dict) else {},
        "error": got.get("error") or got.get("detail"),
    }


def _row(status: str, **extra) -> dict:
    return {"status": status, "certified_100": False, **extra}


def _nv_status(analysis: dict, *, want_quorum: bool, want_reason: str | None = None) -> str:
    if not analysis:
        return "NOT_PROVEN"
    quorum = analysis.get("quorum_ok")
    selected = analysis.get("selected")
    if selected is not None:
        return "FAIL"
    if quorum is not want_quorum:
        return "FAIL"
    if want_reason and analysis.get("reason") != want_reason:
        return "FAIL"
    return "PASS"


def _probe_tpm(nid: str) -> dict:
    got = l265._ssh(
        nid,
        "echo TPM0=$(test -e /dev/tpm0 && echo yes || echo no); "
        "echo TPMRM=$(test -e /dev/tpmrm0 && echo yes || echo no); "
        "echo TPM2=$(command -v tpm2_getcap >/dev/null && echo yes || echo no); "
        "ls /dev/tpm* 2>/dev/null | tr '\\n' ' '; echo; "
        "sudo -n tpm2_getcap properties-fixed 2>/dev/null | head -5 || true",
        timeout=20,
    )
    out = got.get("stdout") or ""
    return {
        "ssh_rc": got.get("returncode"),
        "stdout": out[-400:],
        "has_tpm0": "TPM0=yes" in out,
        "has_tpm2_tools": "TPM2=yes" in out,
        "quote": None,
        "note": "device presence ≠ attested quote",
    }


def _software_revocation_on_vm() -> dict:
    """Code-on-VM only. Does not mutate the live service registry."""
    remote = r"""
set -e
sudo -n bash -lc 'set -a; source /etc/artcb/doppler.env; set +a; cd /home/ubuntu/artcb; export PYTHONPATH=src; doppler run -- .venv/bin/python3 -' <<'PY'
import json
from src.artcb.consensus.replica_identity import (
    ReplicaKeyBinding, load_official_registry, override_replica_registry, verify_replica_key_binding,
)
reg = load_official_registry()
row = reg["ovh-node-2"]
with override_replica_registry({
    "ovh-node-2": ReplicaKeyBinding(node_id="ovh-node-2", ed25519_b64=row.ed25519_b64, pqc_b64=row.pqc_b64, revoked=True)
}):
    ok, reason = verify_replica_key_binding("ovh-node-2", row.ed25519_b64, row.pqc_b64)
print(json.dumps({"ok": ok, "reason": reason, "live_service_mutated": False}))
PY
"""
    got = l265._ssh("ovh-node-1", remote, timeout=40)
    parsed = None
    for line in reversed((got.get("stdout") or "").splitlines()):
        if line.startswith("{") and "reason" in line:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    return {"ssh_rc": got.get("returncode"), "stderr": (got.get("stderr") or "")[-160:], "result": parsed}


def _n04_50_isolated() -> dict:
    """50% loss on replicas only (keep ovh-node-1 reachable from the coordinator)."""
    if os.environ.get("ARTCB277_SKIP_N04") == "1":
        return {
            "status": "FAIL",
            "note": "skipped after prior hang. N04 50% remains FAIL. Not recast PASS.",
        }

    class _Timeout(Exception):
        pass

    def _alarm(_signum, _frame):
        raise _Timeout("n04_wall_timeout")

    n04: dict = {"status": "FAIL", "note": "N04 row requires 1–50%. This cell is 50% only."}
    replicas = ("ovh-node-2", "aws-node-3", "ovh-node-4")
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(45)
    try:
        applied = {nid: l271._netem(nid, "loss 50%") for nid in replicas}
        view = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view", timeout=8)
        from artcb.consensus.pbft_view import primary_of

        prim = primary_of(int(view.get("view") or 0))
        if prim == "ovh-node-1":
            propose_url = f"{HTTP[prim]}/api/v1/consensus/pbft/propose"
        else:
            propose_url = f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/propose"
        propose = l265._http(
            "POST",
            propose_url,
            {"graph_id": "277-n04-50", "graph_root": "n04", "source": "pbft:277-n04"},
            timeout=10,
        )
        certified = bool(propose.get("ok") and propose.get("digest"))
        n04 = {
            "status": "PASS" if certified else "FAIL",
            "propose": {k: propose.get(k) for k in ("ok", "http", "reason", "detail", "digest", "error")},
            "view": {k: view.get(k) for k in ("view", "primary", "http")},
            "netem_targets": list(replicas),
            "netem_applied": {k: (v.get("returncode"), (v.get("stdout") or "")[-80:]) for k, v in applied.items()},
            "note": "N04 row requires 1–50%. This cell is 50% only. Do not recast N04 PASS.",
        }
    except _Timeout:
        n04 = {"status": "FAIL", "error": "Timeout", "note": "50% isolated wall timeout. Not recast PASS."}
    except Exception as exc:
        n04 = {"status": "FAIL", "error": type(exc).__name__, "msg": str(exc)[:200], "note": "50% probe failed"}
    finally:
        signal.alarm(0)
        try:
            l271._clear_netem_all()
        except Exception:
            pass
        try:
            l265._http("GET", f"{HTTP['ovh-node-1']}/health", timeout=8)
        except Exception:
            pass
    return n04


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    origin_main = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    want_sha = (os.environ.get("ARTCB277_WANT_SHA") or origin_main).strip()
    nodes = {nid: _collect(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (nodes[nid]["health"] or {}).get("git_sha") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    bindings = {nid: (nodes[nid]["identity"] or {}).get("binding_enforced") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    sha_ok = all(s == want_sha for s in shas.values()) and origin_main == want_sha
    bind_ok = all(v is True for v in bindings.values())
    results: dict = {
        "phase1_sha_x4": _row("PASS" if sha_ok else "FAIL", shas=shas, origin_main=origin_main, want=want_sha),
        "phase1_binding_enforced_x4": _row("PASS" if bind_ok else "FAIL", bindings=bindings),
    }
    if not sha_ok or not bind_ok:
        results["stopped"] = "phase1_incomplete_no_identity_live"
        payload = {"ok": False, "certified_100": False, "results": results, "stamp": stamp}
        (ROOT / "logs" / f"277_issue77_{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 2

    a1 = _forge("ovh-node-1", "ovh-node-1")
    a1_posts = _post_prepare(a1["row"]) if a1.get("row") else {}
    a1_v, a1_pass, a1_rej = _classify(a1_posts) if a1_posts else ("NOT_PROVEN", [], {})
    results["a1_k1_as_node1"] = _row(
        "PASS" if a1_pass and not a1_rej else "FAIL" if a1_rej else "NOT_PROVEN",
        verdict=a1_v,
        identity_passed=a1_pass,
        binding_rejected=a1_rej,
        posts={n: {k: a1_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in a1_posts},
    )

    a3 = _forge("ovh-node-1", "ovh-node-2")
    a3_posts = _post_prepare(a3["row"]) if a3.get("row") else {}
    a3_v, a3_pass, a3_rej = _classify(a3_posts) if a3_posts else ("NOT_PROVEN", [], {})
    a3_ok = a3_v == "BOUND" and not a3_pass and set(a3_rej) == {"ovh-node-2", "aws-node-3", "ovh-node-4"}
    results["a3_k1_as_node2"] = _row(
        "PASS" if a3_ok else "GAP" if a3_pass else "FAIL",
        verdict=a3_v,
        identity_passed=a3_pass,
        binding_rejected=a3_rej,
        posts={n: {k: a3_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in a3_posts},
        note="200 not_accepted after verify_prepare = GAP, not PASS",
    )
    print("A3", results["a3_k1_as_node2"]["status"], a3_v, a3_rej, a3_pass, flush=True)

    a7 = _forge("ovh-node-2", "ovh-node-1")
    a7_posts = _post_prepare(a7["row"]) if a7.get("row") else {}
    a7_v, a7_pass, a7_rej = _classify(a7_posts) if a7_posts else ("NOT_PROVEN", [], {})
    a7_ok = a7_v == "BOUND" and not a7_pass
    results["a7_k2_as_node1"] = _row(
        "PASS" if a7_ok else "GAP" if a7_pass else "FAIL",
        verdict=a7_v,
        identity_passed=a7_pass,
        binding_rejected=a7_rej,
        posts={n: {k: a7_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in a7_posts},
    )
    print("A7", results["a7_k2_as_node1"]["status"], a7_v, a7_rej, a7_pass, flush=True)

    unknown = dict(a3.get("row") or {})
    if unknown:
        unknown["producer_ed25519_b64"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        unknown["signature"] = "ed25519:" + ("00" * 64)
    unk_posts = _post_prepare(unknown) if unknown else {}
    unk_v, unk_pass, unk_rej = _classify(unk_posts) if unk_posts else ("NOT_PROVEN", [], {})
    results["unknown_key"] = _row(
        "PASS" if unk_v == "BOUND" and not unk_pass else "FAIL" if unk_pass else "NOT_PROVEN",
        verdict=unk_v,
        identity_passed=unk_pass,
        binding_rejected=unk_rej,
        posts={n: {k: unk_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in unk_posts},
    )

    bad_sig = dict(a1.get("row") or {})
    if bad_sig and isinstance(bad_sig.get("signature"), str) and bad_sig["signature"].startswith("ed25519:"):
        hx = bad_sig["signature"].split(":", 1)[1]
        flipped = ("00" if hx[-2:] != "00" else "ff") + hx[2:] if len(hx) >= 2 else "00" * 64
        bad_sig = dict(bad_sig)
        bad_sig["signature"] = "ed25519:" + flipped
    sig_posts = _post_prepare(bad_sig) if bad_sig else {}
    sig_v, sig_pass, sig_rej = _classify(sig_posts) if sig_posts else ("NOT_PROVEN", [], {})
    sig_reasons = {_reason(p) for p in sig_posts.values()}
    sig_ok = bool(sig_posts) and not sig_pass and sig_reasons <= {"invalid_prepare", "invalid_signature"}
    results["invalid_signature"] = _row(
        "PASS" if sig_ok else "FAIL" if sig_pass else "NOT_PROVEN",
        verdict=sig_v,
        identity_passed=sig_pass,
        reasons=sorted(sig_reasons),
        note="correct NodeID+key + bad sig → invalid_prepare, not identity GAP",
        posts={n: {k: sig_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in sig_posts},
    )

    producer_forged = dict(a1.get("row") or {})
    node2_ed = (((nodes["ovh-node-2"].get("identity") or {}).get("replicas") or {}).get("ovh-node-2") or {}).get("ed25519_b64")
    if producer_forged and node2_ed:
        producer_forged = dict(producer_forged)
        producer_forged["producer_ed25519_b64"] = node2_ed
    pf_posts = _post_prepare(producer_forged) if producer_forged else {}
    pf_v, pf_pass, pf_rej = _classify(pf_posts) if pf_posts else ("NOT_PROVEN", [], {})
    results["producer_star_forged"] = _row(
        "PASS" if pf_v == "BOUND" and not pf_pass else "GAP" if pf_pass else "NOT_PROVEN",
        verdict=pf_v,
        identity_passed=pf_pass,
        binding_rejected=pf_rej,
        note="producer_* is not authority; K2 pubkey on a Node1 message must not authenticate",
        posts={n: {k: pf_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in pf_posts},
    )

    replay = dict(a1.get("row") or {})
    if replay:
        replay = dict(replay)
        replay["replica_id"] = "ovh-node-2"
        replay["message"] = str(replay.get("message") or "").replace("ovh-node-1", "ovh-node-2")
    rp_posts = _post_prepare(replay) if replay else {}
    rp_v, rp_pass, rp_rej = _classify(rp_posts) if rp_posts else ("NOT_PROVEN", [], {})
    results["replay_old_sig_new_nodeid"] = _row(
        "PASS" if rp_v == "BOUND" and not rp_pass else "GAP" if rp_pass else "NOT_PROVEN",
        verdict=rp_v,
        identity_passed=rp_pass,
        binding_rejected=rp_rej,
        posts={n: {k: rp_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in rp_posts},
    )

    honest_vcs = []
    honest_meta = []
    for nid in SIGNERS:
        got = _forge(nid, nid, kind="view-change-265")
        honest_meta.append({"signer": nid, "ssh_rc": got.get("ssh_rc"), "has_row": bool(got.get("row"))})
        if got.get("row"):
            honest_vcs.append(got["row"])

    fake_prepared = [{"seq": 9, "digest": "aa" * 32}]
    incomplete_vcs = []
    for nid in SIGNERS:
        got = _forge(nid, nid, kind="view-change-265", prepared=fake_prepared)
        if got.get("row"):
            incomplete_vcs.append(got["row"])

    same_key = []
    for claimed in SIGNERS:
        got = _forge("ovh-node-1", claimed, kind="view-change-265", prepared=fake_prepared)
        if got.get("row"):
            same_key.append(got["row"])

    nv0 = _analyze_http([])
    nv1 = _analyze_http(honest_vcs[:1])
    nv2 = _analyze_http(honest_vcs[:2])
    nv3 = _analyze_http(honest_vcs[:3])
    nv_inc1 = _analyze_http(incomplete_vcs[:1])
    nv_inc3 = _analyze_http(incomplete_vcs[:3])
    nv_same = _analyze_http(same_key)
    sel1 = _select_http(honest_vcs[:1])
    sel3 = _select_http(honest_vcs[:3])

    results["new_view_0vc"] = _row(
        _nv_status(nv0.get("analysis") or {}, want_quorum=False),
        analyze=nv0,
        note="empty set cannot select",
    )
    results["new_view_1vc"] = _row(
        _nv_status(nv1.get("analysis") or {}, want_quorum=False),
        analyze=nv1,
        select=sel1,
        note="1 honest VC is not Q",
    )
    results["new_view_2vc"] = _row(
        _nv_status(nv2.get("analysis") or {}, want_quorum=False),
        analyze=nv2,
        note="2 honest VC is not Q",
    )
    results["new_view_3vc_honest_empty_prepared"] = _row(
        _nv_status(nv3.get("analysis") or {}, want_quorum=True, want_reason="no_prepared"),
        analyze=nv3,
        select=sel3,
        honest=honest_meta,
        note="Q=3 honest VCs are admissible; empty prepared → no_prepared, no bind",
    )
    results["new_view_1vc_state_incomplete"] = _row(
        _nv_status(nv_inc1.get("analysis") or {}, want_quorum=False, want_reason="state_incomplete"),
        analyze=nv_inc1,
        note="claimed prepared, not reconstructable → state_incomplete",
    )
    results["new_view_3vc_state_incomplete"] = _row(
        _nv_status(nv_inc3.get("analysis") or {}, want_quorum=True, want_reason="state_incomplete"),
        analyze=nv_inc3,
        note="Q=3 + claimed unreconstructable prepared stays fail-closed",
    )
    results["new_view_3vc_same_key_not_quorum"] = _row(
        _nv_status(nv_same.get("analysis") or {}, want_quorum=False),
        analyze=nv_same,
        note="3 VCs signed by K1 claiming 3 NodeIDs must not count as Q",
    )
    print(
        "NV",
        results["new_view_1vc"]["status"],
        results["new_view_2vc"]["status"],
        results["new_view_3vc_honest_empty_prepared"]["status"],
        results["new_view_3vc_state_incomplete"]["status"],
        results["new_view_3vc_same_key_not_quorum"]["status"],
        flush=True,
    )

    vc_forge = _forge("ovh-node-1", "ovh-node-2", kind="view-change-265")
    vc_posts = _post_vc(vc_forge["row"]) if vc_forge.get("row") else {}
    vc_ok = all(
        (p.get("ok") is False) and (_reason(p) in BINDING_REJECT or _reason(p) == "invalid_view_change_265")
        for p in vc_posts.values()
    ) if vc_posts else False
    results["combo_forged_identity_plus_view_change"] = _row(
        "PASS" if vc_ok else "FAIL" if vc_posts else "NOT_PROVEN",
        posts={n: {k: vc_posts[n].get(k) for k in ("ok", "http", "reason", "detail")} for n in vc_posts},
    )
    combo_nv = _analyze_http(same_key)
    results["combo_forged_identity_plus_new_view"] = _row(
        _nv_status(combo_nv.get("analysis") or {}, want_quorum=False),
        analyze=combo_nv,
        note="forged identities cannot form a NEW-VIEW quorum",
    )

    print("N04_50 isolated", flush=True)
    results["n04_50"] = _n04_50_isolated()
    print("N04", results["n04_50"].get("status"), flush=True)

    revoked_live = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        replicas = (nodes[nid].get("identity") or {}).get("replicas") or {}
        revoked_live[nid] = {
            rid: bool((row or {}).get("revoked")) for rid, row in replicas.items() if isinstance(row, dict)
        }
    overlay = _software_revocation_on_vm()
    overlay_ok = (overlay.get("result") or {}).get("ok") is False and (overlay.get("result") or {}).get("reason") == "replica_key_revoked"
    results["a4_a8_live"] = _row(
        "NOT_PROVEN",
        note="live service registry was not revoked/expired/downgraded. Overlay is process-local on OVH1, not the running API.",
        live_revoked_flags=revoked_live,
        software_overlay_on_vm=overlay,
        software_overlay_pass=overlay_ok,
        a7_live=results["a7_k2_as_node1"]["status"],
    )
    tpm = {nid: _probe_tpm(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    results["tpm_quote"] = _row(
        "NOT_PROVEN",
        note="registry public keys ≠ TPM quote. Device presence recorded only.",
        nodes=tpm,
        any_tpm0=any(v.get("has_tpm0") for v in tpm.values()),
    )
    results["c04_thousands"] = _row(
        "NOT_PROVEN",
        note="thousands of blocks not run this campaign; a short substitute is forbidden",
    )
    results["certified_100"] = False
    results["n04_row_not_recast_pass"] = True
    results["production_ready"] = False

    nv_live_pass = all(
        results[k]["status"] == "PASS"
        for k in (
            "new_view_1vc",
            "new_view_2vc",
            "new_view_3vc_honest_empty_prepared",
            "new_view_1vc_state_incomplete",
            "new_view_3vc_state_incomplete",
            "new_view_3vc_same_key_not_quorum",
        )
    )
    artefact = write_campaign(
        ROOT,
        campaign_id=f"277_{stamp}",
        code_sha=want_sha,
        runner="scripts/run_live277_issue77.py",
        environment={"origin_main": origin_main, "want_sha": want_sha, "shas": shas, "bindings": bindings},
        nodes={
            nid: {
                "health": nodes[nid]["health"],
                "pbft": nodes[nid]["pbft"],
                "network": nodes[nid]["network"],
                "attest": nodes[nid]["attest"],
                "identity": nodes[nid]["identity"],
            }
            for nid in OFFICIAL_COMPUTE_NODE_IDS
        },
        results=results,
    )
    payload = {
        "ok": bool(a3_ok and a7_ok and sha_ok and bind_ok),
        "certified_100": False,
        "production_ready": False,
        "stamp": stamp,
        "want_sha": want_sha,
        "shas": shas,
        "bindings": bindings,
        "results": results,
        "campaign": artefact,
        "new_view_live_pass": nv_live_pass,
    }
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    (out / f"277_issue77_{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out / "277_issue77_latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "ok": payload["ok"],
        "certified_100": False,
        "phase1": results["phase1_sha_x4"]["status"],
        "binding": results["phase1_binding_enforced_x4"]["status"],
        "a1": results["a1_k1_as_node1"]["status"],
        "a3": results["a3_k1_as_node2"]["status"],
        "a7": results["a7_k2_as_node1"]["status"],
        "unknown": results["unknown_key"]["status"],
        "invalid_sig": results["invalid_signature"]["status"],
        "producer_forged": results["producer_star_forged"]["status"],
        "replay_nodeid": results["replay_old_sig_new_nodeid"]["status"],
        "nv1": results["new_view_1vc"]["status"],
        "nv2": results["new_view_2vc"]["status"],
        "nv3": results["new_view_3vc_honest_empty_prepared"]["status"],
        "nv_inc": results["new_view_3vc_state_incomplete"]["status"],
        "nv_same": results["new_view_3vc_same_key_not_quorum"]["status"],
        "combo_vc": results["combo_forged_identity_plus_view_change"]["status"],
        "combo_nv": results["combo_forged_identity_plus_new_view"]["status"],
        "n04_50": results["n04_50"].get("status"),
        "a4_a8": "NOT_PROVEN",
        "tpm": "NOT_PROVEN",
        "c04": "NOT_PROVEN",
        "new_view_live_pass": nv_live_pass,
    }, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
