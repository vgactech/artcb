"""Découverte workers pool via pairs P2P."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
from typing import Any

import httpx

logger = logging.getLogger("artcb.pool.discovery")


def discover_workers(state: Any, owner_base_url: str) -> list[dict[str, str]]:
    identity = state.p2p_identity
    workers: list[dict[str, str]] = [{
        "node_id": identity.node_id,
        "kem_public_hex": identity.kem_public_key_hex,
        "base_url": owner_base_url.rstrip("/"),
    }]
    seen = {identity.node_id}
    for peer in state.p2p_peers.list_peers():
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.get(f"{peer.base_url}/api/v1/p2p/status")
                r.raise_for_status()
                body = r.json()
                nid = body["node_id"]
                if nid in seen:
                    continue
                workers.append({
                    "node_id": nid,
                    "kem_public_hex": body["kem_public_key_hex"],
                    "base_url": peer.base_url,
                })
                seen.add(nid)
        except Exception as exc:
            logger.warning("Pool worker discovery failed for %s: %s", peer.base_url, exc)
    return workers


def build_peer_urls(state: Any, owner_base_url: str, workers: list[dict[str, str]] | None = None) -> dict[str, str]:
    urls = {state.p2p_identity.node_id: owner_base_url.rstrip("/")}
    for w in workers or discover_workers(state, owner_base_url):
        if w.get("base_url"):
            urls[w["node_id"]] = w["base_url"].rstrip("/")
    return urls
