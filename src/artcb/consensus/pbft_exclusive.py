"""Exclusive PBFT coordination for official public chain writes.

On the four live VMs, a public append constructs the block then runs
PRE-PREPARE → PREPARE → COMMIT → certificate → write_certified_block.
Pytest and agent hosts do not HTTP-fanout to production IPs.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.artcb.consensus.pbft_finality import verify_certificate, verify_preprepare
from src.artcb.consensus.pbft_view import primary_of
from src.artcb.node_registry import (
    OFFICIAL_COMPUTE_IPV4,
    OFFICIAL_COMPUTE_NODE_IDS,
    on_official_compute,
    pbft_reachable_http_map,
)
from src.artcb.trace.ns import emit_pbft, now_mono_ns

HTTP_TIMEOUT = 15.0


def official_http_map() -> dict[str, str]:
    """Seed IPv4 HTTP map (follow-main / book fan-out). Not PBFT membership.

    ~~2026-09-10T11:20:00Z zip(OFFICIAL_COMPUTE_NODE_IDS) was used as if N=4 replicas.~~
    Keep seeds here. Live membership is official_pbft_replica_ids(). Reachable
    Mac tunnel (if any) is pbft_reachable_http_map().
    """
    return {nid: f"http://{ip}:8000" for nid, ip in zip(OFFICIAL_COMPUTE_NODE_IDS, OFFICIAL_COMPUTE_IPV4)}


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = HTTP_TIMEOUT) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            return resp.status, parsed if isinstance(parsed, dict) else {"raw": parsed}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return exc.code, parsed if isinstance(parsed, dict) else {"detail": detail}
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__}


def coordinate_public_finality(engine: Any, chain: Any, block: dict[str, Any]) -> dict[str, Any]:
    """Fan-out PBFT for a constructed public block. Writes locally on certificate.

    R364-BUG1 FIX: when the current primary is unreachable, automatically
    trigger VIEW-CHANGE to the next reachable primary instead of fail-closing.
    This allows OVH2/AWS3/OVH4 to continue consensus without OVH1 (or any
    single dead node) blocking production indefinitely.
    """
    t0 = now_mono_ns()
    data_dir = getattr(engine.pbft_log, "data_dir", None)
    if not on_official_compute():
        if data_dir is not None:
            emit_pbft(data_dir, phase="exclusive", replica_id=engine.node_id, ok=False, dur_ns=now_mono_ns() - t0, reason="not_on_official_compute")
        return {"ok": False, "wrote": False, "reason": "not_on_official_compute"}
    view = int(getattr(engine.pbft, "view", 0) or 0)
    primary = primary_of(view)
    # R364-BUG1: probe-aware reachable map (excludes dead nodes like ovh-node-1)
    hosts = pbft_reachable_http_map()
    if primary not in hosts and engine.node_id != primary:
        # R364-BUG1 FIX — auto VIEW-CHANGE instead of fail-closed
        from src.artcb.consensus.pbft_view import next_reachable_view
        plan = next_reachable_view(view)
        if plan.get("ok"):
            target_view = int(plan["target_view"])
            try:
                split = chain.tip_public_private() if hasattr(chain, "tip_public_private") else {}
                height = int(split.get("public_last_index") or -1) + 1
                last_hash = str(split.get("public_last_hash") or "")
                engine.pbft_log.emit_view_change(
                    chain,
                    view=target_view,
                    height=height,
                    last_hash=last_hash,
                    reason=f"primary_unreachable_auto_vc:view={view}:primary={primary}",
                )
                # Fan-out VIEW-CHANGE to all reachable replicas
                vc_rows = engine.pbft_log.view_changes(target_view) if hasattr(engine.pbft_log, "view_changes") else []
                for nid, url in hosts.items():
                    if nid == engine.node_id:
                        continue
                    _http_json("POST", f"{url}/api/v1/consensus/pbft/view-change",
                               {"view": target_view, "reason": "primary_unreachable_auto_vc"})
                vc_result = {"auto_view_change": True, "target_view": target_view, "new_primary": plan.get("primary")}
            except Exception as exc:
                vc_result = {"auto_view_change": False, "error": str(exc)[:120]}
        else:
            vc_result = {"auto_view_change": False, "reason": "no_reachable_primary"}
        if data_dir is not None:
            emit_pbft(
                data_dir,
                phase="exclusive",
                replica_id=engine.node_id,
                ok=False,
                dur_ns=now_mono_ns() - t0,
                reason="primary_unreachable_transport_auto_vc",
            )
        return {
            "ok": False,
            "wrote": False,
            "reason": "primary_unreachable_transport",
            "primary": primary,
            "reachable": sorted(hosts),
            **vc_result,
        }
    log = engine.pbft_log
    if engine.node_id == primary:
        try:
            pp = log.emit_preprepare(chain, block=block)
        except ValueError as exc:
            return {"ok": False, "wrote": False, "reason": str(exc)}
    else:
        code, body = _http_json("POST", f"{hosts[primary]}/api/v1/consensus/pbft/client-request", {"block": block})
        pp = body.get("pre_prepare") if isinstance(body, dict) else None
        if code != 200 or not isinstance(pp, dict):
            detail = body.get("detail") if isinstance(body, dict) else body
            return {
                "ok": False,
                "wrote": False,
                "reason": f"client_request_failed:{code}:{detail}",
                "http": code,
                "detail": body,
            }
        block = body.get("block") if isinstance(body.get("block"), dict) else block
        accepted = log.accept_preprepare(pp)
        if not accepted.get("ok"):
            return {"ok": False, "wrote": False, "reason": accepted.get("reason") or "preprepare_rejected"}
    if not verify_preprepare(pp):
        return {"ok": False, "wrote": False, "reason": "preprepare_not_verifiable"}
    digest = str(pp.get("digest") or block.get("hash") or "")
    seq = int(block.get("index") if block.get("index") is not None else pp.get("seq") or -1)
    for nid, url in hosts.items():
        if nid == engine.node_id:
            continue
        _http_json("POST", f"{url}/api/v1/consensus/pbft/pre-prepare", {"pre_prepare": pp})
    try:
        local_prep = log.emit_prepare(chain, view=view, seq=seq, digest=digest)
    except ValueError as exc:
        return {"ok": False, "wrote": False, "reason": f"prepare:{exc}"}
    prepares: dict[str, dict[str, Any]] = {engine.node_id: local_prep}
    for nid, url in hosts.items():
        if nid == engine.node_id:
            continue
        _code, body = _http_json("POST", f"{url}/api/v1/consensus/pbft/prepare", {"view": view, "seq": seq, "digest": digest})
        if isinstance(body.get("prepare"), dict):
            prepares[nid] = body["prepare"]
    for src, prep in prepares.items():
        if src != engine.node_id:
            log.accept_prepare(prep)
        for nid, url in hosts.items():
            if nid in {src, engine.node_id}:
                continue
            _http_json("POST", f"{url}/api/v1/consensus/pbft/prepare", {"prepare": prep})
    try:
        emitted = log.emit_commit(chain, view=view, seq=seq, digest=digest)
    except ValueError as exc:
        return {"ok": False, "wrote": False, "reason": f"commit:{exc}"}
    cert = emitted.get("certificate") if isinstance(emitted, dict) else None
    local_commit = emitted.get("commit") if isinstance(emitted, dict) else None
    commits: dict[str, dict[str, Any]] = {}
    if isinstance(local_commit, dict):
        commits[engine.node_id] = local_commit
    for nid, url in hosts.items():
        if nid == engine.node_id:
            continue
        _code, body = _http_json("POST", f"{url}/api/v1/consensus/pbft/commit", {"view": view, "seq": seq, "digest": digest})
        if isinstance(body.get("commit"), dict):
            commits[nid] = body["commit"]
        if isinstance(body.get("certificate"), dict):
            cert = body["certificate"]
    for src, cmsg in commits.items():
        if src != engine.node_id:
            got = log.accept_commit(cmsg)
            if isinstance(got.get("certificate"), dict):
                cert = got["certificate"]
        for nid, url in hosts.items():
            if nid in {src, engine.node_id}:
                continue
            _code, body = _http_json("POST", f"{url}/api/v1/consensus/pbft/commit", {"commit": cmsg})
            if isinstance(body.get("certificate"), dict):
                cert = body["certificate"]
    if not isinstance(cert, dict) or not verify_certificate(cert):
        if data_dir is not None:
            emit_pbft(data_dir, phase="exclusive", replica_id=engine.node_id, ok=False, dur_ns=now_mono_ns() - t0, reason="no_certificate")
        return {"ok": False, "wrote": False, "reason": "no_certificate"}
    installed = log.install_certificate(cert)
    if not installed.get("ok"):
        return {"ok": False, "wrote": False, "reason": installed.get("reason") or "install_failed"}
    wrote = bool(chain.write_certified_block(block, cert, from_node_id="pbft-exclusive"))
    for nid, url in hosts.items():
        if nid == engine.node_id:
            continue
        _http_json("POST", f"{url}/api/v1/consensus/pbft/certificate", {"certificate": cert, "block": block})
    if data_dir is not None:
        emit_pbft(
            data_dir,
            phase="exclusive",
            replica_id=engine.node_id,
            ok=wrote,
            dur_ns=now_mono_ns() - t0,
            seq=seq,
            digest=digest[:16],
        )
    return {
        "ok": wrote,
        "wrote": wrote,
        "certificate": cert,
        "block": {**block, "pbft_cert": cert},
        "seq": seq,
        "digest": digest,
        "view": view,
        "primary": primary,
        "dur_ns": now_mono_ns() - t0,
    }
