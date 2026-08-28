"""WebSocket realtime graph updates — CDC §20."""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.llm_encoder import LLMEncoder
from src.artcb.rtleg.events import RTLEGEvent

logger = logging.getLogger("artcb.api.websocket")
router = APIRouter()


@router.websocket("/ws/graph/{session_id}")
async def graph_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    state = websocket.app.state.artcb
    logger.debug("WebSocket connected session_id=%s", session_id)

    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")
            payload = message.get("payload") or message

            if msg_type == "encode":
                text = payload.get("text", "")
                use_llm = bool(payload.get("use_llm", False))
                graph_id = f"g_{uuid.uuid4().hex[:12]}"
                graph = LLMEncoder(encoder=state.encoder).encode(
                    text, use_llm=use_llm, session_id=graph_id
                )
                state.register_graph(graph)
                state.vectors.index_graph(graph)
                for node in graph.nodes:
                    await websocket.send_json(
                        {
                            "type": "node_added",
                            "node": node.model_dump(),
                            "agent": "explorer",
                        }
                    )
                state.timeline.append(
                    RTLEGEvent(
                        session_id=session_id,
                        agent="explorer",
                        event_type="ws_encode",
                        graph_id=graph.graph_id,
                        payload={"nodes": len(graph.nodes)},
                    )
                )
                await websocket.send_json(
                    {
                        "type": "encode_complete",
                        "graph_id": graph.graph_id,
                        "node_count": len(graph.nodes),
                        "compression_ratio": IREncoder.compression_ratio(graph),
                    }
                )

            elif msg_type == "search":
                query = payload.get("query", "")
                results = state.vectors.search(query, top_k=3)
                await websocket.send_json({"type": "search_results", "results": results})

            elif msg_type == "select_node":
                node_id = payload.get("node_id")
                graph_id = payload.get("graph_id")
                graph = state.get_graph(graph_id) if graph_id else None
                node = None
                if graph:
                    node = next((n for n in graph.nodes if n.id == node_id), None)
                await websocket.send_json(
                    {
                        "type": "node_selected",
                        "node_id": node_id,
                        "node": node.model_dump() if node else None,
                    }
                )

            elif msg_type == "agents_run":
                text = payload.get("text", "")
                result = state.dual.run(text)
                graph = result.graph
                state.register_graph(graph)
                state.vectors.index_graph(graph)
                await websocket.send_json(
                    {
                        "type": "pol_update",
                        "score": result.pol.pol_score,
                        "compression": result.pol.delta_compression,
                        "validation": result.pol.validation_rate,
                    }
                )
                await websocket.send_json(
                    {
                        "type": "node_validated",
                        "graph_id": graph.graph_id,
                        "agent": "critic",
                        "pol_delta": result.pol.pol_score,
                    }
                )

            else:
                await websocket.send_json(
                    {"type": "error", "code": "unknown_type", "message": f"Unknown type: {msg_type}"}
                )

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected session_id=%s", session_id)
    except json.JSONDecodeError as exc:
        logger.error("WebSocket JSON error: %s", exc)
        await websocket.send_json(
            {"type": "error", "code": "invalid_json", "message": str(exc)}
        )


