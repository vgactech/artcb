"""
ARTCB Python SDK — Client officiel
===================================
Usage minimal :

    from artcb_sdk import ArtcbClient

    client = ArtcbClient("http://localhost:8000", api_key="artcb_xxx")

    # Graver une pensée
    bloc = client.memo("J'ai trouvé que X implique Y", memo_type="decision")
    print(f"Gravé en bloc #{bloc['block_index']}, PoL={bloc['pol_score']}")

    # Poser une question
    rep = client.think("Comment corriger le bug de compression ?")
    print(rep["answer"])

    # Chercher dans la mémoire
    results = client.search("compression graphe")
    for r in results:
        print(r["text"], r["score"])

    # Vérifier la chaîne
    status = client.verify()
    print(status["valid"], status["block_count"])

Compatible Python 3.10+ — dépendances : httpx (déjà dans requirements.txt)
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    import urllib.request, urllib.error  # type: ignore[no-redef]
    _HAS_HTTPX = False


class ArtcbError(Exception):
    """Erreur SDK ARTCB."""


class ArtcbClient:
    """
    Client Python officiel pour l'API ARTCB.

    Paramètres :
        base_url  : URL de l'API (ex: "http://localhost:8000")
        api_key   : Token Bearer artcb_xxx (optionnel pour lecture)
        timeout   : Timeout HTTP en secondes (défaut 30)
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        if base_url is None:
            base_url = (
                os.environ.get("ARTCB_API_URL")
                or os.environ.get("ARTCB_NODE_URL")
                or "http://localhost:8000"
            )
        self.base_url = str(base_url).rstrip("/")
        self.api_key = (
            api_key
            or os.environ.get("ARTCB_API_KEY")
            or os.environ.get("ARTCB_NODE_API_KEY")
        )
        self.timeout = timeout

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{qs}"
        if _HAS_HTTPX:
            r = httpx.get(url, headers=self._headers(), timeout=self.timeout)
            if r.status_code >= 400:
                raise ArtcbError(f"GET {path} → HTTP {r.status_code}: {r.text[:200]}")
            return r.json()
        else:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())

    def _post(self, path: str, body: dict) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode()
        if _HAS_HTTPX:
            r = httpx.post(url, content=data, headers=self._headers(), timeout=self.timeout)
            if r.status_code >= 400:
                raise ArtcbError(f"POST {path} → HTTP {r.status_code}: {r.text[:200]}")
            return r.json()
        else:
            req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())

    def _delete(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        if _HAS_HTTPX:
            r = httpx.delete(url, headers=self._headers(), timeout=self.timeout)
            if r.status_code >= 400:
                raise ArtcbError(f"DELETE {path} → HTTP {r.status_code}: {r.text[:200]}")
            return r.json()
        else:
            req = urllib.request.Request(url, headers=self._headers(), method="DELETE")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())

    # ── Santé ──────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """Vérifier que l'API est en ligne."""
        return self._get("/health")

    # ── Blockchain ────────────────────────────────────────────────────────────

    def verify(self) -> dict:
        """
        Vérifier l'intégrité de toute la chaîne.

        Retourne : {"valid": bool, "block_count": int, "pqc_algorithm": str}
        """
        return self._get("/api/v1/chain/verify")

    def chain(self, limit: int = 20, visibility: str = "private") -> list[dict]:
        """Lister les derniers blocs."""
        return self._get("/api/v1/chain", {"limit": limit, "visibility": visibility})

    def block(self, index: int) -> dict:
        """Détails d'un bloc par son index."""
        return self._get(f"/api/v1/chain/block/{index}")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Recherche sémantique dans tous les blocs.

        Retourne une liste de résultats avec score de pertinence.
        """
        resp = self._get("/api/v1/chain/search", {"q": query, "limit": limit})
        return resp.get("results", resp) if isinstance(resp, dict) else resp

    # ── Mémoire IA ─────────────────────────────────────────────────────────────

    def memo(
        self,
        content: str,
        *,
        title: str = "",
        memo_type: str = "observation",
        tags: list[str] | None = None,
        agent_id: str = "artcb_sdk",
        parent_block_index: int | None = None,
    ) -> dict:
        """
        Graver une observation / décision / bug dans la blockchain.

        memo_type : "observation" | "decision" | "bug" | "fix" | "qa_result"

        Retourne : {"block_index": int, "pol_score": float, "hash": str, ...}
        """
        body: dict = {
            "title": title or content[:80],
            "content": content,
            "memo_type": memo_type,
            "tags": tags or ["artcb_sdk"],
            "agent_id": agent_id,
        }
        if parent_block_index is not None:
            body["parent_block_index"] = parent_block_index
        return self._post("/api/v1/ai/memo", body)

    def think(
        self,
        question: str,
        *,
        agent_id: str = "artcb_sdk",
        inject_context: bool = True,
        use_llm: bool = False,
        llm_provider: str | None = None,
    ) -> dict:
        """
        Poser une question à la blockchain — Explorer + Critic répondent.

        La réponse ET le raisonnement sont gravés dans un nouveau bloc.
        Retourne : {"answer": str, "block_index": int, "pol_score": float, ...}
        """
        body: dict = {
            "question": question,
            "agent_id": agent_id,
            "inject_context": inject_context,
            "use_llm": use_llm,
        }
        if llm_provider:
            body["llm_provider"] = llm_provider
        return self._post("/api/v1/ai/think", body)

    def ai_status(self) -> dict:
        """Snapshot complet de l'état IA (memos récents, bugs ouverts, hauteur chaîne)."""
        return self._get("/api/v1/ai/status")

    # ── Wallets ────────────────────────────────────────────────────────────────

    def wallets(self) -> list[dict]:
        """Lister tous les wallets."""
        # P1-1 FIX: route singulier /wallet/list (était /wallets pluriel)
        return self._get("/api/v1/wallet/list")

    def create_wallet(self, name: str) -> dict:
        """Créer un nouveau wallet."""
        # P1-1 FIX: route singulier /wallet/create (était /wallets pluriel)
        return self._post("/api/v1/wallet/create", {"name": name})

    def balance(self, address: str) -> dict:
        """Solde d'un wallet."""
        # P1-1 FIX: route singulier /wallet/balance/{address}
        return self._get(f"/api/v1/wallet/balance/{address}")

    # ── Clés API ───────────────────────────────────────────────────────────────

    def create_api_key(
        self,
        label: str,
        scopes: list[str] | None = None,
        expires_days: int | None = None,
    ) -> dict:
        """
        Générer une clé API Bearer.

        ⚠️  Le token est retourné UNE SEULE FOIS — le conserver immédiatement.
        """
        body: dict = {"label": label, "scopes": scopes or ["read", "write"]}
        if expires_days:
            body["expires_days"] = expires_days
        return self._post("/api/v1/api-keys/generate", body)

    def list_api_keys(self) -> list[dict]:
        """Lister les clés API (tokens masqués)."""
        resp = self._get("/api/v1/api-keys/list")
        return resp.get("keys", [])

    def revoke_api_key(self, key_id: str) -> dict:
        """Révoquer une clé par son key_id."""
        return self._delete(f"/api/v1/api-keys/{key_id}")

    # ── Smart contracts IR v0.2 ────────────────────────────────────────────────

    def create_rule(self, rule_text: str) -> dict:
        """
        Créer un smart contract PoL en langage naturel.

        Exemple : "SI pol_score > 0.9 ALORS reward_bonus = 0.5 ARTCB"
        """
        return self._post("/api/v1/ir/rules", {"rule_text": rule_text})

    def list_rules(self) -> list[dict]:
        """Lister les smart contracts actifs."""
        resp = self._get("/api/v1/ir/rules")
        return resp.get("rules", [])

    def evaluate_rule(self, rule_id: str, context: dict) -> dict:
        """Évaluer un smart contract contre un contexte."""
        return self._post(f"/api/v1/ir/rules/{rule_id}/evaluate", {"context": context})

    # ── NFT PoL ────────────────────────────────────────────────────────────────

    def mint_nft(
        self,
        title: str,
        content: str,
        owner: str,
        *,
        description: str = "",
        rights: str = "all-rights-reserved",
    ) -> dict:
        """
        Créer un NFT sémantique gravé dans la blockchain.

        Le contenu est INTÉGRÉ dans la chaîne (pas un lien externe).
        """
        return self._post("/api/v1/pol/nft/mint", {
            "title": title,
            "content": content,
            "owner": owner,
            "description": description,
            "rights": rights,
        })

    def list_nfts(self, owner: str | None = None) -> list[dict]:
        """Lister les NFT (filtrable par propriétaire)."""
        params = {"owner": owner} if owner else {}
        resp = self._get("/api/v1/pol/nft/list", params or None)
        return resp.get("nfts", []) if isinstance(resp, dict) else resp

    # ── Transfers PoL ──────────────────────────────────────────────────────────

    def transfer(
        self,
        from_address: str,
        to_address: str,
        amount: float,
        *,
        memo: str = "",
    ) -> dict:
        """
        Transférer des ARTCB avec preuve sémantique gravée dans la chaîne.
        """
        return self._post("/api/v1/pol/transfer", {
            "from_address": from_address,
            "to_address": to_address,
            "amount_artcb": amount,
            "memo": memo,
        })

    # ── Mémorisation ──────────────────────────────────────────────────────────

    def memorize(
        self,
        text: str,
        *,
        visibility: str = "private",
        use_llm: bool = False,
        wallet_address: str | None = None,
    ) -> dict:
        """
        Mémoriser un texte → IRGraph → bloc miné automatiquement.

        Retourne : {"graph_id": str, "pol_score": float, "block_index": int}
        """
        body: dict = {
            "text": text,
            "visibility": visibility,
            "use_llm": use_llm,
        }
        if wallet_address:
            body["actor_address"] = wallet_address
        return self._post("/api/v1/store", body)

    # ── Webhooks ───────────────────────────────────────────────────────────────

    def register_webhook(self, url: str, events: list[str] | None = None) -> dict:
        """S'abonner aux événements blockchain via webhook HTTP."""
        return self._post("/api/v1/webhooks/register", {
            "url": url,
            "events": events or ["new_block"],
        })

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "ArtcbClient":
        return self

    def __exit__(self, *_: Any) -> None:
        pass

    def __repr__(self) -> str:
        return f"ArtcbClient(base_url={self.base_url!r}, authenticated={bool(self.api_key)})"


# ── Convenience factory ────────────────────────────────────────────────────────

def connect(
    base_url: str | None = None,
    api_key: str | None = None,
) -> ArtcbClient:
    """
    Crée un client ARTCB et vérifie la connexion.

    Lève ArtcbError si l'API n'est pas joignable.
    """
    client = ArtcbClient(base_url, api_key)
    try:
        h = client.health()
        if h.get("status") != "healthy":
            raise ArtcbError(f"API non saine : {h}")
    except Exception as e:
        raise ArtcbError(f"Impossible de joindre {base_url} : {e}") from e
    return client
