"""Définition et exécution des outils MCP ARTCB.

7 outils enregistrés :
    artcb_memo          — graver une pensée dans la blockchain
    artcb_think         — IA raisonne + grave le résultat
    artcb_search        — recherche sémantique dans les blocs
    artcb_mine          — pipeline minage complet (texte → IR → bloc)
    artcb_chain_verify  — vérifier l'intégrité de la chaîne
    artcb_wallet_balance — solde d'un wallet ARTCB
    artcb_bridge_import — importer une transaction d'une blockchain externe
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger("artcb.mcp.tools")


# ---------------------------------------------------------------------------
# Schémas JSON (liste retournée à tools/list)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "artcb_memo",
        "description": (
            "Grave une pensée, une décision ou une information dans la blockchain ARTCB "
            "de façon immuable. Chaque bloc est signé ML-DSA-65 (post-quantique) et reçoit "
            "un score PoL (Proof of Learning). Retourne le numéro de bloc et le score PoL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texte à graver (max 10 000 chars)"},
                "memo_type": {
                    "type": "string",
                    "enum": ["decision", "observation", "bug", "fix", "analysis", "benchmark", "qa_result"],
                    "default": "observation",
                    "description": "Type de mémo",
                },
                "visibility": {
                    "type": "string",
                    "enum": ["private", "public"],
                    "default": "private",
                    "description": "Visibilité du bloc (private = local uniquement)",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "artcb_think",
        "description": (
            "Pose une question à l'agent IA ARTCB. L'IA raisonne en utilisant la mémoire "
            "de la blockchain et grave la réponse dans un nouveau bloc. "
            "Retourne la réponse et le bloc gravé."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Question à poser à l'agent IA"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "artcb_search",
        "description": (
            "Recherche sémantique dans tous les blocs de la blockchain ARTCB. "
            "Retourne les blocs les plus pertinents avec leurs scores de similarité."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Requête de recherche"},
                "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "artcb_mine",
        "description": (
            "Lance le pipeline de minage complet : encode le texte en IR PoL, "
            "calcule le score Proof of Learning, signe avec ML-DSA-65 et grave dans la chaîne. "
            "Plus riche que artcb_memo — inclut la décomposition IR complète."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texte à miner"},
                "visibility": {"type": "string", "enum": ["private", "public"], "default": "private"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "artcb_chain_verify",
        "description": (
            "Vérifie l'intégrité complète de la blockchain ARTCB. "
            "Retourne le nombre de blocs, la validité, et l'algorithme de signature."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "artcb_wallet_balance",
        "description": "Retourne le solde ARTCB d'une adresse wallet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Adresse wallet ARTCB (artcb1...)"},
            },
            "required": ["address"],
        },
    },
    {
        "name": "artcb_bridge_import",
        "description": (
            "Importe une transaction d'une blockchain externe (Ethereum, Bitcoin, Solana…) "
            "dans ARTCB. La transaction est encodée en IR PoL et gravée de façon immuable."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "chain": {
                    "type": "string",
                    "enum": ["ethereum", "bitcoin", "solana", "bnb", "polygon", "avalanche"],
                    "description": "Blockchain source",
                },
                "tx_hash": {"type": "string", "description": "Hash de la transaction source"},
                "description": {"type": "string", "description": "Description optionnelle"},
            },
            "required": ["chain", "tx_hash"],
        },
    },
]


# ---------------------------------------------------------------------------
# Exécution des outils
# ---------------------------------------------------------------------------

def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = (os.environ.get("ARTCB_API_KEY") or os.environ.get("ARTCB_NODE_API_KEY") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _api_post(url: str, data: dict[str, Any]) -> dict[str, Any]:
    """HTTP POST vers l'API ARTCB — utilise urllib (pas de dépendances supplémentaires)."""
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {detail[:200]}") from exc
    except Exception as exc:
        raise RuntimeError(f"API unreachable: {exc}") from exc


def _api_get(url: str) -> dict[str, Any] | list:
    """HTTP GET vers l'API ARTCB."""
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"API HTTP {exc.code}: {detail[:200]}") from exc
    except Exception as exc:
        raise RuntimeError(f"API unreachable: {exc}") from exc


