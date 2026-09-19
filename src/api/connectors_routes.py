"""Connecteurs API — clés utilisateur pour IA et sources d'apprentissage."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.artcb.connectors.manager import (
    DATA_SOURCE_PROVIDERS,
    LLM_PROVIDERS,
    ConnectorError,
    ConnectorManager,
)
from src.artcb.connectors.sources import DataSourceError, fetch_learning_text, test_connector

logger = logging.getLogger("artcb.api.connectors")
router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


class SaveConnectorRequest(BaseModel):
    provider: str = Field(min_length=2)
    label: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=8)
    config: dict = Field(default_factory=dict)
    connector_id: str | None = None


class LearnFromSourceRequest(BaseModel):
    connector_id: str
    session_id: str = "learn_session"
    use_llm: bool = False
    llm_provider: str | None = None
    limit: int = Field(default=30, ge=1, le=500)


def _state(request: Request):
    return request.app.state.artcb


def _connectors(request: Request) -> ConnectorManager:
    return _state(request).connectors


@router.get("/formats")
def list_supported_formats_endpoint() -> dict:
    from src.artcb.io.media_ingest import list_supported_formats

    fmts = list_supported_formats()
    return {
        "formats": fmts,
        "total_extensions": len(fmts.get("all_extensions", [])),
        "note": "JSON, CSV, YAML, TOML, XML, HTML, PDF, images, audio, vidéo, DOCX, XLSX, EPUB, sous-titres…",
    }


@router.get("")
def list_connectors(
    request: Request,
    kind: str | None = Query(None, description="llm | data_source"),
) -> dict:
    mgr = _connectors(request)
    items = [r.public_dict() for r in mgr.list_connectors(kind=kind)]
    return {
        "connectors": items,
        "count": len(items),
        "llm_providers": sorted(LLM_PROVIDERS),
        "data_source_providers": sorted(DATA_SOURCE_PROVIDERS),
        "storage": "local_encrypted",
        "note": "Clés stockées chiffrées sur VOTRE machine — jamais sur cloud ARTCB",
    }


@router.post("")
def save_connector(body: SaveConnectorRequest, request: Request) -> dict:
    mgr = _connectors(request)
    try:
        record = mgr.save_connector(
            provider=body.provider,  # type: ignore[arg-type]
            label=body.label,
            api_key=body.api_key,
            config=body.config,
            connector_id=body.connector_id,
        )
        return {"connector": record.public_dict(), "message": "Connecteur enregistré (local chiffré)"}
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{connector_id}")
def delete_connector(connector_id: str, request: Request) -> dict:
    mgr = _connectors(request)
    if not mgr.delete_connector(connector_id):
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"deleted": connector_id}


@router.post("/{connector_id}/test")
def test_connector_endpoint(connector_id: str, request: Request) -> dict:
    mgr = _connectors(request)
    record = mgr.get_connector(connector_id)
    if not record:
        raise HTTPException(status_code=404, detail="Connector not found")
    ok, message = test_connector(record)
    mgr.set_test_result(connector_id, ok, message)
    return {"connector_id": connector_id, "ok": ok, "message": message}


@router.post("/{connector_id}/learn")
def learn_from_source(connector_id: str, body: LearnFromSourceRequest, request: Request) -> dict:
    """
    Récupère le texte depuis la source connectée (DB client) et lance l'apprentissage IR + PoL.
    Le résultat peut ensuite être stocké sur la blockchain via POST /store.
    """
    state = _state(request)
    mgr = _connectors(request)
    record = mgr.get_connector(connector_id)
    if not record:
        raise HTTPException(status_code=404, detail="Connector not found")
    if record.provider not in DATA_SOURCE_PROVIDERS:
        raise HTTPException(status_code=400, detail="Ce connecteur n'est pas une source de données")

    try:
        text = fetch_learning_text(record, limit=body.limit)
    except DataSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="Source vide — rien à apprendre")

    from src.artcb.ir.llm_encoder import LLMEncoder
    from src.artcb.rtleg.events import RTLEGEvent

    session_id = body.session_id or f"g_{uuid.uuid4().hex[:12]}"
    llm_encoder = LLMEncoder(encoder=state.encoder, connectors=mgr)
    if body.use_llm and body.llm_provider:
        graph = llm_encoder.encode(
            text,
            use_llm=True,
            session_id=session_id,
            llm_provider=body.llm_provider,
        )
        result = state.dual.critic.validate(graph)
    else:
        result = state.dual.run(text)

    graph = result.graph
    state.register_graph(graph)
    pol = result.pol

    state.timeline.append(
        RTLEGEvent(
            session_id=body.session_id,
            agent="critic",
            event_type="learned_from_connector",
            graph_id=graph.graph_id,
            payload={
                "connector_id": connector_id,
                "provider": record.provider,
                "chars_ingested": len(text),
                "pol": pol.to_dict(),
            },
        )
    )

    return {
        "graph_id": graph.graph_id,
        "node_count": len(graph.nodes),
        "chars_ingested": len(text),
        "source": record.public_dict(),
        "pol": pol.to_dict(),
        "message": "Apprentissage terminé — utilisez POST /store pour graver sur la blockchain",
    }
