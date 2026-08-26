"""
Module IA Autonome — ARTCB Agent Routes
========================================
Permet à un agent IA (Bob, Cursor, LangChain…) d'utiliser la blockchain ARTCB
comme mémoire persistante, moteur de raisonnement et bus d'événements.

Endpoints :
  GET  /api/v1/ai/status              — Snapshot complet état IA (P2)
  POST /api/v1/ai/memo                — Graver une observation dans la chaîne (P6)
  POST /api/v1/ai/think               — Question → Explorer+Critic → bloc PoL (P3)
  GET  /api/v1/chain/search           — Recherche sémantique cross-graphs (P4)
  GET  /api/v1/chain/export           — Export JSONL/JSON de la chaîne complète (P5)
  POST /api/v1/webhooks/register      — Webhooks sortants sur nouveaux blocs (P7)
  GET  /api/v1/webhooks/list          — Liste les webhooks actifs
  DELETE /api/v1/webhooks/{id}        — Révoque un webhook

Sécurité : tous les endpoints sensibles utilisent verify_api_key (Bearer).
"""

from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.api.api_keys_routes import verify_api_key, require_scope

logger = logging.getLogger("artcb.api.ai")

router_ai = APIRouter(prefix="/api/v1/ai", tags=["ai-agent"])
router_chain_ext = APIRouter(prefix="/api/v1/chain", tags=["chain-extended"])
router_webhooks = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — contexte automatique à chaque prompt
# ─────────────────────────────────────────────────────────────────────────────

def _build_context_snippet(state, agent_id: str | None, limit: int = 5) -> str:
    """
    Construit un snippet de contexte compact à injecter dans CHAQUE prompt IA.
    Appelé automatiquement sur POST /ai/think et POST /ai/memo si inject_context=True.

    Contenu :
    - Hauteur de chaîne actuelle
    - N derniers memos de cet agent (titres + types)
    - Bugs ouverts non résolus
    - Dernière décision gravée

    Compact par design : 5 memos max, 80 chars/memo — ne pollue pas le prompt.
    """
    try:
        blocks = state.chain.list_blocks()
        chain_height = len(blocks)

        # Collecter memos IA (les plus récents d'abord)
        memos: list[dict] = []
        fixes_parents: set = set()
        for b in reversed(blocks):
            ps = b.get("public_symbols") or {}
            src = ps.get("learning_source", "")
            gid = b.get("graph_id", "")
            if not src.startswith("ai:") and not gid.startswith("ai_memo_") and not gid.startswith("ai_think_"):
                continue
            memo_type = ps.get("memo_type", "")
            if memo_type == "fix" and ps.get("parent_block_index"):
                try:
                    fixes_parents.add(int(ps["parent_block_index"]))
                except (ValueError, TypeError):
                    pass
            memos.append({
                "index": b.get("index"),
                "type": memo_type,
                "agent": ps.get("agent_id", "?"),
                "ts": (b.get("timestamp") or "")[:10],
                "tags": ps.get("tags", ""),
                "parent": ps.get("parent_block_index"),
            })

        # Bugs ouverts
        open_bugs = [
            m for m in memos
            if m["type"] == "bug" and m["index"] not in fixes_parents
        ][:3]

        # Memos récents de cet agent
        recent = [
            m for m in memos
            if agent_id is None or m["agent"] == agent_id
        ][:limit]

        lines = [
            f"[ARTCB CONTEXT — {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}]",
            f"Chain: {chain_height} blocs | {len(memos)} memos IA",
        ]
        if open_bugs:
            lines.append(f"Bugs ouverts: " + ", ".join(f"#{b['index']}" for b in open_bugs))
        if recent:
            lines.append(f"Tes {len(recent)} derniers memos:")
            for m in recent:
                tags = f" [{m['tags']}]" if m["tags"] else ""
                lines.append(f"  [{m['type']} #{m['index']}] {m['ts']}{tags}")
        lines.append("[FIN CONTEXTE — continue depuis ici]")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("_build_context_snippet error (non bloquant): %s", exc)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _state(request: Request):
    return request.app.state.artcb


def _webhooks_path(request: Request) -> Path:
    return _state(request).settings.data_dir / "webhooks.json"


def _load_webhooks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def _save_webhooks(path: Path, hooks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hooks, indent=2))


def _fire_webhooks(request: Request, event: str, payload: dict) -> None:
    """Déclenche tous les webhooks actifs pour un événement donné (fire-and-forget)."""
    path = _webhooks_path(request)
    hooks = _load_webhooks(path)
    active = [h for h in hooks if h.get("active", True) and event in h.get("events", [event])]
    if not active:
        return
    body = {"event": event, "timestamp": time.time(), "payload": payload}
    for hook in active:
        try:
            httpx.post(hook["url"], json=body, timeout=5.0)
            logger.debug("Webhook fired: %s → %s", event, hook["url"])
        except Exception as exc:
            logger.warning("Webhook failed %s: %s", hook["url"], exc)


# ─────────────────────────────────────────────────────────────────────────────
# P2 — GET /api/v1/ai/status
# ─────────────────────────────────────────────────────────────────────────────

