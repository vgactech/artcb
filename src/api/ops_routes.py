"""R336 — HTTPS operator ops (no SSH :22).

Ports measured from LAN 2026-09-13: only :80/:443 OPEN on seeds.
:22/:8000/:8443/:2222 CLOSED. Admin actions that need process restart
must therefore travel on the existing HTTPS surface, not a fantasy free port.

~~Do not add a raw shell/exec endpoint.~~ Restart = exit so systemd
``Restart=always`` re-runs ``doppler run`` and refreshes secrets.

Two auth paths:
1. Local ``require_write_actor`` (node's own env key) — ``/self-restart``
2. Official replica signature (like concept peer-ingest) — ``/peer-restart``
   so ovh-node-1 can bounce n2/n3/n4 over :443 without their API keys.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from src.api.api_keys_routes import require_write_actor
from src.artcb.trace.ns import now_mono_ns, now_wall_ns

router = APIRouter(prefix="/api/v1/ops", tags=["ops"])

PEER_RESTART_PROTOCOL = "ops-peer-restart-v1"
_MAX_SKEW_NS = 120_000_000_000  # 120s
_LAST_RESTART_MONO = 0.0
_MIN_RESTART_GAP_S = 30.0


def _key_fingerprint() -> dict[str, Any]:
    raw = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(raw) < 16:
        return {"present": False, "sha256_16": None, "len": len(raw)}
    return {
        "present": True,
        "sha256_16": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
        "len": len(raw),
    }


def peer_restart_message(*, from_replica_id: str, ts_ns: int, target_hint: str) -> str:
    return f"{PEER_RESTART_PROTOCOL}|{from_replica_id}|{ts_ns}|{target_hint}"


def _schedule_exit(delay_s: float = 1.5) -> None:
    def _exit_later() -> None:
        time.sleep(delay_s)
        os._exit(42)

    threading.Thread(target=_exit_later, name="artcb-ops-self-restart", daemon=True).start()


def _rate_limit_or_429() -> None:
    global _LAST_RESTART_MONO
    now = time.monotonic()
    if now - _LAST_RESTART_MONO < _MIN_RESTART_GAP_S:
        raise HTTPException(status_code=429, detail="ops_restart_rate_limited")
    _LAST_RESTART_MONO = now


@router.get("/key-fingerprint", summary="Empreinte sha256_16 de ARTCB_API_KEY env (jamais la valeur)")
def key_fingerprint(
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    if actor is None:
        raise HTTPException(status_code=401, detail="ops_requires_bearer")
    return {
        "node_id": os.environ.get("ARTCB_NODE_ID") or None,
        "doppler_project": os.environ.get("DOPPLER_PROJECT") or None,
        "doppler_config": os.environ.get("DOPPLER_CONFIG") or None,
        "key": _key_fingerprint(),
        "ts_ns": now_wall_ns(),
        "note": "compare sha256_16 to local ~/.artcb/nodes/*.env without shipping secrets",
    }


@router.post(
    "/self-restart",
    summary="Quitte le process (Bearer local) pour systemd + doppler run",
)
async def self_restart(
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    t0 = now_mono_ns()
    if actor is None:
        raise HTTPException(status_code=401, detail="ops_requires_bearer")
    source = str(actor.get("source") or "")
    if source not in {"operator", "env", "api_key"}:
        scopes = actor.get("scopes") or []
        if "admin" not in scopes and "write" not in scopes:
            raise HTTPException(status_code=403, detail="ops_restart_forbidden")
    _rate_limit_or_429()
    delay_s = 1.5
    _schedule_exit(delay_s)
    return {
        "accepted": True,
        "action": "self_restart",
        "delay_s": delay_s,
        "node_id": os.environ.get("ARTCB_NODE_ID") or None,
        "key_before": _key_fingerprint(),
        "doppler_project": os.environ.get("DOPPLER_PROJECT") or None,
        "doppler_config": os.environ.get("DOPPLER_CONFIG") or None,
        "auth": source or actor.get("kind"),
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "note": "systemd Restart=always expected; CERTIFIED_100 unchanged",
    }


@router.post(
    "/peer-restart",
    summary="Redémarrage demandé par une replica officielle (signature, pas API key étrangère)",
)
async def peer_restart(
    request: Request,
    x_artcb_replica_id: Annotated[str | None, Header()] = None,
    x_artcb_replica_sig: Annotated[str | None, Header()] = None,
    x_artcb_producer_ed25519: Annotated[str | None, Header()] = None,
    x_artcb_ops_ts_ns: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """R336 — same trust model as ``/concepts/peer-ingest``."""
    t0 = now_mono_ns()
    replica_id = (x_artcb_replica_id or "").strip()
    signature = (x_artcb_replica_sig or "").strip()
    ed_b64 = (x_artcb_producer_ed25519 or "").strip()
    try:
        ts_ns = int((x_artcb_ops_ts_ns or "0").strip())
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="ops_peer_ts_invalid") from exc

    if not replica_id or not signature or not ed_b64:
        raise HTTPException(status_code=401, detail="ops_peer_restart_requires_replica_signature")
    now = now_wall_ns()
    if ts_ns <= 0 or abs(now - ts_ns) > _MAX_SKEW_NS:
        raise HTTPException(status_code=401, detail="ops_peer_ts_stale_or_missing")

    host = (request.headers.get("host") or "").split(":")[0].lower()
    message = peer_restart_message(from_replica_id=replica_id, ts_ns=ts_ns, target_hint=host)

    from src.artcb.consensus.replica_identity import (
        expected_binding,
        official_pbft_replica_ids,
        verify_bound_signature,
    )

    if replica_id not in set(official_pbft_replica_ids()):
        raise HTTPException(status_code=403, detail="ops_peer_replica_not_official")
    expected = expected_binding(replica_id)
    if expected is None or expected.revoked:
        raise HTTPException(status_code=403, detail="ops_peer_replica_unregistered")
    ed_use = (expected.ed25519_b64 or ed_b64 or "").strip()
    ok, reason = verify_bound_signature(
        replica_id=replica_id,
        message=message,
        signature=signature,
        producer_ed25519_b64=ed_use,
        producer_pqc_b64="",
    )
    if not ok:
        raise HTTPException(status_code=403, detail=f"ops_peer_rejected:{reason}")

    _rate_limit_or_429()
    delay_s = 1.5
    _schedule_exit(delay_s)
    return {
        "accepted": True,
        "action": "peer_restart",
        "delay_s": delay_s,
        "from_replica_id": replica_id,
        "target_host": host,
        "protocol": PEER_RESTART_PROTOCOL,
        "key_before": _key_fingerprint(),
        "doppler_project": os.environ.get("DOPPLER_PROJECT") or None,
        "doppler_config": os.environ.get("DOPPLER_CONFIG") or None,
        "node_id": os.environ.get("ARTCB_NODE_ID") or None,
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "note": "replica-signed restart over :443; not SSH; CERTIFIED_100 unchanged",
    }


@router.post(
    "/fanout-restart",
    summary="Depuis ce nœud, demande peer-restart signé vers les seeds (Bearer local)",
)
async def fanout_restart(
    request: Request,
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict[str, Any]:
    """Publisher (usually ovh1) bounces peers over HTTPS with replica sig."""
    import urllib.error
    import urllib.request

    t0 = now_mono_ns()
    if actor is None:
        raise HTTPException(status_code=401, detail="ops_requires_bearer")

    from src.artcb.consensus.replica_identity import official_consensus_node_id
    from src.artcb.consensus.tip_attest import producer_key_b64, sign_message
    from src.api.concept_routes import DEFAULT_SEED_PEERS

    state = request.app.state.artcb
    chain = state.chain
    replica_id = official_consensus_node_id()
    if not replica_id:
        raise HTTPException(status_code=503, detail="local_replica_id_unknown")

    ts_ns = now_wall_ns()
    ed_b64, _pqc = producer_key_b64(chain)
    host = (request.headers.get("host") or "").split(":")[0].lower()
    peers_env = (os.getenv("ARTCB_OPS_RESTART_PEERS") or "").strip()
    peers = [p.strip() for p in peers_env.split(",") if p.strip()] or list(DEFAULT_SEED_PEERS)

    peer_rows: dict[str, Any] = {}
    ok_peers = 0
    for peer in peers:
        peer_host = peer.split("//", 1)[-1].split("/")[0].lower()
        if host and host == peer_host:
            peer_rows[peer] = {"skipped": "self"}
            continue
        message = peer_restart_message(from_replica_id=replica_id, ts_ns=ts_ns, target_hint=peer_host)
        signature = sign_message(chain, message)
        url = f"{peer.rstrip('/')}/api/v1/ops/peer-restart"
        req = urllib.request.Request(
            url,
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-ARTCB-Replica-Id": replica_id,
                "X-ARTCB-Replica-Sig": signature,
                "X-ARTCB-Producer-Ed25519": ed_b64,
                "X-ARTCB-Ops-Ts-Ns": str(ts_ns),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode()
                peer_rows[peer] = {"http": int(resp.status), "ok": True, "body_preview": body[:240]}
                ok_peers += 1
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            peer_rows[peer] = {"http": int(exc.code), "ok": False, "body": err_body}
        except Exception as exc:  # noqa: BLE001
            peer_rows[peer] = {"http": 0, "ok": False, "error": type(exc).__name__, "detail": str(exc)[:160]}

    return {
        "from_replica_id": replica_id,
        "protocol": PEER_RESTART_PROTOCOL,
        "peers": peer_rows,
        "peers_ok": ok_peers,
        "fanout_restart_pass": ok_peers >= 3,
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "published_by": actor.get("kind") or actor.get("source"),
        "note": "HTTPS :443 peer restart; keys reload only if doppler run injects ARTCB_API_KEY",
    }
