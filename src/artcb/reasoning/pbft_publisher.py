"""PBFT Publisher — Gravure distribuée d'un REASONING_RECORD scellé (R356, 2026-09-17).

## Architecture R356 (audit rapport 372)

La distinction fondamentale que R356 doit prouver :

  R355 répond : « le serveur peut démontrer cryptographiquement ce qu'était
                  exactement le raisonnement terminé »

  R356 répond : « le RÉSEAU DISTRIBUÉ peut démontrer que ce final_hash précis
                  a été accepté définitivement par le consensus, indépendamment
                  du serveur qui l'a produit »

## Flux R356

  ReasoningRecord.final_hash (scellé)
        ↓
  _build_reasoning_block()     — construit le bloc public (dry_run)
        ↓
  _submit_to_primary()         — soumet via /pbft/client-request au primary
        ↓
  primary → PRE-PREPARE
        ↓
  replicas → PREPARE (Q=3 requis)
        ↓
  COMMIT
        ↓
  write_certified_block()
        ↓
  bloc public + finalité
        ↓
  PublishResult.block_index, block_hash

## Sécurité (audit R372 point 7-8)

Le bloc NE contient PAS le raisonnement brut (contexte privé potentiellement sensible).
Il contient uniquement :
  - final_hash (preuve cryptographique)
  - record_id (référence stable)
  - metadata minimale (session_id_hash, agent_id, ts_seal)
  - protocol_version R356

Les données privées restent dans data/trace/reasoning_records.jsonl.
Quiconque vérifie peut recalculer final_hash depuis le record privé et le comparer
au hash publié on-chain → preuve sans révéler le contenu.

## Scénarios gérés

  - Nœud primary mort        → timeout → PublishResult.error="primary_unreachable"
  - Double proposition       → 409 equivocation → PublishResult.error="equivocation"
  - Partition réseau (< Q)   → no_majority → PublishResult.error="no_quorum"
  - Record non scellé        → refus immédiat → PublishResult.error="record_not_sealed"
  - Record déjà publié       → PublishResult.already_published=True (idempotent)

HONNÊTETÉ : Ce module utilise des appels HTTP réels aux nœuds ARTCB.
En environnement de test (sans nœuds live), les appels échouent gracieusement.
CERTIFIED_100=false.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("artcb.reasoning.pbft_publisher")

# ─── Constantes ──────────────────────────────────────────────────────────────

R356_PROTOCOL_VERSION = "r356-reasoning-v1"
R356_GRAPH_PREFIX = "reasoning_"
R356_SOURCE = "reasoning:pbft:r356"
R356_VISIBILITY = "public"

# Timeout HTTP par requête (secondes)
_HTTP_TIMEOUT = 10.0

# Nœuds seeds officiels (sans OVH1 qui est bloqué)
_DEFAULT_SEEDS: list[dict[str, Any]] = [
    {"node_id": "ovh-node-2",  "base_url": "https://artcb.me"},
    {"node_id": "aws-node-3",  "base_url": "https://n3.artcb.me"},
    {"node_id": "ovh-node-4",  "base_url": "https://n4.artcb.me"},
]


# ─── Résultat ─────────────────────────────────────────────────────────────────


@dataclass
class PublishResult:
    """Résultat de la tentative de publication PBFT d'un REASONING_RECORD.

    ok=True signifie : le bloc a été accepté par Q≥3 nœuds et écrit on-chain.
    ok=False signifie : la publication a échoué (voir error).
    already_published=True : le record avait déjà un bloc associé (idempotent).
    """
    ok: bool
    record_id: str
    final_hash: str
    block_index: int | None = None
    block_hash: str = ""
    primary_node: str = ""
    prepared_count: int = 0
    quorum_required: int = 3
    already_published: bool = False
    error: str = ""
    error_detail: str = ""
    duration_ms: float = 0.0
    ts_ns: int = field(default_factory=time.time_ns)
    certified: bool = False    # CERTIFIED_100=false
    protocol_version: str = R356_PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "record_id": self.record_id,
            "final_hash": self.final_hash,
            "block_index": self.block_index,
            "block_hash": self.block_hash,
            "primary_node": self.primary_node,
            "prepared_count": self.prepared_count,
            "quorum_required": self.quorum_required,
            "already_published": self.already_published,
            "error": self.error,
            "error_detail": self.error_detail,
            "duration_ms": self.duration_ms,
            "ts_ns": self.ts_ns,
            "certified": self.certified,
            "protocol_version": self.protocol_version,
            "note": (
                "R356 — preuve distribuée PBFT du REASONING_RECORD. "
                "Le bloc contient uniquement final_hash (pas le raisonnement brut). "
                "CERTIFIED_100=false."
            ),
        }


# ─── Utilitaires HTTP ─────────────────────────────────────────────────────────


def _http_json(
    method: str,
    url: str,
    body: dict | None = None,
    *,
    timeout: float = _HTTP_TIMEOUT,
    api_key: str = "",
) -> tuple[int, dict[str, Any]]:
    """Appel HTTP JSON minimal (pas de dépendance requests/httpx).

    Retourne (status_code, response_dict).
    En cas d'erreur réseau : retourne (0, {"error": message}).
    """
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return code, json.loads(raw)
            except json.JSONDecodeError:
                return code, {"raw": raw[:500]}
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            detail = json.loads(raw).get("detail", raw[:200])
        except Exception:
            detail = str(exc)
        return exc.code, {"detail": detail, "error": f"http_{exc.code}"}
    except Exception as exc:
        return 0, {"error": str(exc)[:200]}


# ─── Construire le contenu public du bloc ────────────────────────────────────


def _build_block_payload(record_id: str, final_hash: str, *, session_id: str = "", agent_id: str = "") -> dict[str, Any]:
    """Construit les métadonnées minimales à inscrire on-chain.

    R356 / audit R372 point 9 :
      - Données privées (contexte, observations) → RESTENT dans le JSONL local
      - Données publiques (hash + références) → bloc on-chain
      Ce n'est pas le raisonnement complet, c'est sa PREUVE.
    """
    session_id_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16] if session_id else ""
    return {
        "protocol_version": R356_PROTOCOL_VERSION,
        "record_id": record_id,
        "final_hash": final_hash,
        "session_id_hash": session_id_hash,   # hash du session_id — pas le session_id brut
        "agent_id": agent_id,
        "published_at_ns": time.time_ns(),
    }


def _build_graph_id(record_id: str, final_hash: str) -> str:
    """Détermine un graph_id stable et unique pour ce record R356."""
    combined = hashlib.sha256(f"r356:{record_id}:{final_hash}".encode()).hexdigest()[:16]
    return f"{R356_GRAPH_PREFIX}{combined}"


# ─── PBFT Publisher ───────────────────────────────────────────────────────────


class ReasoningPbftPublisher:
    """Publie un REASONING_RECORD scellé via le consensus PBFT ARTCB.

    Usage :
        from src.artcb.reasoning.pbft_publisher import ReasoningPbftPublisher
        publisher = ReasoningPbftPublisher(api_url="https://artcb.me")
        result = publisher.publish(record)

    Le publisher est stateless — créer une instance par publication.
    CERTIFIED_100=false.
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        seeds: list[dict[str, Any]] | None = None,
        timeout: float = _HTTP_TIMEOUT,
    ) -> None:
        """
        Args:
            api_url:  URL du nœud primary à contacter (ex: https://artcb.me).
                      Si vide, utilise ARTCB_API_URL de l'env ou le premier seed.
            api_key:  Clé API Bearer. Si vide, utilise ARTCB_API_KEY de l'env.
            seeds:    Liste de nœuds alternatifs [{"node_id": ..., "base_url": ...}].
            timeout:  Timeout HTTP par requête.
        """
        self._api_url = (
            api_url
            or os.environ.get("ARTCB_API_URL", "")
            or (_DEFAULT_SEEDS[0]["base_url"] if _DEFAULT_SEEDS else "http://localhost:8001")
        ).rstrip("/")
        self._api_key = api_key or os.environ.get("ARTCB_API_KEY", "")
        self._seeds = seeds or _DEFAULT_SEEDS
        self._timeout = timeout

    # ── API publique ──────────────────────────────────────────────────────────

    def publish(self, record: Any) -> PublishResult:
        """Publie un REASONING_RECORD scellé via PBFT.

        Args:
            record: ReasoningRecord scellé (frozen=True, final_hash non vide).

        Returns:
            PublishResult — ok=True si le bloc est finalisé.

        Scénarios gérés :
          - Record non scellé → error=record_not_sealed
          - Déjà publié       → already_published=True
          - Primary mort      → error=primary_unreachable
          - Quorum < Q=3      → error=no_quorum
          - Equivocation      → error=equivocation
        """
        t0 = time.time_ns()

        # ── Vérifications préalables ──────────────────────────────────────────
        if not getattr(record, "frozen", False):
            return PublishResult(
                ok=False,
                record_id=getattr(record, "record_id", ""),
                final_hash="",
                error="record_not_sealed",
                error_detail=(
                    "Le ReasoningRecord doit être scellé (frozen=True) avant publication PBFT. "
                    "Appelez record.seal() d'abord."
                ),
                duration_ms=0.0,
            )

        record_id: str = record.record_id
        final_hash: str = record.final_hash
        session_id: str = getattr(record, "session_id", "")
        agent_id: str = getattr(record, "agent_id", "bob-ide")

        if not final_hash:
            return PublishResult(
                ok=False,
                record_id=record_id,
                final_hash="",
                error="missing_final_hash",
                error_detail="final_hash vide — le record semble mal scellé.",
                duration_ms=0.0,
            )

        # ── Vérifier si déjà publié (idempotence) ────────────────────────────
        graph_id = _build_graph_id(record_id, final_hash)
        already = self._check_already_published(graph_id)
        if already:
            dur = (time.time_ns() - t0) / 1_000_000
            logger.info("R356 already published: record_id=%s graph_id=%s", record_id[:12], graph_id)
            return PublishResult(
                ok=True,
                record_id=record_id,
                final_hash=final_hash,
                block_index=already.get("block_index"),
                block_hash=str(already.get("block_hash") or ""),
                already_published=True,
                duration_ms=dur,
                protocol_version=R356_PROTOCOL_VERSION,
            )

        # ── Récupérer le primary ──────────────────────────────────────────────
        primary_url, primary_node = self._get_primary()
        if not primary_url:
            dur = (time.time_ns() - t0) / 1_000_000
            return PublishResult(
                ok=False,
                record_id=record_id,
                final_hash=final_hash,
                error="primary_unreachable",
                error_detail="Impossible de déterminer le primary PBFT ou aucun nœud accessible.",
                duration_ms=dur,
            )

        # ── Construire le bloc (dry_run via append_block) ─────────────────────
        block_payload = _build_block_payload(record_id, final_hash, session_id=session_id, agent_id=agent_id)
        graph_root = hashlib.sha256(
            json.dumps(block_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        block = self._dry_run_block(primary_url, graph_id, graph_root)
        if block is None:
            dur = (time.time_ns() - t0) / 1_000_000
            return PublishResult(
                ok=False,
                record_id=record_id,
                final_hash=final_hash,
                primary_node=primary_node,
                error="block_construction_failed",
                error_detail="append_block(dry_run=True) a échoué — vérifier le primary.",
                duration_ms=dur,
            )

        # ── Injecter le final_hash dans les public_symbols du bloc ────────────
        block.setdefault("public_symbols", {})
        block["public_symbols"]["reasoning_record_id"] = record_id
        block["public_symbols"]["reasoning_final_hash"] = final_hash
        block["public_symbols"]["r356_protocol"] = R356_PROTOCOL_VERSION
        block["public_symbols"]["session_id_hash"] = hashlib.sha256(
            session_id.encode()
        ).hexdigest()[:16]

        # ── Soumettre via /pbft/client-request ───────────────────────────────
        code, resp = _http_json(
            "POST",
            f"{primary_url}/api/v1/consensus/pbft/client-request",
            {"block": block},
            timeout=self._timeout,
            api_key=self._api_key,
        )

        if code == 409:
            detail = str(resp.get("detail", ""))
            dur = (time.time_ns() - t0) / 1_000_000
            if "equivoc" in detail.lower():
                err = "equivocation"
            elif "not_primary" in detail.lower():
                err = "not_primary"
            else:
                err = f"rejected_409:{detail[:60]}"
            return PublishResult(
                ok=False,
                record_id=record_id,
                final_hash=final_hash,
                primary_node=primary_node,
                error=err,
                error_detail=detail,
                duration_ms=dur,
            )

        if code != 200 or not resp.get("ok"):
            dur = (time.time_ns() - t0) / 1_000_000
            return PublishResult(
                ok=False,
                record_id=record_id,
                final_hash=final_hash,
                primary_node=primary_node,
                error=f"client_request_failed_{code}",
                error_detail=str(resp)[:200],
                duration_ms=dur,
            )

        # ── Récupérer le pre_prepare + collecter PREPARE/COMMIT ───────────────
        pre_prepare = resp.get("pre_prepare", {})
        digest = pre_prepare.get("digest", "")
        view = int(pre_prepare.get("view", 0))
        seq = int(pre_prepare.get("seq", 0))

        prepared_count, commit_result = self._collect_quorum(
            primary_url=primary_url,
            block=block,
            digest=digest,
            view=view,
            seq=seq,
        )

        dur = (time.time_ns() - t0) / 1_000_000

        if not commit_result.get("ok"):
            err_reason = commit_result.get("reason", "quorum_failed")
            if "no_majority" in err_reason or prepared_count < 3:
                err = "no_quorum"
            else:
                err = err_reason
            return PublishResult(
                ok=False,
                record_id=record_id,
                final_hash=final_hash,
                primary_node=primary_node,
                prepared_count=prepared_count,
                quorum_required=3,
                error=err,
                error_detail=str(commit_result)[:300],
                duration_ms=dur,
            )

        # ── Succès ────────────────────────────────────────────────────────────
        written_block = commit_result.get("block") or block
        block_index = written_block.get("index")
        block_hash = str(written_block.get("hash") or "")

        logger.info(
            "R356 published: record_id=%s final_hash=%s block=%s/%s primary=%s dur=%.0fms",
            record_id[:12], final_hash[:12], block_index, block_hash[:12],
            primary_node, dur,
        )

        return PublishResult(
            ok=True,
            record_id=record_id,
            final_hash=final_hash,
            block_index=block_index,
            block_hash=block_hash,
            primary_node=primary_node,
            prepared_count=prepared_count,
            quorum_required=3,
            duration_ms=dur,
            protocol_version=R356_PROTOCOL_VERSION,
        )

    # ── Méthodes internes ─────────────────────────────────────────────────────

    def _get_primary(self) -> tuple[str, str]:
        """Retourne (primary_base_url, primary_node_id) depuis /pbft/view du premier nœud accessible."""
        for seed in self._seeds:
            base = seed.get("base_url", "").rstrip("/")
            if not base:
                continue
            code, resp = _http_json("GET", f"{base}/api/v1/consensus/pbft/view", timeout=5.0)
            if code == 200 and resp.get("primary"):
                primary_node = str(resp["primary"])
                # Trouver l'URL du primary dans les seeds
                for s in self._seeds:
                    if s.get("node_id") == primary_node:
                        return s["base_url"].rstrip("/"), primary_node
                # Primary pas dans les seeds connus — utiliser le nœud courant comme relay
                return base, primary_node
            # Nœud accessible mais pas primary info → continuer
        return "", ""

    def _check_already_published(self, graph_id: str) -> dict | None:
        """Vérifie si ce graph_id est déjà dans la chaîne publique.

        Retourne le bloc existant si trouvé, None sinon.
        """
        for seed in self._seeds:
            base = seed.get("base_url", "").rstrip("/")
            if not base:
                continue
            code, resp = _http_json(
                "GET", f"{base}/api/v1/chain/graph/{graph_id}", timeout=5.0
            )
            if code == 200 and resp.get("found"):
                return resp
        return None

    def _dry_run_block(
        self, primary_url: str, graph_id: str, graph_root: str
    ) -> dict | None:
        """Demande au primary de construire le bloc (dry_run) via /pbft/propose."""
        code, resp = _http_json(
            "POST",
            f"{primary_url}/api/v1/consensus/pbft/propose",
            {
                "graph_id": graph_id,
                "graph_root": graph_root,
                "visibility": R356_VISIBILITY,
                "source": R356_SOURCE,
            },
            timeout=self._timeout,
            api_key=self._api_key,
        )
        if code == 200 and resp.get("ok") and resp.get("block"):
            return resp["block"]
        logger.warning("_dry_run_block failed: code=%d resp=%s", code, str(resp)[:200])
        return None

    def _collect_quorum(
        self,
        *,
        primary_url: str,
        block: dict,
        digest: str,
        view: int,
        seq: int,
    ) -> tuple[int, dict[str, Any]]:
        """Collecte Q=3 PREPARE puis lance le COMMIT local.

        Retourne (prepared_count, commit_result).
        Commit_result contient ok=True si le bloc est écrit.
        """
        prepared_count = 0
        # Envoyer PREPARE à tous les seeds (y compris primary pour compter)
        for seed in self._seeds:
            base = seed.get("base_url", "").rstrip("/")
            if not base:
                continue
            code, resp = _http_json(
                "POST",
                f"{base}/api/v1/consensus/pbft/prepare",
                {"view": view, "seq": seq, "digest": digest},
                timeout=self._timeout,
            )
            if code == 200 and resp.get("result") in ("prepared", "ok", "accepted"):
                prepared_count += 1
            elif code == 200 and "seq" in resp:
                # Certains nœuds retournent le row sans "result" explicite
                prepared_count += 1

        if prepared_count < 3:
            return prepared_count, {
                "ok": False,
                "reason": "no_quorum",
                "prepared": prepared_count,
                "quorum_required": 3,
            }

        # COMMIT local via le primary
        code, resp = _http_json(
            "POST",
            f"{primary_url}/api/v1/consensus/pbft/commit",
            {"view": view, "seq": seq, "digest": digest, "block": block},
            timeout=self._timeout * 2,
            api_key=self._api_key,
        )
        if code == 200 and (resp.get("ok") or resp.get("written") or resp.get("block_index") is not None):
            return prepared_count, {"ok": True, "block": resp.get("block") or block, **resp}
        return prepared_count, {
            "ok": False,
            "reason": f"commit_failed_{code}",
            "detail": str(resp)[:200],
        }


# ─── Instance par défaut ──────────────────────────────────────────────────────


def get_default_publisher() -> ReasoningPbftPublisher:
    """Retourne un publisher configuré depuis les variables d'environnement."""
    return ReasoningPbftPublisher()