# ─────────────────────────────────────────────────────────────────────────────
# /ws/stream_thought — Graver le raisonnement token-par-token dans la chaîne
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/stream_thought")
async def stream_thought_ws(websocket: WebSocket) -> None:
    """
    WebSocket pour graver le raisonnement d'un agent IA token-par-token.

    Protocole :
      Client → {"type": "start", "session_id": "...", "agent_id": "...", "memo_type": "reasoning"}
      Client → {"type": "token", "text": "..."}   (répété N fois)
      Client → {"type": "commit", "wallet_name": "...", "visibility": "private"}
      Server → {"type": "committed", "block_index": N, "block_hash": "...", "pol_score": ...}
      Client → {"type": "abort"}  (optionnel)
    """
    await websocket.accept()
    state = websocket.app.state.artcb
    logger.debug("stream_thought connected")

    session_id: str = f"stream_{uuid.uuid4().hex[:12]}"
    agent_id: str = "agent_anonymous"
    memo_type: str = "reasoning"
    tokens: list[str] = []

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "start":
                # Initialise la session de stream
                session_id = msg.get("session_id", session_id)
                agent_id = msg.get("agent_id", agent_id)
                memo_type = msg.get("memo_type", memo_type)
                tokens = []
                await websocket.send_json({
                    "type": "started",
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "memo_type": memo_type,
                    "message": "Stream ouvert — envoyez des tokens puis 'commit'",
                })

            elif mtype == "token":
                # Accumule chaque token
                token = msg.get("text", "")
                if token:
                    tokens.append(token)
                    # ACK léger pour flot continu
                    await websocket.send_json({
                        "type": "token_ack",
                        "count": len(tokens),
                    })

            elif mtype == "commit":
                # Grave tout le flux dans un bloc PoL
                if not tokens:
                    await websocket.send_json({
                        "type": "error",
                        "code": "empty_stream",
                        "message": "Aucun token reçu à graver",
                    })
                    continue

                full_text = (
                    f"[AI STREAM — {memo_type.upper()}]\n"
                    f"Agent: {agent_id}\n"
                    f"Session: {session_id}\n"
                    f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                    f"Tokens: {len(tokens)}\n\n"
                    + "".join(tokens)
                )

                wallet_name: str | None = msg.get("wallet_name")
                visibility: str = msg.get("visibility", "private")
                graph_id = f"stream_{uuid.uuid4().hex[:12]}"

                try:
                    from src.artcb.ir.llm_encoder import LLMEncoder
                    from src.artcb.ir.models import sha256_text

                    encoder = LLMEncoder(encoder=state.encoder)
                    graph = encoder.encode(full_text, use_llm=False, session_id=graph_id)
                    state.register_graph(graph)

                    graph_root = sha256_text(graph.checksum).replace("sha256:", "")

                    # Wallet optionnel
                    contributors = None
                    wallet_password_ws: str | None = msg.get("wallet_password")
                    if wallet_name:
                        try:
                            from src.artcb.wallet.manager import WalletManager
                            from src.artcb.mining.pipeline import build_contributors
                            wallet = WalletManager().load_wallet(name=wallet_name, user_password=wallet_password_ws)
                            contributors = build_contributors(
                                actor_address=wallet.address,
                                pol_score=0.72,
                                wallet=wallet,
                                graph_root=graph_root,
                                machine_registry=getattr(state, "machine_registry", None),
                                human_registry=getattr(state, "human_registry", None),
                                work_registry=getattr(state, "work_registry", None),
                            )
                        except Exception:
                            pass

                    public_symbols = {
                        "learning_source": f"ai:stream:{memo_type}",
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "memo_type": memo_type,
                        "token_count": str(len(tokens)),
                    }

                    block = state.chain.append_block(
                        graph_id=graph.graph_id,
                        graph_root=graph_root,
                        pol_score=0.72,
                        visibility=visibility,
                        group_id=None,
                        contributors=contributors,
                        public_symbols=public_symbols if visibility == "public" else None,
                    )

                    logger.info(
                        "stream_thought gravé: bloc #%d tokens=%d agent=%s",
                        block.index, len(tokens), agent_id,
                    )

                    # Reset pour un nouveau flux dans la même connexion
                    committed_tokens = len(tokens)
                    tokens = []

                    await websocket.send_json({
                        "type": "committed",
                        "block_index": block.index,
                        "block_hash": block.hash,
                        "graph_id": graph.graph_id,
                        "pol_score": 0.72,
                        "token_count": committed_tokens,
                        "node_count": len(graph.nodes),
                        "message": (
                            f"✅ {committed_tokens} tokens gravés en bloc #{block.index} "
                            f"— immuable ML-DSA-65"
                        ),
                    })

                except Exception as exc:
                    logger.error("stream_thought commit error: %s", exc)
                    await websocket.send_json({
                        "type": "error",
                        "code": "commit_failed",
                        "message": str(exc),
                    })

            elif mtype == "abort":
                tokens = []
                await websocket.send_json({
                    "type": "aborted",
                    "message": "Stream annulé — tokens effacés",
                })

            elif mtype == "ping":
                await websocket.send_json({"type": "pong", "token_buffer": len(tokens)})

            else:
                await websocket.send_json({
                    "type": "error",
                    "code": "unknown_type",
                    "message": f"Type inconnu: {mtype}. Valides: start|token|commit|abort|ping",
                })

    except WebSocketDisconnect:
        logger.debug(
            "stream_thought disconnected session=%s tokens_lost=%d",
            session_id, len(tokens),
        )
    except json.JSONDecodeError as exc:
        logger.error("stream_thought JSON error: %s", exc)
        try:
            await websocket.send_json(
                {"type": "error", "code": "invalid_json", "message": str(exc)}
            )
        except Exception:
            pass
