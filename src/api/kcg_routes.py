"""Routes KCG — GO-F 2026-09-07.

POST /api/v1/kcg/publish      — publie une entrée de connaissance (après PoL)
POST /api/v1/kcg/consult      — enregistre un événement CONSULT
POST /api/v1/kcg/use          — enregistre un événement USE + mesure delta
GET  /api/v1/kcg/knowledge    — liste toutes les entrées
GET  /api/v1/kcg/knowledge/{kid} — détail + stats d'une entrée
GET  /api/v1/kcg/stats        — statistiques globales du KCG
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.artcb.kcg.events import (
    ConsultEvent,
    KnowledgeEntry,
    UseEvent,
    knowledge_id,
)
from src.artcb.kcg.store import KCGIndex, KCGStore

router = APIRouter(prefix="/api/v1/kcg", tags=["kcg"])


def _kcg_index(request: Request) -> KCGIndex:
    """Récupère ou crée le KCGIndex depuis l'état de l'app."""
    state = request.app.state
    if not hasattr(state, "kcg_index") or state.kcg_index is None:
        data_dir = Path(getattr(state, "data_dir", "data"))
        store = KCGStore(data_dir)
        state.kcg_index = KCGIndex(store)
    return state.kcg_index


# ── Modèles Pydantic ─────────────────────────────────────────────────────────

class PublishKnowledgeRequest(BaseModel):
    graph_id: str
    producer_address: str
    pol_block_index: int = 0
    pol_score: float = 0.0
    title: str = ""
    visibility: str = "public"


class ConsultRequest(BaseModel):
    graph_id: str
    consultant_address: str
    agent_id: str = ""
    session_id: str = ""


class UseRequest(BaseModel):
    consult_id: str = ""
    graph_id: str
    consumer_address: str
    agent_id: str = ""
    session_id: str = ""
    score_before: float | None = None
    score_after: float | None = None
    derived_graph_id: str = ""


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/publish")
def publish_knowledge(req: PublishKnowledgeRequest, request: Request) -> dict[str, Any]:
    """Publie une entrée de connaissance dans le KCG après validation PoL."""
    idx = _kcg_index(request)
    kid = knowledge_id(req.graph_id)
    title = (req.title or req.graph_id)[:64]
    entry = KnowledgeEntry(
        knowledge_id=kid,
        graph_id=req.graph_id,
        producer_address=req.producer_address,
        pol_block_index=req.pol_block_index,
        pol_score=req.pol_score,
        title=title,
        visibility=req.visibility,
    )
    saved = idx.publish(entry)
    return {
        "published": True,
        "knowledge_id": saved.knowledge_id,
        "graph_id": saved.graph_id,
        "producer_address": saved.producer_address,
        "pol_score": saved.pol_score,
        "visibility": saved.visibility,
        "fee_active": False,  # GO-G activera le fee
        "note": "GO-F : enregistrement sans fee. GO-G activera Reasoning Fee.",
    }


@router.post("/consult")
def record_consult(req: ConsultRequest, request: Request) -> dict[str, Any]:
    """Enregistre un événement CONSULT (découverte + accès à K)."""
    idx = _kcg_index(request)
    kid = knowledge_id(req.graph_id)
    if not idx.get(kid):
        raise HTTPException(
            status_code=404,
            detail=f"KnowledgeID {kid} introuvable — publiez d'abord via /kcg/publish",
        )
    event = ConsultEvent(
        knowledge_id=kid,
        graph_id=req.graph_id,
        consultant_address=req.consultant_address,
        agent_id=req.agent_id,
        session_id=req.session_id,
        fee_amount_satoshi=0,   # GO-F : pas de fee
        fee_pending=False,      # GO-G activera fee_pending=True
    )
    saved = idx.consult(event)
    return {
        "consult_id": saved.consult_id,
        "knowledge_id": saved.knowledge_id,
        "consultant_address": saved.consultant_address,
        "timestamp": saved.timestamp,
        "fee_pending": saved.fee_pending,
        "fee_amount_satoshi": saved.fee_amount_satoshi,
        "note": "GO-F : CONSULT enregistré sans fee. GO-G activera le Reasoning Fee.",
    }


@router.post("/use")
def record_use(req: UseRequest, request: Request) -> dict[str, Any]:
    """Enregistre un événement USE avec mesure optionnelle de delta d'utilité."""
    idx = _kcg_index(request)
    kid = knowledge_id(req.graph_id)
    derived_kid = knowledge_id(req.derived_graph_id) if req.derived_graph_id else ""
    event = UseEvent(
        consult_id=req.consult_id,
        knowledge_id=kid,
        graph_id=req.graph_id,
        consumer_address=req.consumer_address,
        agent_id=req.agent_id,
        session_id=req.session_id,
        score_before=req.score_before,
        score_after=req.score_after,
        derived_graph_id=req.derived_graph_id,
        derived_knowledge_id=derived_kid,
    )
    saved = idx.use(event)
    entry = idx.get(kid)
    return {
        "usage_id": saved.usage_id,
        "knowledge_id": saved.knowledge_id,
        "consumer_address": saved.consumer_address,
        "delta_utility": saved.delta_utility,
        "utility_measured": saved.utility_measured,
        "timestamp": saved.timestamp,
        "derived_knowledge_id": saved.derived_knowledge_id or None,
        "reputation_after": entry.reputation_score if entry else None,
        "note": "GO-F : USE enregistré. Delta utilité mis à jour dans le KCG.",
    }


@router.get("/knowledge")
def list_knowledge(request: Request) -> dict[str, Any]:
    """Liste toutes les entrées de connaissance du KCG."""
    idx = _kcg_index(request)
    entries = idx.all()
    return {
        "knowledge": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@router.get("/knowledge/{kid}")
def get_knowledge(kid: str, request: Request) -> dict[str, Any]:
    """Détail d'une entrée KCG avec ses statistiques."""
    idx = _kcg_index(request)
    entry = idx.get(kid)
    if not entry:
        raise HTTPException(status_code=404, detail=f"KnowledgeID {kid} introuvable")
    events = idx._store.events_for_knowledge(kid)
    return {
        "entry": entry.to_dict(),
        "events_count": len(events),
        "consult_count": entry.consult_count,
        "use_count": entry.use_count,
        "total_delta_utility": entry.total_delta_utility,
        "reputation_score": entry.reputation_score,
    }


@router.get("/stats")
def kcg_stats(request: Request) -> dict[str, Any]:
    """Statistiques globales du KCG."""
    idx = _kcg_index(request)
    return idx.stats()