@router_ai.get("/status", summary="Snapshot complet état IA — raisonnement, chaîne, mémoire")
def ai_status(
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    Retourne tout ce dont un agent IA a besoin pour se situer :
    - État de la chaîne (hauteur, dernier bloc, PoL moyen)
    - Graphes en mémoire vive
    - Scores PoL actuels
    - Derniers événements RT-LEG
    - Nombre de memos IA gravés
    - Clés actives (résumé)
    """
    state = _state(request)

    # Chaîne
    try:
        blocks = state.chain.list_blocks()
        chain_height = len(blocks)
        last_block = blocks[-1] if blocks else None
        pol_scores = [b.get("pol_score", 0) for b in blocks if b.get("pol_score", 0) > 0]
        pol_avg = sum(pol_scores) / len(pol_scores) if pol_scores else 0.0
        last_block_info = None
        if last_block:
            h = last_block.get("hash", "")
            last_block_info = {
                "index": last_block.get("index"),
                "hash": h[:16] + "…" if len(h) >= 16 else h,
                "graph_id": last_block.get("graph_id"),
                "pol_score": last_block.get("pol_score"),
                "timestamp": last_block.get("timestamp"),
                "visibility": last_block.get("visibility"),
            }
    except Exception as exc:
        chain_height = 0
        pol_avg = 0.0
        last_block_info = None
        logger.warning("ai/status chain read error: %s", exc)

    # Graphes en mémoire
    graphs_in_memory = len(state.graphs.cache) if hasattr(state.graphs, "cache") else 0

    # Memos IA (blocs avec learning_source="ai:memo")
    memo_count = 0
    try:
        memo_count = sum(
            1 for b in state.chain.list_blocks()
            if isinstance(b.get("public_symbols"), dict)
            and b.get("public_symbols", {}).get("learning_source", "").startswith("ai:")
        )
    except Exception:
        pass

    # RT-LEG récents
    recent_events = []
    try:
        for ev in list(state.timeline.events)[-10:]:
            recent_events.append({
                "agent": ev.agent,
                "event_type": ev.event_type,
                "session_id": ev.session_id,
                "timestamp": ev.timestamp if hasattr(ev, "timestamp") else None,
            })
    except Exception:
        pass

    # Clé courante (si Bearer fourni)
    current_key = None
    if key_record:
        current_key = {
            "key_id": key_record["key_id"],
            "label": key_record["label"],
            "scopes": key_record.get("scopes", []),
        }

    return {
        "agent_ready": True,
        "timestamp": time.time(),
        "chain": {
            "height": chain_height,
            "pol_avg": round(pol_avg, 4),
            "last_block": last_block_info,
        },
        "memory": {
            "graphs_in_ram": graphs_in_memory,
            "memo_blocks": memo_count,
        },
        "pol_state": state.pol_state,
        "recent_events": recent_events,
        "current_key": current_key,
        "capabilities": [
            "ai/memo", "ai/think", "chain/search",
            "chain/export", "webhooks/register",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# P6 — POST /api/v1/ai/memo
# ─────────────────────────────────────────────────────────────────────────────

class MemoRequest(BaseModel):
    content: str = Field(min_length=1, max_length=32000,
                         description="Observation, raisonnement, leçon, bug, solution…")
    memo_type: str = Field(
        default="observation",
        description="Type: observation | bug | fix | lesson | decision | hypothesis | goal | proof",
    )
    tags: list[str] = Field(default_factory=list, description="Tags libres (ex: ['i18n','bug','fix'])")
    session_id: str = Field(default="ai_memo", description="ID de session de l'agent")
    wallet_name: str | None = Field(default=None, description="Wallet pour signer le bloc")
    wallet_password: str | None = Field(default=None, description="Mot de passe du wallet")
    visibility: str = Field(default="private", description="private | public")
    parent_block_index: int | None = Field(default=None, description="Bloc parent (ex: bug que ce fix résout)")
    inject_context: bool = Field(
        default=True,
        description=(
            "Injecter le contexte blockchain dans le mémo avant gravure. "
            "Permet à l'agent de savoir ce qu'il faisait quand il a gravé cette observation."
        ),
    )


@router_ai.post("/memo", summary="Graver une observation IA dans la blockchain")
def ai_memo(
    body: MemoRequest,
    request: Request,
    key_record: Annotated[dict | None, Depends(require_scope("write"))] = None,
) -> dict:
    """
    Grave une observation structurée de l'agent IA dans un bloc PoL immuable.

    Le texte est enrichi avec les métadonnées (type, tags, session, timestamp)
    puis encodé en graphe IR → validé PoL → signé → bloc gravé.

    Chaque memo est récupérable via GET /api/v1/chain/search?q=<terme>.
    """
    state = _state(request)

    # Construire un texte structuré pour l'encodage IR
    agent_id = key_record["label"] if key_record else "agent_anonymous"

    # P0-3 — utiliser le wallet auto si aucun wallet explicite fourni
    if not body.wallet_name and key_record and key_record.get("auto_wallet"):
        body.wallet_name = key_record["auto_wallet"]

    # ── Injection contexte automatique — même logique que /ai/think ──
    # Chaque mémo gravé contient le snapshot de contexte au moment de la gravure.
    # Permet de retrouver exactement dans quel état l'agent était quand il a observé ça.
    context_snippet = ""
    if body.inject_context:
        context_snippet = _build_context_snippet(state, agent_id=agent_id)

    memo_text = (
        f"[AI MEMO — {body.memo_type.upper()}]\n"
        f"Agent: {agent_id}\n"
        f"Session: {body.session_id}\n"
        f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        f"Tags: {', '.join(body.tags) if body.tags else 'none'}\n\n"
        + (f"{context_snippet}\n\n" if context_snippet else "")
        + body.content
    )

    # Encoder en graphe IR
    graph_id = f"ai_memo_{uuid.uuid4().hex[:12]}"
    try:
        from src.artcb.ir.llm_encoder import LLMEncoder
        encoder = LLMEncoder(encoder=state.encoder)
        graph = encoder.encode(memo_text, use_llm=False, session_id=graph_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Encoding failed: {exc}") from exc

    state.register_graph(graph)

    # Valider PoL (bypass threshold pour les memos — toujours accepté)
    from src.artcb.ir.models import sha256_text
    graph_root = sha256_text(graph.checksum).replace("sha256:", "")

    # Wallet
    actor = None
    wallet = None
    if body.wallet_name:
        try:
            from src.artcb.wallet.manager import WalletManager
            wallet = WalletManager().load_wallet(name=body.wallet_name, user_password=body.wallet_password)
            actor = wallet.address
        except Exception:
            pass

    # Construire les contributors
    contributors = None
    if actor:
        from src.artcb.mining.pipeline import build_contributors
        contributors = build_contributors(
            actor_address=actor,
            pol_score=0.75,
            wallet=wallet,
            graph_root=graph_root,
        )

    # Marquer le bloc comme memo IA via public_symbols
    public_symbols = {
        "learning_source": f"ai:memo:{body.memo_type}",
        "agent_id": agent_id,
        "session_id": body.session_id,
        "tags": ",".join(body.tags),
        "memo_type": body.memo_type,
    }
    # P1-1 — lien parent→enfant (bug→fix)
    if body.parent_block_index is not None:
        public_symbols["parent_block_index"] = str(body.parent_block_index)

    # Graver le bloc — source="ai:memo" → bypass anti-Sybil si ARTCB_ANTI_SYBIL_AI_BYPASS=true
    # Plus de fallback sans contributors : tous les blocs IA sont signés normalement
    try:
        block = state.chain.append_block(
            graph_id=graph.graph_id,
            graph_root=graph_root,
            pol_score=0.75,
            visibility=body.visibility,
            group_id=None,
            contributors=contributors,
            public_symbols=public_symbols,
            source=f"ai:memo:{body.memo_type}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Block append failed: {exc}") from exc

    # Déclencher webhooks
    _fire_webhooks(request, "block_stored", {
        "block_index": block.index,
        "block_hash": block.hash,
        "memo_type": body.memo_type,
        "agent_id": agent_id,
        "graph_id": graph.graph_id,
    })

    logger.info("AI memo gravé: bloc #%d graph=%s agent=%s", block.index, graph.graph_id, agent_id)

    return {
        "memo_stored": True,
        "block_index": block.index,
        "block_hash": block.hash,
        "graph_id": graph.graph_id,
        "pol_score": 0.75,
        "memo_type": body.memo_type,
        "agent_id": agent_id,
        "node_count": len(graph.nodes),
        "message": f"Observation gravée en bloc #{block.index} — immuable ML-DSA-65",
    }


# ─────────────────────────────────────────────────────────────────────────────
# P3 — POST /api/v1/ai/think
# ─────────────────────────────────────────────────────────────────────────────

class ThinkRequest(BaseModel):
    question: str = Field(min_length=1, max_length=32000,
                           description="Problème, question ou sujet à raisonner")
    session_id: str = Field(default="ai_think")
    use_llm: bool = Field(default=False, description="Enrichir avec LLM connecteur")
    llm_provider: str | None = Field(default=None)
    wallet_name: str | None = None
    visibility: str = "private"
    store_block: bool = Field(default=True, description="Graver le résultat en bloc")


@router_ai.post("/think", summary="Question → Explorer+Critic → bloc PoL")
def ai_think(
    body: ThinkRequest,
    request: Request,
    key_record: Annotated[dict | None, Depends(require_scope("write"))] = None,
) -> dict:
    """
    L'agent IA soumet une question/problème → ARTCB lance le pipeline
    Explorer (encode) + Critic (valide PoL) → optionnellement grave un bloc.

    Retourne : graph_id, pol_score, nodes, block_hash (si store_block=True).
    C'est le cœur de la boucle autonome : penser → apprendre → graver.
    """
    state = _state(request)
    agent_id = key_record["label"] if key_record else "agent_anonymous"

    # Enrichir le texte avec le contexte agent
    think_text = (
        f"[AI THINK — {agent_id}]\n"
        f"Session: {body.session_id}\n"
        f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
        f"Question/Problème:\n{body.question}"
    )

    try:
        from src.artcb.ir.llm_encoder import LLMEncoder
        from src.artcb.mining.pipeline import MiningPipeline
        from src.artcb.wallet.manager import WalletManager

        # Résoudre le llm_provider via les connecteurs
        llm_record = None
        llm_key = None
        if body.use_llm and body.llm_provider:
            try:
                records = state.connectors.list_connectors()
                for rec in records:
                    if rec.provider == body.llm_provider and rec.enabled:
                        llm_record = rec
                        llm_key = rec._api_key
                        break
            except Exception:
                pass

        pipeline = MiningPipeline(
            dual=state.dual,
            chain=state.chain,
            wallet_manager=WalletManager(),
            connectors=state.connectors,
            groups=state.groups,
            timeline=state.timeline,
            register_graph=state.register_graph,
            publish_public_symbols=state.publish_public_symbols,
        )

        result = pipeline.run_from_text(
            think_text,
            session_id=body.session_id,
            wallet_name=body.wallet_name,
            visibility=body.visibility,
            store_block=body.store_block,
            learning_source=f"ai:think:{agent_id}",
        )

    except Exception as exc:
        logger.error("ai/think pipeline error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Think pipeline failed: {exc}") from exc

    if body.store_block and result.block_index is not None:
        _fire_webhooks(request, "block_stored", {
            "block_index": result.block_index,
            "block_hash": result.block_hash,
            "source": "ai:think",
            "agent_id": agent_id,
            "graph_id": result.graph_id,
        })

    return {
        "think_complete": True,
        "graph_id": result.graph_id,
        "pol_score": result.pol_score,
        "node_count": result.node_count if hasattr(result, "node_count") else None,
        "block_index": result.block_index,
        "block_hash": result.block_hash,
        "agent_id": agent_id,
        "message": (
            f"Raisonnement gravé en bloc #{result.block_index} (PoL {result.pol_score:.3f})"
            if result.block_index is not None
            else f"Raisonnement encodé (graph {result.graph_id}) — non gravé"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# P4 — GET /api/v1/chain/search
# ─────────────────────────────────────────────────────────────────────────────

@router_chain_ext.get("/search", summary="Recherche sémantique cross-graphs dans tous les blocs")
def chain_search(
    request: Request,
    q: str = Query(min_length=1, description="Terme ou phrase à rechercher"),
    top_k: int = Query(default=10, ge=1, le=100),
    visibility: str = Query(default="all", description="all | private | public"),
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    Recherche sémantique dans TOUS les graphes de TOUS les blocs gravés.
    Contrairement à POST /search qui cherche dans un seul graph_id,
    cet endpoint parcourt la chaîne entière.

    Retourne les nodes les plus proches avec leur bloc d'origine.
    """
    state = _state(request)
    results = []

    try:
        # Recherche vectorielle globale (tous graph_ids)
        raw_results = state.vectors.search(q, graph_id=None, top_k=top_k)

        # Enrichir avec les métadonnées de bloc
        block_by_graph: dict[str, dict] = {}
        try:
            for b in state.chain.list_blocks():
                gid = b.get("graph_id", "")
                if gid not in block_by_graph:
                    h = b.get("hash", "")
                    block_by_graph[gid] = {
                        "block_index": b.get("index"),
                        "block_hash": h[:16] + "…" if len(h) >= 16 else h,
                        "pol_score": b.get("pol_score"),
                        "timestamp": b.get("timestamp"),
                        "visibility": b.get("visibility"),
                    }
        except Exception:
            pass

        for r in raw_results:
            entry = dict(r)
            gid = r.get("graph_id", "")
            if gid in block_by_graph:
                entry["block"] = block_by_graph[gid]
            results.append(entry)

        # Filtrer par visibilité si demandé
        if visibility != "all":
            results = [
                r for r in results
                if r.get("block", {}).get("visibility", "private") == visibility
            ]

    except Exception as exc:
        logger.error("chain/search error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "query": q,
        "results": results[:top_k],
        "count": len(results[:top_k]),
        "total_graphs_searched": len(state.graphs.cache) if hasattr(state.graphs, "cache") else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# P5 — GET /api/v1/chain/export
# ─────────────────────────────────────────────────────────────────────────────

@router_chain_ext.get("/export", summary="Export compact de la chaîne entière")
def chain_export(
    request: Request,
    fmt: str = Query(default="jsonl", alias="format", description="jsonl | json | summary"),
    visibility: str = Query(default="all", description="all | private | public"),
    include_symbols: bool = Query(default=False),
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    Exporte la chaîne entière dans un format compact utilisable comme context LLM.

    - format=jsonl  : chaque bloc = une ligne JSON (optimal pour RAG/context)
    - format=json   : tableau JSON complet
    - format=summary: résumé lisible pour copier-coller dans un prompt
    """
    state = _state(request)

    try:
        all_blocks = state.chain.list_blocks()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if visibility != "all":
        all_blocks = [b for b in all_blocks if b.get("visibility") == visibility]

    if fmt == "jsonl":
        lines = []
        for b in all_blocks:
            h = b.get("hash", "")
            entry = {
                "index": b.get("index"),
                "timestamp": b.get("timestamp"),
                "graph_id": b.get("graph_id"),
                "pol_score": b.get("pol_score"),
                "hash": h[:32],
                "visibility": b.get("visibility"),
                "block_reward": b.get("block_reward"),
            }
            if include_symbols and b.get("public_symbols"):
                entry["public_symbols"] = b["public_symbols"]
            if b.get("contributors"):
                entry["contributor_count"] = len(b["contributors"])
            lines.append(json.dumps(entry, ensure_ascii=False))
        return {
            "format": "jsonl",
            "block_count": len(lines),
            "data": "\n".join(lines),
            "size_bytes": sum(len(l) for l in lines),
        }

    elif fmt == "summary":
        pol_scores = [b.get("pol_score", 0) for b in all_blocks if b.get("pol_score", 0) > 0]
        pol_avg = sum(pol_scores) / len(pol_scores) if pol_scores else 0.0
        last = all_blocks[-1] if all_blocks else None
        lines = [
            f"ARTCB Blockchain — {len(all_blocks)} blocs",
            f"PoL moyen: {pol_avg:.4f}",
            f"Dernier bloc: #{last.get('index')} ({last.get('timestamp')})" if last else "Aucun bloc",
            "",
        ]
        for b in all_blocks[-20:]:
            h = b.get("hash", "")
            gid = b.get("graph_id", "")
            ts_raw = b.get("timestamp", "")
            lines.append(
                f"#{b.get('index')} | {ts_raw[:19]} | PoL={b.get('pol_score', 0):.3f} | "
                f"{b.get('visibility')} | graph={gid[:12]}… | hash={h[:12]}…"
            )
        return {
            "format": "summary",
            "block_count": len(all_blocks),
            "data": "\n".join(lines),
        }

    else:  # json
        data = []
        for b in all_blocks:
            sig = b.get("signature", "")
            entry = {
                "index": b.get("index"),
                "timestamp": b.get("timestamp"),
                "graph_id": b.get("graph_id"),
                "pol_score": b.get("pol_score"),
                "hash": b.get("hash"),
                "hash_sha3": b.get("hash_sha3"),
                "signature": sig[:32] + "…" if sig else None,
                "visibility": b.get("visibility"),
                "block_reward": b.get("block_reward"),
                "contributors": b.get("contributors"),
            }
            if include_symbols:
                entry["public_symbols"] = b.get("public_symbols")
            data.append(entry)
        return {
            "format": "json",
            "block_count": len(data),
            "data": data,
        }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/chain/block-sizes — Analyse taille blocs + impact tokenomics
# ─────────────────────────────────────────────────────────────────────────────

@router_chain_ext.get(
    "/block-sizes",
    summary="Analyse taille des blocs et impact sur les tokenomics ARTCB",
)
def chain_block_sizes(
    request: Request,
    top_n: int = Query(default=10, ge=1, le=100, description="N plus gros + N plus petits blocs"),
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    ## Taille des blocs et tokenomics ARTCB

    ### Comment la taille d'un bloc est-elle calculée ?
    Un bloc ARTCB est une ligne JSON dans `data/chain/blocks.jsonl`.
    Sa taille = len(json_line.encode('utf-8')) en octets.

    Contenu variable d'un bloc :
    - **Champs fixes** (~400 octets) : index, timestamp, prev_hash, hash, signature, pol_score…
    - **contributors[]** (~200–800 octets/contributeur) : adresse, signature Ed25519/ML-DSA-65, pol_score, reward
    - **public_symbols** (0–N Ko) : métadonnées IA (agent_id, tags, memo_type, contenu texte court)
    - **graph_root / merkle_root** : hash SHA-256 du graphe IR encodé (taille fixe 64 chars)

    ### La taille affecte-t-elle la quantité de coins disponibles ?
    **NON** — le reward est `min(R(H), remaining_21M)` (D-024, géopopulation).
    L'index de bloc et la vitesse de minage **ne coupent plus** le reward.
    Un bloc de 1 octet et un bloc de 1 Mo reçoivent le même reward à H et supply restante égaux.

    ### Ce qui affecte RÉELLEMENT les coins disponibles :
    1. **R(H)** → reward population (50 à ≤1M humains, ~0.075 à 1 milliard)
    2. **Supply restante** → hard cap 21 000 000 (D-014) ; les frais reviennent au restant
    3. **HBP(H)** + **P_owner(n)** → répartition, pas le volume émis
    4. **PoL score** → poids W de chaque machine dans le pool travail

    ### Réponse rapide (H ≤ 1M) :
    - Chaque bloc émet **50 ARTCB** tant que H ≤ 1M et qu'il reste du cap
    - Le passage du bloc 209 999 au bloc 210 000 **ne divise plus** le reward
    - Supply max = 21 000 000 ARTCB (hard cap, plus un calendrier 50×210k×2)
    """
    state = _state(request)

    try:
        raw_blocks = state.chain.list_blocks()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not raw_blocks:
        return {"block_count": 0, "message": "Chaîne vide"}

    # ── Calcul taille par bloc ──────────────────────────────────────────────
    sizes: list[dict] = []
    total_bytes = 0
    total_reward_satoshi = 0

    for b in raw_blocks:
        # Taille réelle : le champ block_size_bytes si présent (nouveaux blocs)
        # sinon recalcul depuis la sérialisation JSON
        raw_size = b.get("block_size_bytes")
        if raw_size is None:
            import json as _json
            raw_size = len(_json.dumps(b, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        idx = b.get("index", 0)
        reward_satoshi = b.get("block_reward", 0)
        reward_artcb = reward_satoshi / 100_000_000
        n_contrib = len(b.get("contributors") or [])
        pol = b.get("pol_score", 0.0)

        # Décomposition taille estimée
        contrib_bytes = sum(
            len(str(c).encode("utf-8")) for c in (b.get("contributors") or [])
        )
        symbols_bytes = len(
            str(b.get("public_symbols", {})).encode("utf-8")
        )
        header_bytes = raw_size - contrib_bytes - symbols_bytes

        sizes.append({
            "index": idx,
            "size_bytes": raw_size,
            "size_kb": round(raw_size / 1024, 2),
            "reward_artcb": round(reward_artcb, 8),
            "reward_satoshi": reward_satoshi,
            "contributors": n_contrib,
            "pol_score": pol,
            "visibility": b.get("visibility"),
            "breakdown": {
                "header_bytes": max(0, header_bytes),
                "contributors_bytes": contrib_bytes,
                "public_symbols_bytes": symbols_bytes,
            },
        })
        total_bytes += raw_size
        total_reward_satoshi += reward_satoshi

    # ── Statistiques globales ────────────────────────────────────────────────
    all_sizes = [s["size_bytes"] for s in sizes]
    sorted_sizes = sorted(all_sizes)
    n = len(sorted_sizes)

    def percentile(lst: list, p: float) -> float:
        idx_f = p / 100 * (len(lst) - 1)
        lo, hi = int(idx_f), min(int(idx_f) + 1, len(lst) - 1)
        return lst[lo] + (idx_f - lo) * (lst[hi] - lst[lo])

    distribution = {
        "min_bytes": sorted_sizes[0],
        "p25_bytes": int(percentile(sorted_sizes, 25)),
        "p50_bytes": int(percentile(sorted_sizes, 50)),
        "p75_bytes": int(percentile(sorted_sizes, 75)),
        "p90_bytes": int(percentile(sorted_sizes, 90)),
        "p99_bytes": int(percentile(sorted_sizes, 99)),
        "max_bytes": sorted_sizes[-1],
        "avg_bytes": int(total_bytes / n),
        "total_kb": round(total_bytes / 1024, 1),
        "total_mb": round(total_bytes / (1024 * 1024), 3),
    }

    # ── Buckets par tranche de taille ────────────────────────────────────────
    buckets = {"<1KB": 0, "1-10KB": 0, "10-100KB": 0, "100KB-1MB": 0, ">1MB": 0}
    for s in all_sizes:
        if s < 1_024:               buckets["<1KB"] += 1
        elif s < 10_240:            buckets["1-10KB"] += 1
        elif s < 102_400:           buckets["10-100KB"] += 1
        elif s < 1_048_576:         buckets["100KB-1MB"] += 1
        else:                       buckets[">1MB"] += 1

    # ── Tokenomics — impact coins ────────────────────────────────────────────
    from src.artcb.tokenomics import (
        EMISSION_MODEL,
        SATOSHI_PER_ARTCB,
        MAX_SUPPLY_ARTCB,
    )
    from src.artcb.economics.emission import issued_reward_satoshi, population_reward_artcb

    issued_so_far = total_reward_satoshi
    current_reward_satoshi = issued_reward_satoshi(
        len(raw_blocks),
        issued_so_far_satoshi=issued_so_far,
    )
    current_reward = current_reward_satoshi / SATOSHI_PER_ARTCB

    mined_artcb = total_reward_satoshi / SATOSHI_PER_ARTCB
    supply_max = MAX_SUPPLY_ARTCB
    mined_pct = mined_artcb / supply_max * 100

    tokenomics = {
        "supply_max_artcb": supply_max,
        "mined_artcb": round(mined_artcb, 8),
        "mined_pct": round(mined_pct, 6),
        "remaining_artcb": round(supply_max - mined_artcb, 8),
        "emission_model": EMISSION_MODEL,
        "halving_removed": True,
        "current_epoch_fixe": None,
        "current_epoch_dynamique": None,
        "current_epoch_total": None,
        "current_reward_artcb": round(current_reward, 8),
        "r_h_artcb": round(population_reward_artcb(0), 8),
        "next_halving_at_block": None,
        "blocks_until_halving": None,
        "halving_interval": None,
        "max_halvings": None,
        "size_does_NOT_affect_reward": True,
        "reward_formula": "min(R(H), remaining_21M)  [D-024 geopopulation, no 210k schedule]",
        "what_affects_reward": [
            "verified_humans R(H)",
            "remaining 21M hard cap",
            "contributors count (split du reward)",
            "pol_score (pondération du split entre contributors)",
        ],
        "what_does_NOT_affect_reward": [
            "block_index (plus de halving 210k)",
            "mining velocity extra_epochs",
            "block_size_bytes",
            "content volume",
            "visibility (private/public)",
            "graph complexity",
        ],
    }

    # ── Top N grands + petits ────────────────────────────────────────────────
    sorted_by_size = sorted(sizes, key=lambda x: x["size_bytes"], reverse=True)
    top_largest = sorted_by_size[:top_n]
    top_smallest = sorted_by_size[-top_n:]

    return {
        "block_count": n,
        "distribution": distribution,
        "buckets": buckets,
        "tokenomics": tokenomics,
        "top_largest": top_largest,
        "top_smallest": top_smallest,
        "note": (
            "block_size_bytes dans chaque bloc = taille réelle de la ligne JSONL en octets UTF-8. "
            "Les blocs antérieurs au Rapport 078 n'ont pas ce champ — taille recalculée à la volée."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# P7 — Webhooks sortants
# ─────────────────────────────────────────────────────────────────────────────

class WebhookRegisterRequest(BaseModel):
    url: str = Field(min_length=8, description="URL HTTPS de destination")
    label: str = Field(min_length=1, max_length=128)
    events: list[str] = Field(
        default=["block_stored"],
        description="Événements: block_stored | memo_stored | think_complete | all",
    )
    secret: str | None = Field(default=None, description="Secret HMAC optionnel (header X-ARTCB-Signature)")


@router_webhooks.post("/register", summary="Enregistrer un webhook sortant")
def register_webhook(
    body: WebhookRegisterRequest,
    request: Request,
    key_record: Annotated[dict | None, Depends(require_scope("write"))] = None,
) -> dict:
    """
    Enregistre une URL à appeler à chaque événement blockchain.
    Cursor/Bob peut s'abonner pour être notifié en temps réel de chaque nouveau bloc.
    """
    path = _webhooks_path(request)
    hooks = _load_webhooks(path)

    hook_id = "wh_" + secrets.token_hex(8)
    hook = {
        "hook_id": hook_id,
        "url": body.url,
        "label": body.label,
        "events": body.events if "all" not in body.events else ["block_stored", "memo_stored", "think_complete"],
        "secret": body.secret,
        "created_at": time.time(),
        "active": True,
        "registered_by": key_record["key_id"] if key_record else "anonymous",
    }
    hooks.append(hook)
    _save_webhooks(path, hooks)
    logger.info("Webhook registered: %s → %s", hook_id, body.url)

    return {
        "hook_id": hook_id,
        "url": body.url,
        "label": body.label,
        "events": hook["events"],
        "active": True,
        "message": f"Webhook {hook_id} actif — ARTCB appellera {body.url} à chaque événement",
    }


@router_webhooks.get("/list", summary="Lister les webhooks actifs")
def list_webhooks(
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    path = _webhooks_path(request)
    hooks = _load_webhooks(path)
    safe = [
        {
            "hook_id": h["hook_id"],
            "url": h["url"],
            "label": h["label"],
            "events": h.get("events", []),
            "active": h.get("active", True),
            "created_at": h.get("created_at"),
        }
        for h in hooks
    ]
    return {"webhooks": safe, "count": len(safe)}


@router_webhooks.delete("/{hook_id}", summary="Révoquer un webhook")
def delete_webhook(
    hook_id: str,
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    path = _webhooks_path(request)
    hooks = _load_webhooks(path)
    for h in hooks:
        if h["hook_id"] == hook_id:
            h["active"] = False
            _save_webhooks(path, hooks)
            return {"revoked": True, "hook_id": hook_id}
    raise HTTPException(status_code=404, detail=f"Webhook {hook_id} introuvable")


# ─────────────────────────────────────────────────────────────────────────────
# P8 (bonus) — GET /api/v1/ai/memory — liste des memos gravés
# ─────────────────────────────────────────────────────────────────────────────

@router_ai.get("/memory", summary="Liste des observations IA gravées dans la chaîne")
def ai_memory(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    memo_type: str | None = Query(default=None),
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """Retrouve tous les blocs créés par ai/memo ou ai/think."""
    state = _state(request)
    memos = []
    try:
        for b in reversed(state.chain.list_blocks()):
            ps = b.get("public_symbols") or {}
            src = ps.get("learning_source", "")
            gid = b.get("graph_id", "")
            if not src.startswith("ai:"):
                # Vérifie aussi via graph_id préfixe ai_memo_
                if not gid.startswith("ai_memo_") and not gid.startswith("ai_think_"):
                    continue
            if memo_type and ps.get("memo_type") != memo_type:
                continue
            h = b.get("hash", "")
            memos.append({
                "block_index": b.get("index"),
                "block_hash": h[:16] + "…" if len(h) >= 16 else h,
                "graph_id": gid,
                "timestamp": b.get("timestamp"),
                "pol_score": b.get("pol_score"),
                "memo_type": ps.get("memo_type", "unknown"),
                "agent_id": ps.get("agent_id", "unknown"),
                "session_id": ps.get("session_id", ""),
                "tags": ps.get("tags", "").split(",") if ps.get("tags") else [],
                "source": src,
            })
            if len(memos) >= limit:
                break
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"memos": memos, "count": len(memos)}


# ─────────────────────────────────────────────────────────────────────────────
# P0-1 — GET /api/v1/ai/context — contexte inter-sessions prêt à injecter
# ─────────────────────────────────────────────────────────────────────────────

@router_ai.get("/context", summary="Contexte inter-sessions prêt à injecter dans un prompt LLM")
def ai_context(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50, description="Nombre de memos récents à inclure"),
    session_id: str | None = Query(default=None, description="Filtrer par session"),
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    Retourne un bloc de contexte prêt à injecter dans le system prompt d'un LLM.
    Agrège : memos récents, bugs ouverts, dernière décision, hauteur chaîne.
    Permet à Bob/Cursor de reprendre exactement là où il s'était arrêté.
    """
    state = _state(request)
    agent_id = key_record["label"] if key_record else None

    # Lire tous les blocs IA
    all_memos: list[dict] = []
    try:
        for b in reversed(state.chain.list_blocks()):
            ps = b.get("public_symbols") or {}
            src = ps.get("learning_source", "")
            gid = b.get("graph_id", "")
            if not src.startswith("ai:") and not gid.startswith("ai_memo_") and not gid.startswith("ai_think_"):
                continue
            if session_id and ps.get("session_id") != session_id:
                continue
            h = b.get("hash", "")
            all_memos.append({
                "block_index": b.get("index"),
                "block_hash": h[:16] + "…" if len(h) >= 16 else h,
                "graph_id": gid,
                "timestamp": b.get("timestamp"),
                "pol_score": b.get("pol_score"),
                "memo_type": ps.get("memo_type", "unknown"),
                "agent_id": ps.get("agent_id", "unknown"),
                "session_id": ps.get("session_id", ""),
                "tags": ps.get("tags", "").split(",") if ps.get("tags") else [],
                "content_preview": "",  # pas de décodage IR ici pour perf
                "parent_block_index": ps.get("parent_block_index"),
                "source": src,
            })
    except Exception as exc:
        logger.error("ai/context read memos error: %s", exc)

    # Bugs ouverts = type=bug sans enfant type=fix lié
    all_bug_indices = {
        m["block_index"]
        for m in all_memos if m["memo_type"] == "bug"
    }
    fixed_parents = {
        m["parent_block_index"]
        for m in all_memos
        if m["memo_type"] == "fix" and m["parent_block_index"] is not None
    }
    open_bugs = [m for m in all_memos if m["block_index"] in (all_bug_indices - fixed_parents)]

    # Dernières décisions
    last_decisions = [m for m in all_memos if m["memo_type"] == "decision"][:3]

    # Derniers memos récents
    recent_memos = all_memos[:limit]

    # Hauteur chaîne
    try:
        chain_height = len(state.chain.list_blocks())
    except Exception:
        chain_height = 0

    # Construire le prompt_ready
    lines = [
        f"## Contexte ARTCB — {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"Agent: {agent_id or 'anonymous'}",
        f"Chaîne: {chain_height} blocs | {len(all_memos)} memos IA gravés",
        "",
    ]
    if open_bugs:
        lines.append(f"### Bugs ouverts ({len(open_bugs)})")
        for b in open_bugs[:5]:
            lines.append(f"- [bug #{b['block_index']}] {b['agent_id']} — {b['timestamp']}")
        lines.append("")
    if last_decisions:
        lines.append("### Dernières décisions")
        for d in last_decisions:
            lines.append(f"- [décision #{d['block_index']}] {d['agent_id']} — {d['timestamp']}")
        lines.append("")
    if recent_memos:
        lines.append(f"### {len(recent_memos)} derniers memos")
        for m in recent_memos[:5]:
            lines.append(f"- [{m['memo_type']} #{m['block_index']}] agent={m['agent_id']} tags={m['tags']}")
    lines.append("")
    lines.append("Reprends le travail depuis ce contexte.")

    return {
        "prompt_ready": "\n".join(lines),
        "agent_id": agent_id,
        "chain_height": chain_height,
        "total_ai_memos": len(all_memos),
        "recent_memos": recent_memos,
        "open_bugs": open_bugs,
        "last_decisions": last_decisions,
        "session_filter": session_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# P1-1b — GET /api/v1/ai/bugs/open — bugs sans fix lié
# ─────────────────────────────────────────────────────────────────────────────

@router_ai.get("/bugs/open", summary="Liste les bugs IA ouverts (sans fix lié)")
def ai_bugs_open(
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """Retourne tous les memos type=bug sans mémo type=fix lié via parent_block_index."""
    state = _state(request)
    bugs: list[dict] = []
    fixes_parents: set = set()
    try:
        blocks = state.chain.list_blocks()
        for b in blocks:
            ps = b.get("public_symbols") or {}
            if ps.get("memo_type") == "fix" and ps.get("parent_block_index"):
                try:
                    fixes_parents.add(int(ps["parent_block_index"]))
                except (ValueError, TypeError):
                    pass
        for b in reversed(blocks):
            ps = b.get("public_symbols") or {}
            if ps.get("memo_type") != "bug":
                continue
            idx = b.get("index")
            if idx in fixes_parents:
                continue
            h = b.get("hash", "")
            bugs.append({
                "block_index": idx,
                "block_hash": h[:16] + "…" if len(h) >= 16 else h,
                "graph_id": b.get("graph_id"),
                "timestamp": b.get("timestamp"),
                "agent_id": ps.get("agent_id", "unknown"),
                "session_id": ps.get("session_id", ""),
                "tags": ps.get("tags", "").split(",") if ps.get("tags") else [],
            })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"open_bugs": bugs, "count": len(bugs)}


# ─────────────────────────────────────────────────────────────────────────────
# P1-1c — GET /api/v1/ai/memo/{block_index}/children — enfants d'un bloc
# ─────────────────────────────────────────────────────────────────────────────

@router_ai.get("/memo/{block_index}/children", summary="Blocs enfants (fixes, réponses) d'un mémo")
def ai_memo_children(
    block_index: int,
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """Retourne tous les blocs qui référencent ce bloc via parent_block_index."""
    state = _state(request)
    children: list[dict] = []
    try:
        for b in state.chain.list_blocks():
            ps = b.get("public_symbols") or {}
            parent = ps.get("parent_block_index")
            if parent is None:
                continue
            try:
                if int(parent) == block_index:
                    h = b.get("hash", "")
                    children.append({
                        "block_index": b.get("index"),
                        "block_hash": h[:16] + "…" if len(h) >= 16 else h,
                        "memo_type": ps.get("memo_type", "unknown"),
                        "agent_id": ps.get("agent_id", "unknown"),
                        "timestamp": b.get("timestamp"),
                        "tags": ps.get("tags", "").split(",") if ps.get("tags") else [],
                    })
            except (ValueError, TypeError):
                pass
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"parent_block_index": block_index, "children": children, "count": len(children)}


# ─────────────────────────────────────────────────────────────────────────────
# P1-2 — GET /api/v1/ai/memo/{block_index} — contenu texte décodé
# ─────────────────────────────────────────────────────────────────────────────

@router_ai.get("/memo/{block_index}", summary="Lire le contenu texte décodé d'un mémo IA")
def ai_memo_read(
    block_index: int,
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> dict:
    """
    Retourne le bloc + son contenu textuel reconstitué depuis le graphe IR.
    Permet à l'agent de relire exactement ce qu'il avait gravé.
    """
    state = _state(request)
    target = None
    try:
        for b in state.chain.list_blocks():
            if b.get("index") == block_index:
                target = b
                break
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if target is None:
        raise HTTPException(status_code=404, detail=f"Bloc #{block_index} introuvable")

    ps = target.get("public_symbols") or {}
    gid = target.get("graph_id", "")

    # Tenter de décoder le graphe IR en texte
    content_text = None
    try:
        graph = state.get_graph(gid)
        if graph and graph.nodes:
            from src.artcb.ir.decoder import IRDecoder
            decoded = IRDecoder().decode(graph)
            content_text = decoded if isinstance(decoded, str) else str(decoded)
    except Exception as exc:
        logger.debug("ai/memo/%d decode error: %s", block_index, exc)
        content_text = None

    # Fallback : reconstituer depuis les nodes du graphe (labels)
    if not content_text:
        try:
            graph = state.get_graph(gid)
            if graph and graph.nodes:
                content_text = " | ".join(
                    n.label for n in graph.nodes if hasattr(n, "label") and n.label
                )[:2000]
        except Exception:
            content_text = None

    h = target.get("hash", "")
    return {
        "block_index": block_index,
        "block_hash": h[:16] + "…" if len(h) >= 16 else h,
        "graph_id": gid,
        "timestamp": target.get("timestamp"),
        "pol_score": target.get("pol_score"),
        "visibility": target.get("visibility"),
        "memo_type": ps.get("memo_type", "unknown"),
        "agent_id": ps.get("agent_id", "unknown"),
        "session_id": ps.get("session_id", ""),
        "tags": ps.get("tags", "").split(",") if ps.get("tags") else [],
        "parent_block_index": ps.get("parent_block_index"),
        "content_text": content_text,
        "content_available": content_text is not None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# P1-3 — GET /api/v1/ai/events — SSE push nouveaux blocs
# ─────────────────────────────────────────────────────────────────────────────

from fastapi.responses import StreamingResponse


@router_ai.get("/events", summary="SSE — notifications temps réel des nouveaux blocs IA")
def ai_events_sse(
    request: Request,
    key_record: Annotated[dict | None, Depends(verify_api_key)] = None,
) -> StreamingResponse:
    """
    Server-Sent Events : envoie un événement JSON à chaque poll (toutes les 2s).
    Compatible Cursor IDE, VSCode, navigateur nativement.

    Format : data: {"event":"heartbeat","chain_height":N,"timestamp":T}
    """
    state = _state(request)

    def _event_generator():
        last_height = 0
        # Heartbeat immédiat au démarrage — permet au client de confirmer l'ouverture
        try:
            blocks = state.chain.list_blocks()
            last_height = len(blocks)
        except Exception:
            last_height = 0
        hb0 = json.dumps({"event": "connected", "chain_height": last_height, "timestamp": time.time()})
        yield f"data: {hb0}\n\n"

        try:
            for _ in range(150):  # max 5 minutes (150 × 2s)
                import time as _time
                _time.sleep(2)
                try:
                    blocks = state.chain.list_blocks()
                    height = len(blocks)
                    if height != last_height:
                        # Nouveau bloc détecté
                        last_block = blocks[-1] if blocks else {}
                        ps = last_block.get("public_symbols") or {}
                        payload = json.dumps({
                            "event": "new_block",
                            "chain_height": height,
                            "block_index": last_block.get("index"),
                            "block_hash": (last_block.get("hash") or "")[:16],
                            "memo_type": ps.get("memo_type"),
                            "agent_id": ps.get("agent_id"),
                            "timestamp": time.time(),
                        }, ensure_ascii=False)
                        yield f"data: {payload}\n\n"
                        last_height = height
                    else:
                        # Heartbeat
                        hb = json.dumps({"event": "heartbeat", "chain_height": height, "timestamp": time.time()})
                        yield f"data: {hb}\n\n"
                except Exception as exc:
                    err = json.dumps({"event": "error", "message": str(exc)})
                    yield f"data: {err}\n\n"
        except GeneratorExit:
            pass

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
