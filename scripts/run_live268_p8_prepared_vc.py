#!/usr/bin/env python3
"""R268 P8 live — prepared certificate survives view-change; Y is refused.

Prepare X (no commit) → VC 264+265 → select/bind proofs → propose Y 409
→ repropose X → cert ×4. Processes stay UP. Never wipe.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_live265_pbft_e2e as l265  # noqa: E402
from artcb.consensus.pbft_finality import verify_prepared_certificate, verify_preprepare  # noqa: E402
from artcb.consensus.pbft_view import primary_of  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
VC_KEYS = (
    "kind", "protocol", "view", "from_view", "height", "last_hash", "replica_id",
    "reason", "message", "signature", "producer_ed25519_b64", "producer_pqc_b64", "ts_ns",
)


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    try:
        import subprocess

        want_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        want_sha = ""
    payload: dict = {"stamp": stamp, "protocol": "268-p8-prepared-vc", "git_sha_agent": want_sha}
    before = l265.independent_snapshot()
    payload["before"] = {n: {k: (before[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary")} for n in OFFICIAL_COMPUTE_NODE_IDS}
    payload["sha_equal"] = l265._same_sha(before, want_sha)
    view = int((before.get("ovh-node-1") or {}).get("view") or 0)
    primary = primary_of(view)
    t0 = time.perf_counter_ns()
    proposed = l265._http("POST", f"{HTTP[primary]}/api/v1/consensus/pbft/propose", {"graph_id": f"268-p8-{stamp}", "graph_root": "p8", "source": "pbft:268"})
    pp = proposed.get("pre_prepare") if isinstance(proposed.get("pre_prepare"), dict) else None
    block = proposed.get("block") if isinstance(proposed.get("block"), dict) else None
    payload["propose"] = {"http": proposed.get("http"), "detail": proposed.get("detail") or proposed.get("error")}
    if proposed.get("http") != 200 or not pp or not block:
        payload["ok"] = False
        payload["reason"] = "propose_failed"
        _write(payload, stamp)
        return 2
    digest = str(pp.get("digest") or block.get("hash") or "")
    seq = int(block.get("index") or -1)
    payload["x"] = {"seq": seq, "digest": digest, "primary": primary, "view": view, "pp_ok": verify_preprepare(pp)}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid == primary:
            continue
        l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
    prepares = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        prepares[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for src, row in prepares.items():
            prep = row.get("prepare")
            if src == nid or not isinstance(prep, dict):
                continue
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
    prepared = {n: l265._http("GET", f"{HTTP[n]}/api/v1/consensus/pbft/prepared") for n in OFFICIAL_COMPUTE_NODE_IDS}
    proofs = {}
    for n, row in prepared.items():
        items = [i for i in (row.get("prepared") or []) if int(i.get("seq") or -1) == seq]
        proofs[n] = bool(items) and verify_prepared_certificate(items[0])
    payload["prepared_proofs"] = proofs
    new_v = view + 1
    new_p = primary_of(new_v)
    vcs265 = []
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        r = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change-265", {"view": new_v})
        vc = r.get("view_change") if isinstance(r.get("view_change"), dict) else None
        payload.setdefault("vc265_http", {})[nid] = {"http": r.get("http"), "ok": r.get("ok"), "detail": r.get("detail")}
        if vc:
            vcs265.append(vc)
    vcs264 = []
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        r = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change", {"view": new_v, "reason": "p8_prepared_preserve"})
        if r.get("http") == 200:
            vcs264.append({k: r.get(k) for k in VC_KEYS if r.get(k) is not None})
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        for vc in vcs264:
            if vc.get("replica_id") == nid:
                continue
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/view-change/receive", {"view_change": vc})
    nv = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264})
    nv_obj = nv.get("new_view")
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        if nid == new_p or not nv_obj:
            continue
        l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/new-view", {"view": new_v, "view_changes": vcs264, "new_view": nv_obj})
    selected = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/select-prepared", {"view_changes": vcs265})
    chosen = selected.get("chosen") if isinstance(selected.get("chosen"), dict) else None
    payload["select"] = {
        "http": selected.get("http"),
        "ok": selected.get("ok"),
        "proof": selected.get("proof"),
        "seq": (chosen or {}).get("seq"),
        "digest": (chosen or {}).get("digest"),
        "kept_x": bool(chosen) and str(chosen.get("digest")) == digest,
    }
    binds = {}
    if chosen:
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            binds[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/bind-prepared", {"chosen": chosen})
    payload["binds"] = {n: {"http": r.get("http"), "ok": r.get("ok")} for n, r in binds.items()}
    evil = l265._http(
        "POST",
        f"{HTTP[new_p]}/api/v1/consensus/pbft/propose",
        {"graph_id": f"268-p8-evil-{stamp}", "graph_root": "Y", "source": "pbft:268-evil"},
    )
    payload["propose_y"] = {
        "http": evil.get("http"),
        "detail": str(evil.get("detail") or evil.get("error") or "")[:300],
        "refused": evil.get("http") == 409 and "must_repropose_prepared" in str(evil.get("detail") or ""),
    }
    repro = l265._http("POST", f"{HTTP[new_p]}/api/v1/consensus/pbft/client-request", {"block": block})
    payload["repropose_x"] = {"http": repro.get("http"), "ok": repro.get("ok"), "detail": repro.get("detail")}
    pp2 = repro.get("pre_prepare") if isinstance(repro.get("pre_prepare"), dict) else None
    if pp2:
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            if nid == new_p:
                continue
            l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp2})
        view2 = new_v
        prepares2 = {}
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            prepares2[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"view": view2, "seq": seq, "digest": digest})
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            for src, row in prepares2.items():
                prep = row.get("prepare")
                if src == nid or not isinstance(prep, dict):
                    continue
                l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": prep})
        cert = None
        commits = {}
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            commits[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/commit", {"view": view2, "seq": seq, "digest": digest})
            if isinstance(commits[nid].get("certificate"), dict):
                cert = commits[nid]["certificate"]
        for nid in OFFICIAL_COMPUTE_NODE_IDS:
            cmsg = commits[nid].get("commit") if isinstance(commits[nid], dict) else None
            if not isinstance(cmsg, dict):
                continue
            for dst in OFFICIAL_COMPUTE_NODE_IDS:
                if dst == nid:
                    continue
                got = l265._http("POST", f"{HTTP[dst]}/api/v1/consensus/pbft/commit", {"commit": cmsg})
                if isinstance(got.get("certificate"), dict):
                    cert = got["certificate"]
        writes = {}
        if cert:
            for nid in OFFICIAL_COMPUTE_NODE_IDS:
                writes[nid] = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/certificate", {"certificate": cert, "block": block})
        payload["finalize"] = {"cert": bool(cert), "writes": {n: w.get("wrote") for n, w in writes.items()}}
    after = l265.independent_snapshot()
    payload["after"] = {n: {k: (after[n] or {}).get(k) for k in ("git_sha", "height", "last_hash", "view", "primary")} for n in OFFICIAL_COMPUTE_NODE_IDS}
    tips = {(after[n] or {}).get("last_hash") for n in OFFICIAL_COMPUTE_NODE_IDS}
    payload["ok"] = bool(
        payload["sha_equal"]
        and all(proofs.values())
        and payload["select"].get("kept_x")
        and payload["propose_y"].get("refused")
        and payload.get("finalize", {}).get("cert")
        and len(tips) == 1
        and str(next(iter(tips))) == digest
    )
    payload["dur_ns"] = time.perf_counter_ns() - t0
    _write(payload, stamp)
    print(json.dumps({"ok": payload["ok"], "sha_equal": payload["sha_equal"], "kept_x": payload["select"].get("kept_x"), "y_refused": payload["propose_y"].get("refused"), "seq": seq, "digest": digest[:16]}, indent=2))
    return 0 if payload["ok"] else 4


def _write(payload: dict, stamp: str) -> None:
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    dest = out / f"268_p8_{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "268_p8_latest.json").write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
