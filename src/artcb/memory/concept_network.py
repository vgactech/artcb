"""Client réseau du ConceptStore — R320 (2026-09-11T21:30:00Z).

Ce module donne à un agent le moyen d'aller chercher, **sur le réseau ARTCB**,
la définition binaire d'un ConceptID qu'il ne connaît pas encore.

C'est le maillon qui manquait à C2-D :

    A : learn_from_text → concept_ids → publish_bundle(...)      (écriture)
    A → B : ConceptPacket binaire (identifiants seulement)
    B : receive_packet(packet, resolver=HttpConceptResolver(...)) (lecture)

B n'a jamais vu le texte humain, et son store était vide au départ.
"""

from __future__ import annotations

import contextlib
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("artcb.memory.concept_network")

DEFAULT_TIMEOUT = 30
DEFAULT_FALLBACK_PEERS = (
    "https://artcb.me",
    "https://n2.artcb.me",
    "https://n3.artcb.me",
    "https://n4.artcb.me",
)


class HttpConceptResolver:
    """Résolveur appelable : ``resolver(missing_ids) -> bytes | None``.

    Interroge ``GET /api/v1/concepts/resolve`` et renvoie le bundle binaire
    ``ACBN``. Retourne ``None`` si le nœud ne connaît aucun de ces concepts —
    un « je ne sais pas » honnête, jamais une réponse inventée.

    R322 : si le nœud cible renvoie un bundle vide, bascule (client) sur les
    seeds publisher — C2-D multi-hôte même quand l'egress serveur est filtré.
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout: int = DEFAULT_TIMEOUT,
        federate_fallback: bool = True,
        fallback_peers: tuple[str, ...] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.federate_fallback = federate_fallback
        self.fallback_peers = fallback_peers or DEFAULT_FALLBACK_PEERS
        self.last_status: int | None = None
        self.last_missing: list[str] = []
        self.last_bundle_sha256: str | None = None
        self.last_federated_from: str | None = None

    def __call__(self, concept_ids: list[str]) -> bytes | None:
        if not concept_ids:
            return None
        url = f"{self.base_url}/api/v1/concepts/resolve?ids={','.join(concept_ids)}"
        headers = {"Accept": "application/octet-stream"}
        if len(self.api_key) >= 16:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        data: bytes | None = None
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self.last_status = resp.status
                missing = resp.headers.get("X-ARTCB-Concept-Missing", "")
                self.last_missing = [x for x in missing.split(",") if x]
                self.last_bundle_sha256 = resp.headers.get("X-ARTCB-Bundle-Sha256")
                data = resp.read()
        except urllib.error.HTTPError as exc:
            self.last_status = exc.code
            logger.warning("resolve HTTP %s sur %s", exc.code, self.base_url)
            data = None
        except Exception as exc:  # noqa: BLE001
            self.last_status = 0
            logger.warning("resolve échec transport : %s", type(exc).__name__)
            data = None
        if data is not None and len(data) > 10:
            return data
        # R322: if this node has an empty store, fall back to publisher seeds (client federation).
        if self.federate_fallback:
            for peer in self.fallback_peers:
                if peer.rstrip("/") == self.base_url.rstrip("/"):
                    continue
                alt = HttpConceptResolver(
                    peer,
                    api_key=self.api_key,
                    timeout=self.timeout,
                    federate_fallback=False,
                )
                got = alt(concept_ids)
                if got:
                    self.last_status = alt.last_status
                    self.last_bundle_sha256 = alt.last_bundle_sha256
                    self.last_missing = alt.last_missing
                    self.last_federated_from = peer
                    return got
        return None


def publish_bundle(
    base_url: str,
    bundle: bytes,
    *,
    api_key: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST ``/api/v1/concepts/publish`` avec le bundle binaire.

    Returns:
        Réponse JSON du nœud, ou ``{"error": ..., "http": code}`` si refus.
    """
    import json

    url = f"{base_url.rstrip('/')}/api/v1/concepts/publish"
    headers = {
        "Content-Type": "application/octet-stream",
        "Accept": "application/json",
    }
    key = (api_key or "").strip()
    if len(key) >= 16:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=bundle, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = ""
        with contextlib.suppress(Exception):
            body = exc.read().decode()[:400]
        return {"error": "http_error", "http": exc.code, "body": body}
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__, "http": 0}
