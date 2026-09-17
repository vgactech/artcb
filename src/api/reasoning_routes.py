"""Routes API — REASONING_RECORD ARTCB (R355, 2026-09-17).

Expose :
  GET  /api/v1/reasoning/records        → liste des records locaux
  GET  /api/v1/reasoning/records/count  → nombre de records
  POST /api/v1/reasoning/record         → créer/compléter un record manuellement
  GET  /api/v1/reasoning/record/{id}    → récupérer un record par record_id
  POST /api/v1/reasoning/record/{id}/seal → sceller un record (résultat + apprentissage)

CERTIFIED_100=false — données locales uniquement.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.artcb.reasoning.record import (
    ReasoningRecord,
    RecordAction,
    RecordOutcome,
    ReasoningRecordStore,
    get_record_store,
    record_from_dict,
)
from src.artcb.reasoning.reference_id import (
    ReferenceID,
    RefType,
    ref_code,
    ref_block,
    ref_rule,
    ref_human,
)
from src.artcb.reasoning.first_reflex import (
    FirstReflex,
    EarliestDetectablePoint,
    estimate_earliest_from_logs,
)
from src.artcb.reflex.core import get_reflex_engine

logger = logging.getLogger("artcb.api.reasoning")
router = APIRouter(prefix="/api/v1/reasoning", tags=["reasoning"])


# ─── Schémas ──────────────────────────────────────────────────────────────────


class CreateRecordRequest(BaseModel):
    """Crée un REASONING_RECORD manuellement (ex: depuis un hook Bob IDE)."""
    session_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(default="bob-ide", max_length=64)
    context_summary: str = Field(default="", max_length=2000)
    trigger_text: str = Field(
        default="",
        max_length=4000,
        description="Texte du prompt à analyser pour détecter le réflexe",
    )
    files: list[str] = Field(default_factory=list, max_length=20)
    action: str = Field(default="analyze", max_length=32)
    action_detail: str = Field(default="", max_length=500)


class SealRecordRequest(BaseModel):
    """Scelle un REASONING_RECORD existant."""
    outcome: str = Field(default="pass", max_length=32)
    outcome_detail: str = Field(default="", max_length=500)
    learning: str = Field(default="", max_length=2000)
    new_rule_candidate: bool = False


# ─── Routes ───────────────────────────────────────────────────────────────────


@router.get("/records/count", summary="Nombre de REASONING_RECORD locaux")
def records_count() -> dict:
    store = get_record_store()
    return {
        "count": store.count(),
        "certified_100": False,
        "note": "Données locales uniquement — data/trace/reasoning_records.jsonl",
    }


@router.get("/records", summary="Liste des REASONING_RECORD locaux")
def list_records(limit: int = 20, session_id: str = "") -> dict:
    """Retourne les derniers REASONING_RECORD persistés localement.

    Args:
        limit:      Nombre max de records à retourner (défaut 20, max 100).
        session_id: Filtrer par session_id (optionnel).
    """
    limit = min(limit, 100)
    store = get_record_store()
    rows = store.load_by_session(session_id) if session_id else store.load_all()
    return {
        "records": rows[-limit:],
        "total": len(rows),
        "returned": min(len(rows), limit),
        "certified_100": False,
    }


@router.post("/record", summary="Créer un REASONING_RECORD via le réflexe ARTCB")
def create_record(body: CreateRecordRequest) -> dict:
    """Crée un REASONING_RECORD en activant le ReflexEngine.

    Le réflexe est activé sur le texte + fichiers fournis.
    Un FIRST_REFLEX et un EARLIEST_DETECTABLE_POINT sont calculés.
    Le record est persisté localement.
    CERTIFIED_100=false.
    """
    engine = get_reflex_engine()
    try:
        action_enum = RecordAction(body.action.lower())
    except ValueError:
        action_enum = RecordAction.ANALYZE

    report = engine.activate(
        text=body.trigger_text or body.context_summary,
        files=body.files,
        session_id=body.session_id,
        agent_id=body.agent_id,
    )

    record_id = report.get("record_id", "")
    return {
        "record_created": True,
        "record_id": record_id,
        "priority": report.get("priority"),
        "priority_name": report.get("priority_name"),
        "action": report.get("action"),
        "first_reflex": report.get("first_reflex"),
        "earliest": report.get("earliest"),
        "triggers_count": len(report.get("triggers", [])),
        "certified_100": False,
        "note": "REASONING_RECORD créé et persisté. Utilisez /seal pour marquer le résultat.",
    }


@router.get("/record/{record_id}", summary="Récupérer un REASONING_RECORD par ID")
def get_record(record_id: str) -> dict:
    """Récupère un REASONING_RECORD depuis le store local par son record_id."""
    store = get_record_store()
    rows = store.load_all()
    match = next((r for r in rows if r.get("record_id", "").startswith(record_id)), None)
    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"record_not_found: {record_id}. Vérifiez data/trace/reasoning_records.jsonl.",
        )
    return match


@router.post("/record/{record_id}/seal", summary="Sceller un REASONING_RECORD (R355.2–R355.3)")
def seal_record(record_id: str, body: SealRecordRequest) -> dict:
    """Scelle un REASONING_RECORD existant — préserve FIRST_REFLEX + EARLIEST + refs + obs.

    R355.2 : le record scellé est frozen (SealedRecordError si modifié ultérieurement).
    R355.3 : reconstruit le record complet depuis le JSONL — first_reflex, earliest,
             reference_ids et observations sont préservés.
    final_hash = SHA-256(canonique complet = TOUS les champs).
    CERTIFIED_100=false.
    """
    store = get_record_store()
    try:
        outcome_enum = RecordOutcome(body.outcome.lower())
    except ValueError:
        outcome_enum = RecordOutcome.UNKNOWN

    # R355.3 : seal_in_place reconstruit le record complet (first_reflex, earliest, refs, obs)
    sealed = store.seal_in_place(
        record_id,
        outcome=outcome_enum,
        outcome_detail=body.outcome_detail,
        learning=body.learning,
        new_rule_candidate=body.new_rule_candidate,
    )
    if sealed is None:
        raise HTTPException(status_code=404, detail=f"record_not_found: {record_id}")

    logger.info(
        "REASONING_RECORD sealed: record_id=%s final_hash=%s outcome=%s frozen=%s",
        sealed.record_id[:12], sealed.final_hash[:12], outcome_enum.value, sealed.frozen,
    )

    return {
        "sealed": True,
        "record_id": sealed.record_id,
        "final_hash": sealed.final_hash,   # R355.1 : hash de TOUT le record
        "frozen": sealed.frozen,           # R355.2 : toujours True après seal
        "outcome": outcome_enum.value,
        "new_rule_candidate": body.new_rule_candidate,
        "first_reflex_preserved": sealed.first_reflex is not None,   # R355.3
        "earliest_preserved": sealed.earliest is not None,           # R355.3
        "observations_count": len(sealed.observations),              # R355.3
        "reference_ids_count": len(sealed.reference_ids),            # R355.3
        "certified_100": False,
        "note": (
            "R355.1: final_hash=SHA-256(tous les champs). "
            "R355.2: frozen=True. "
            "R355.3: first_reflex+earliest+refs+obs préservés."
        ),
    }


@router.get("/reflex-records", summary="REASONING_RECORD créés par le ReflexEngine")
def reflex_records() -> dict:
    """Retourne les records créés par le ReflexEngine lors des activations.

    Combine /records filtrés par agent_id=bob-ide avec les données du ReflexEngine.
    CERTIFIED_100=false.
    """
    engine = get_reflex_engine()
    store = get_record_store()
    records = store.load_all()
    reflex_records_list = [
        r for r in records
        if r.get("first_reflex") is not None
    ]
    return {
        "reflex_records": reflex_records_list[-20:],
        "total_reflex_records": len(reflex_records_list),
        "engine_total_triggers": engine.report()["total_triggers"],
        "certified_100": False,
    }
