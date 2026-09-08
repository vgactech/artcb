"""GET /api/v1/trace — nanosecond JSONL produced by live traffic and book writes."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from src.artcb.trace.ns import list_traces, summarize

router = APIRouter(prefix="/api/v1/trace", tags=["trace"])


def _state(request: Request):
    return request.app.state.artcb


@router.get("")
def list_ns_traces(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
    kind: str | None = Query(None),
) -> dict:
    data_dir = _state(request).settings.data_dir
    rows = list_traces(data_dir, limit=limit, kind=kind)
    return {
        "rows": rows,
        "summary": summarize(rows),
        "path": "data/trace/ns.jsonl",
        "unit": "nanosecond",
        "includes_book": True,
        "includes_pbft": True,
        "granularity": "nanosecond",
    }