def _text_content(text: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": text}]


def execute_tool(name: str, arguments: dict[str, Any], *, api_url: str) -> list[dict[str, Any]]:
    """Exécute un outil MCP et retourne le contenu MCP."""
    try:
        if name == "artcb_memo":
            return _tool_memo(arguments, api_url)
        elif name == "artcb_think":
            return _tool_think(arguments, api_url)
        elif name == "artcb_search":
            return _tool_search(arguments, api_url)
        elif name == "artcb_mine":
            return _tool_mine(arguments, api_url)
        elif name == "artcb_chain_verify":
            return _tool_chain_verify(api_url)
        elif name == "artcb_wallet_balance":
            return _tool_wallet_balance(arguments, api_url)
        elif name == "artcb_bridge_import":
            return _tool_bridge_import(arguments, api_url)
        else:
            return _text_content(f"Outil inconnu : {name}")
    except Exception as exc:
        logger.exception("Tool %s error", name)
        return _text_content(f"Erreur outil {name} : {exc}")


def _tool_memo(args: dict, api_url: str) -> list[dict]:
    resp = _api_post(f"{api_url}/api/v1/ai/memo", {
        "text": args["text"],
        "memo_type": args.get("memo_type", "observation"),
        "visibility": args.get("visibility", "private"),
    })
    block_index = resp.get("block_index", "?")
    pol_score = resp.get("pol_score", "?")
    chain_hash = resp.get("block_hash", "")[:16]
    return _text_content(
        f"✅ Gravé en bloc #{block_index} | PoL={pol_score} | hash={chain_hash}… | "
        f"Immuable ML-DSA-65 post-quantique.\n"
        f"Message : {resp.get('message', '')}"
    )


def _tool_think(args: dict, api_url: str) -> list[dict]:
    resp = _api_post(f"{api_url}/api/v1/ai/think", {
        "question": args["question"],
    })
    answer = resp.get("answer", resp.get("text", str(resp)))
    block_index = resp.get("block_index")
    pol = resp.get("pol_score")
    suffix = f"\n\n[Gravé en bloc #{block_index}, PoL={pol}]" if block_index else ""
    return _text_content(f"{answer}{suffix}")


def _tool_search(args: dict, api_url: str) -> list[dict]:
    limit = args.get("limit", 5)
    try:
        import urllib.parse as _up
        q = _up.quote(args["query"])
    except Exception:
        q = args["query"].replace(" ", "+")
    result = _api_get(f"{api_url}/api/v1/chain/search?q={q}&limit={limit}")
    if isinstance(result, dict):
        items = result.get("results", result.get("blocks", []))
    else:
        items = result
    if not items:
        return _text_content(f"Aucun résultat pour : {args['query']}")
    lines = [f"🔍 {len(items)} résultat(s) pour « {args['query']} »:\n"]
    for i, item in enumerate(items[:limit], 1):
        text = item.get("text", item.get("source_text", ""))[:200]
        score = item.get("score", item.get("pol_score", "?"))
        block = item.get("block_index", item.get("index", "?"))
        lines.append(f"{i}. [Bloc #{block} | score={score}] {text}")
    return _text_content("\n".join(lines))


def _tool_mine(args: dict, api_url: str) -> list[dict]:
    resp = _api_post(f"{api_url}/api/v1/mining/pipeline", {
        "text": args["text"],
        "visibility": args.get("visibility", "private"),
        "private": args.get("visibility", "private") == "private",
    })
    block = resp.get("block_index", resp.get("block", {}).get("index", "?"))
    pol = resp.get("pol_score", "?")
    nodes = resp.get("graph", {}).get("node_count", "?")
    return _text_content(
        f"⛏️ Minage complet — Bloc #{block} | PoL={pol} | Nœuds IR={nodes}\n"
        f"Signé ML-DSA-65 + Ed25519 hybride. Immuable."
    )


def _tool_chain_verify(api_url: str) -> list[dict]:
    resp = _api_get(f"{api_url}/api/v1/chain/verify")
    valid = resp.get("valid", False)
    blocks = resp.get("block_count", "?")
    algo = resp.get("pqc_algorithm", "?")
    hybrid = resp.get("hybrid_signatures", False)
    icon = "✅" if valid else "❌"
    return _text_content(
        f"{icon} Chaîne ARTCB : valid={valid} | {blocks} blocs | "
        f"algo={algo} | hybrid_sig={hybrid}"
    )


def _tool_wallet_balance(args: dict, api_url: str) -> list[dict]:
    address = args["address"]
    resp = _api_get(f"{api_url}/api/v1/wallet/balance/{address}")
    balance = resp.get("balance_artcb", resp.get("balance", "?"))
    satoshi = resp.get("balance_satoshi", "?")
    return _text_content(
        f"💰 Wallet {address[:20]}…\n"
        f"Balance : {balance} ARTCB ({satoshi} satoshi)"
    )


def _tool_bridge_import(args: dict, api_url: str) -> list[dict]:
    resp = _api_post(f"{api_url}/api/v1/bridges/import", {
        "chain": args["chain"],
        "tx_hash": args["tx_hash"],
        "description": args.get("description", ""),
    })
    block = resp.get("block_index", "?")
    pol = resp.get("pol_score", "?")
    return _text_content(
        f"🌉 Bridge {args['chain'].upper()} → ARTCB\n"
        f"Tx {args['tx_hash'][:20]}… gravée en bloc #{block} | PoL={pol}\n"
        f"Encodage IR PoL + signature ML-DSA-65."
    )
