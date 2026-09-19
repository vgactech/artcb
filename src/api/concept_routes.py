"""Concept sync réseau — R320 (2026-09-11T21:30:00Z).

Pourquoi ce fichier existe
--------------------------
R319 a mesuré C2-D = PARTIAL. Raison honnête : un agent B « froid » recevait un
ConceptPacket (uniquement des ConceptID) et ne pouvait rien en faire, parce que
la **définition binaire** du concept (le blob ``.arcb``) n'existait que sur le
disque de l'agent A. Le script de R319 contournait le trou avec une copie de
répertoire locale — ce n'était pas une preuve réseau.

Ces routes ferment le trou :

  POST /api/v1/concepts/publish   — A publie un bundle binaire ``ACBN`` (write Bearer)
  GET  /api/v1/concepts/resolve   — B récupère les blobs des ConceptID manquants
  GET  /api/v1/concepts/{cid}     — métadonnées d'un concept (vue humaine)
  GET  /api/v1/concepts/stats     — état du store de concepts du nœud

Le corps transporté est **binaire** (``application/octet-stream``). Aucun texte
humain n'est requis pour que B comprenne : c'est exactement l'exigence du
rapport 238 §28-§29.

Écriture protégée (write Bearer) : publier un concept modifie l'état sémantique
partagé du nœud. Lecture publique : un ConceptID est un identifiant public, et
C2-D exige qu'un agent tiers puisse résoudre sans clé.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import contextlib
import logging
import urllib.error
import urllib.request
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from src.api.api_keys_routes import require_write_actor
from src.artcb.memory.concept_store import ConceptStore
from src.artcb.memory.concept_sync import (
    ConceptBundleError,
    bundle_sha256,
    encode_concept_bundle,
    export_bundle,
    import_bundle,
)
from src.artcb.trace.ns import emit, now_mono_ns, now_wall_ns

logger = logging.getLogger("artcb.api.concepts")
router = APIRouter(prefix="/api/v1/concepts", tags=["concepts"])

MAX_BUNDLE_BYTES = 8 * 1024 * 1024  # 8 MiB — un bundle de concepts reste petit
# R334-C 2026-09-13T00:25:00Z — peer fan-out uses replica identity, not a shared API key.
PEER_INGEST_PROTOCOL = "concept-peer-ingest-v1"
PEER_INGEST_MAX_AGE_NS = 600 * 1_000_000_000
DEFAULT_SEED_PEERS = (
    "https://artcb.me",
    "https://n2.artcb.me",
    "https://n3.artcb.me",
    "https://n4.artcb.me",
)


def peer_ingest_message(*, sha: str, from_replica_id: str, ts_ns: int) -> str:
    return f"{PEER_INGEST_PROTOCOL}|{sha}|{from_replica_id}|{int(ts_ns)}"


def _state(request: Request):
    return request.app.state.artcb


def _store(request: Request) -> ConceptStore:
    """ConceptStore partagé du nœud (créé à la première demande)."""
    state = _state(request)
    store = getattr(state, "concept_store", None)
    if store is None:
        store = ConceptStore(state.settings.data_dir)
        state.concept_store = store  # type: ignore[attr-defined]
    return store


def _trace(request: Request, *, kind: str, t0: int, **fields: Any) -> None:
    """Traçabilité nanoseconde obligatoire (règle 10 artcb-live-node)."""
    try:
        emit(
            _state(request).settings.data_dir,
            {
                "kind": kind,
                "ts_ns": now_wall_ns(),
                "dur_ns": now_mono_ns() - t0,
                **fields,
            },
        )
    except Exception:  # noqa: BLE001 — la trace ne casse jamais la requête
        logger.debug("trace ns non écrite pour %s", kind)


@router.post("/publish", summary="Publier un bundle binaire de concepts (.arcb) sur ce nœud")
async def publish_concepts(
    request: Request,
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict:
    """Ingère un bundle ``ACBN`` dans le ConceptStore du nœud.

    Corps : ``application/octet-stream`` — le bundle binaire produit par
    ``AgentChannel.export_bundle``. Réponse JSON (canal humain) avec le sha256
    du bundle, qui sert d'ancre vérifiable.
    """
    t0 = now_mono_ns()
    if actor is None:
        raise HTTPException(status_code=401, detail="concept_publish_requires_bearer")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty_bundle")
    if len(data) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="bundle_too_large")
    try:
        report = import_bundle(
            _store(request),
            data,
            agent_id=str(actor.get("label") or actor.get("agent_id") or "network"),
        )
    except ConceptBundleError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_bundle:{exc}") from exc
    report["published_by"] = actor.get("kind")
    report["ts_ns"] = now_wall_ns()
    report["dur_ns"] = now_mono_ns() - t0
    _trace(
        request,
        kind="concept_publish",
        t0=t0,
        graphs=report["graphs"],
        concepts=len(report["concept_ids"]),
        bundle_sha256=report["bundle_sha256"],
    )
    logger.info(
        "Concepts publiés : %d graphes, %d concepts, sha=%s…",
        report["graphs"], len(report["concept_ids"]), report["bundle_sha256"][:12],
    )
    return report


@router.post(
    "/peer-ingest",
    summary="Ingérer un bundle signé par une replica officielle (fan-out write)",
)
async def peer_ingest_concepts(
    request: Request,
    x_artcb_replica_id: Annotated[str | None, Header()] = None,
    x_artcb_replica_sig: Annotated[str | None, Header()] = None,
    x_artcb_producer_ed25519: Annotated[str | None, Header()] = None,
    x_artcb_concept_ts_ns: Annotated[str | None, Header()] = None,
) -> dict:
    """R334-C — write path between seeds without sharing per-node API keys.

    Auth = official replica key binding + signature over
    ``concept-peer-ingest-v1|{sha256}|{from}|{ts_ns}``. Knowing a ConceptID
    alone never authorizes ingest. API Bearer is intentionally not enough.
    """
    t0 = now_mono_ns()
    replica_id = (x_artcb_replica_id or "").strip()
    signature = (x_artcb_replica_sig or "").strip()
    ed = (x_artcb_producer_ed25519 or "").strip()
    try:
        ts_ns = int((x_artcb_concept_ts_ns or "0").strip() or "0")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_ts_ns") from exc
    if not replica_id or not signature:
        raise HTTPException(status_code=401, detail="peer_ingest_requires_replica_signature")
    now = now_wall_ns()
    if ts_ns <= 0 or abs(now - ts_ns) > PEER_INGEST_MAX_AGE_NS:
        raise HTTPException(status_code=401, detail="peer_ingest_ts_stale_or_missing")

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty_bundle")
    if len(data) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="bundle_too_large")
    sha = bundle_sha256(data)
    message = peer_ingest_message(sha=sha, from_replica_id=replica_id, ts_ns=ts_ns)

    from src.artcb.consensus.replica_identity import (
        expected_binding,
        official_pbft_replica_ids,
        verify_bound_signature,
    )

    if replica_id not in set(official_pbft_replica_ids()):
        raise HTTPException(status_code=403, detail="peer_ingest_replica_not_official")
    expected = expected_binding(replica_id)
    if expected is None or expected.revoked:
        raise HTTPException(status_code=403, detail="peer_ingest_replica_unregistered")
    # Prefer registry key; header ed is only a hint / forensic field.
    ed_use = (expected.ed25519_b64 or ed or "").strip()
    ok, reason = verify_bound_signature(
        replica_id=replica_id,
        message=message,
        signature=signature,
        producer_ed25519_b64=ed_use,
        producer_pqc_b64="",
    )
    if not ok:
        raise HTTPException(status_code=403, detail=f"peer_ingest_rejected:{reason}")

    try:
        report = import_bundle(_store(request), data, agent_id=f"peer:{replica_id}")
    except ConceptBundleError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_bundle:{exc}") from exc
    report["published_by"] = "official_replica"
    report["from_replica_id"] = replica_id
    report["protocol"] = PEER_INGEST_PROTOCOL
    report["ts_ns"] = now_wall_ns()
    report["dur_ns"] = now_mono_ns() - t0
    _trace(
        request,
        kind="concept_peer_ingest",
        t0=t0,
        from_replica_id=replica_id,
        graphs=report["graphs"],
        concepts=len(report["concept_ids"]),
        bundle_sha256=report["bundle_sha256"],
    )
    return report


@router.post(
    "/fanout",
    summary="Publier localement puis pousser le bundle signé vers les seeds pairs",
)
async def fanout_concepts(
    request: Request,
    actor: Annotated[dict | None, Depends(require_write_actor)] = None,
) -> dict:
    """R334-C — operator/agent write on this node → replica-signed peer-ingest × seeds.

    Does not replace per-node ACL for ORG/GROUP private bodies. Public ConceptStore only.
    """
    t0 = now_mono_ns()
    if actor is None:
        raise HTTPException(status_code=401, detail="concept_fanout_requires_bearer")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty_bundle")
    if len(data) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="bundle_too_large")

    local = import_bundle(
        _store(request),
        data,
        agent_id=str(actor.get("label") or actor.get("agent_id") or "fanout"),
    )
    state = _state(request)
    chain = state.chain
    from src.artcb.consensus.replica_identity import official_consensus_node_id
    from src.artcb.consensus.tip_attest import producer_key_b64, sign_message

    replica_id = official_consensus_node_id()
    if not replica_id:
        raise HTTPException(status_code=503, detail="local_replica_id_unknown")
    ts_ns = now_wall_ns()
    sha = local["bundle_sha256"]
    message = peer_ingest_message(sha=sha, from_replica_id=replica_id, ts_ns=ts_ns)
    signature = sign_message(chain, message)
    ed_b64, _pqc = producer_key_b64(chain)

    import os

    host = (request.headers.get("host") or "").split(":")[0].lower()
    peers_env = (os.getenv("ARTCB_CONCEPT_FANOUT_PEERS") or "").strip()
    peers = [p.strip() for p in peers_env.split(",") if p.strip()] or list(DEFAULT_SEED_PEERS)
    peer_rows: dict[str, Any] = {}
    ok_peers = 0
    for peer in peers:
        peer_host = peer.split("//", 1)[-1].split("/")[0].lower()
        if host and host == peer_host:
            peer_rows[peer] = {"skipped": "self"}
            continue
        url = f"{peer.rstrip('/')}/api/v1/concepts/peer-ingest"
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
                "X-ARTCB-Replica-Id": replica_id,
                "X-ARTCB-Replica-Sig": signature,
                "X-ARTCB-Producer-Ed25519": ed_b64,
                "X-ARTCB-Concept-Ts-Ns": str(ts_ns),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode()
                peer_rows[peer] = {"http": int(resp.status), "ok": True, "body_preview": body[:200]}
                ok_peers += 1
        except urllib.error.HTTPError as exc:
            err_body = ""
            with contextlib.suppress(Exception):
                err_body = exc.read().decode()[:300]
            peer_rows[peer] = {"http": int(exc.code), "ok": False, "body": err_body}
        except Exception as exc:  # noqa: BLE001
            peer_rows[peer] = {"http": 0, "ok": False, "error": type(exc).__name__, "detail": str(exc)[:160]}

    out = {
        "local": local,
        "from_replica_id": replica_id,
        "protocol": PEER_INGEST_PROTOCOL,
        "peers": peer_rows,
        "peers_ok": ok_peers,
        "fanout_pass": ok_peers >= 3,
        "ts_ns": now_wall_ns(),
        "dur_ns": now_mono_ns() - t0,
        "published_by": actor.get("kind"),
        "note": "replica-signed peer ingest; not ORG body ACL; CERTIFIED_100 unchanged",
    }
    _trace(request, kind="concept_fanout", t0=t0, peers_ok=ok_peers, bundle_sha256=sha)
    return out


@router.get("/resolve", summary="Récupérer les blobs .arcb d'une liste de ConceptID")
def resolve_concepts(
    request: Request,
    ids: str = Query(..., description="ConceptID séparés par des virgules"),
) -> Response:
    """Réponse **binaire** ``ACBN`` — c'est le chemin IA↔IA de C2-D.

    Un ConceptID inconnu de ce nœud est simplement absent du bundle ; l'agent
    appelant voit alors un ``missing`` honnête plutôt qu'une réponse inventée.

    R322 (2026-09-11T21:50:00Z) — fédération one-hop optionnelle :
    si le store local rate et ``ARTCB_CONCEPT_FEDERATE=1`` (défaut), le nœud
    interroge les seeds HTTPS publics **une seule fois** (header hop) puis
    ingère le bundle avant de répondre. Pas de boucle (hop≥1 = local only).
    """
    import os
    import urllib.request

    t0 = now_mono_ns()
    wanted = [x.strip() for x in ids.split(",") if x.strip()]
    if not wanted:
        raise HTTPException(status_code=400, detail="no_concept_ids")
    if len(wanted) > 512:
        raise HTTPException(status_code=413, detail="too_many_concept_ids")
    store = _store(request)
    known = [cid for cid in wanted if store.knows_concept(cid)]
    missing = [cid for cid in wanted if cid not in known]
    federated = False
    hop = int(request.headers.get("x-artcb-federation-hop") or "0")
    federate_on = os.getenv("ARTCB_CONCEPT_FEDERATE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if missing and federate_on and hop < 1:
        peers = [
            "https://artcb.me",
            "https://n2.artcb.me",
            "https://n3.artcb.me",
            "https://n4.artcb.me",
        ]
        # Avoid self only on exact Host match (R324 2026-09-12T01:05:00Z).
        # ~~host.endswith("." + peer_host)~~ barred: n2.artcb.me.endswith(".artcb.me")
        # skipped the apex publisher https://artcb.me → federation never persisted.
        host = (request.headers.get("host") or "").split(":")[0].lower()
        for peer in peers:
            peer_host = peer.split("//", 1)[-1].split("/")[0].lower()
            if host and host == peer_host:
                continue
            url = f"{peer}/api/v1/concepts/resolve?ids={','.join(missing)}"
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/octet-stream",
                    "X-ARTCB-Federation-Hop": "1",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
            except Exception:  # noqa: BLE001
                continue
            if len(data) <= 10:
                continue
            try:
                import_bundle(store, data, agent_id="federation")
                federated = True
            except ConceptBundleError:
                continue
            known = [cid for cid in wanted if store.knows_concept(cid)]
            missing = [cid for cid in wanted if cid not in known]
            if not missing:
                break

    bundle = export_bundle(store, known) if known else encode_concept_bundle([])
    _trace(
        request,
        kind="concept_resolve",
        t0=t0,
        requested=len(wanted),
        known=len(known),
        missing=len(missing),
        bundle_bytes=len(bundle),
        federated=federated,
        federation_hop=hop,
    )
    return Response(
        content=bundle,
        media_type="application/octet-stream",
        headers={
            "X-ARTCB-Concept-Requested": str(len(wanted)),
            "X-ARTCB-Concept-Known": str(len(known)),
            "X-ARTCB-Concept-Missing": ",".join(missing)[:2000],
            "X-ARTCB-Bundle-Sha256": bundle_sha256(bundle),
            "X-ARTCB-Concept-Federated": "1" if federated else "0",
            "X-ARTCB-Trace-Ns": str(now_mono_ns() - t0),
        },
    )


@router.get("/stats", summary="État du ConceptStore de ce nœud")
def concept_stats(request: Request) -> dict:
    t0 = now_mono_ns()
    store = _store(request)
    out = store.stats()
    out["ts_ns"] = now_wall_ns()
    out["dur_ns"] = now_mono_ns() - t0
    out["network_sync"] = "R320"
    return out


@router.get("/{concept_id}", summary="Métadonnées humaines d'un ConceptID")
def concept_meta(concept_id: str, request: Request) -> dict:
    store = _store(request)
    record = store.get_concept_record(concept_id)
    if record is None:
        raise HTTPException(status_code=404, detail="concept_unknown_on_this_node")
    return {
        "concept_id": concept_id,
        "record": record.to_dict(),
        "ts_ns": now_wall_ns(),
        "note": "vue humaine — le canal IA↔IA utilise /resolve en binaire",
    }
