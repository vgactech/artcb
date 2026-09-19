"""Ressources MCP ARTCB — données passives lues automatiquement par les agents IA.

Schéma URI : artcb://<type>/<identifiant>

Ressources disponibles :
    artcb://chain/status          — état live de la chaîne
    artcb://chain/blocks/latest   — derniers blocs
    artcb://pol/score             — score PoL courant
    artcb://wallet/{address}      — info wallet
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger("artcb.mcp.resources")


RESOURCES: list[dict[str, Any]] = [
    {
        "uri": "artcb://chain/status",
        "name": "État de la chaîne ARTCB",
        "description": "Hauteur, PoL moyen, validité, algorithme de signature, dernier bloc.",
        "mimeType": "application/json",
    },
    {
        "uri": "artcb://chain/blocks/latest",
        "name": "Derniers blocs ARTCB",
        "description": "Les 5 derniers blocs gravés dans la blockchain.",
        "mimeType": "application/json",
    },
    {
        "uri": "artcb://pol/score",
        "name": "Score PoL courant",
        "description": "Score Proof of Learning actuel + état mining.",
        "mimeType": "application/json",
    },
    {
        "uri": "artcb://node/identity",
        "name": "Identité du nœud",
        "description": "node_id, clé publique KEM, ports API et P2P.",
        "mimeType": "application/json",
    },
]


def _api_get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"error": str(exc)}


def read_resource(uri: str, *, api_url: str) -> list[dict[str, Any]]:
    """Lit une ressource MCP et retourne une liste de contents."""
    try:
        if uri == "artcb://chain/status":
            data = _api_get(f"{api_url}/api/v1/ai/status")
            chain = data.get("chain", data)
            text = json.dumps({
                "height": chain.get("height"),
                "pol_avg": chain.get("pol_avg"),
                "last_block": chain.get("last_block"),
                "valid": True,
            }, ensure_ascii=False, indent=2)
        elif uri == "artcb://chain/blocks/latest":
            data = _api_get(f"{api_url}/api/v1/chain")
            blocks = data.get("blocks", []) if isinstance(data, dict) else data
            last5 = blocks[-5:] if len(blocks) >= 5 else blocks
            text = json.dumps([{
                "index": b.get("index"),
                "hash": b.get("hash", "")[:16] + "…",
                "pol_score": b.get("pol_score"),
                "timestamp": b.get("timestamp"),
                "visibility": b.get("visibility"),
            } for b in last5], ensure_ascii=False, indent=2)
        elif uri == "artcb://pol/score":
            data = _api_get(f"{api_url}/api/v1/dashboard/mining/status")
            text = json.dumps({
                "pol_score": data.get("pol_score"),
                "current_reward_artcb": data.get("current_reward_artcb"),
                "block_count": data.get("block_count"),
                "blocks_until_halving": data.get("blocks_until_halving"),
            }, ensure_ascii=False, indent=2)
        elif uri == "artcb://node/identity":
            data = _api_get(f"{api_url}/api/v1/p2p/status")
            text = json.dumps(data, ensure_ascii=False, indent=2)
        elif uri.startswith("artcb://wallet/"):
            address = uri.split("/")[-1]
            data = _api_get(f"{api_url}/api/v1/wallet/balance/{address}")
            text = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            text = json.dumps({"error": f"Ressource inconnue : {uri}"})

        return [{"uri": uri, "mimeType": "application/json", "text": text}]

    except Exception as exc:
        logger.exception("Resource read error uri=%s", uri)
        return [{"uri": uri, "mimeType": "text/plain", "text": f"Erreur : {exc}"}]
