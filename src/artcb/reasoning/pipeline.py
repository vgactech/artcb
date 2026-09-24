"""R450 — ARTCD G4 : Pipeline de raisonnement bout-en-bout ARTCB.

Ce module orchestre le pipeline complet d'un cycle de raisonnement ARTCB :

    text (n'importe quelle langue)
          ↓
    IREncoder.encode()          → IRGraph
          ↓
    canonicalize_text()         → CanonicalReasoning
          ↓
    create_knowledge()          → KnowledgeRecord (frozen)
          ↓
    record_usage()              → UsageRecord   (frozen)
          ↓
    PolScorer.score()           → PolMetrics    (frozen)
          ↓
    create_knowledge_work_record() → KnowledgeWorkRecord (PENDING)
          ↓
    [on-chain via KnowledgeWorkStore.seal_with_block_hash()]

Propriétés garanties (G4) :
  - DÉTERMINISME   : même texte + même producer_id → même KnowledgeID (reasoning_id stable)
  - COHÉRENCE      : knowledge_id présent dans PolMetrics, UsageRecord et KnowledgeWorkRecord
  - RÉSISTANCE     : texte vide / None / malformé → PipelineError sans crash
  - MULTILINGUISME : 14 langues ARTCB produisent un CanonicalReasoning (reasoning_id peut diverger)
  - INVARIANTS PoL : unique_human_proven=False dans toute la chaîne ; CERTIFIED_100=false

Séparations fondamentales (non implémentées ici) :
  - on-chain seal  : hors scope de ce module — utiliser KnowledgeWorkStore.seal_with_block_hash()
  - FHE biométrique: hors scope — homomorphic.py stub
  - FAR/FRR        : non mesurés sur vrais capteurs

PROTOCOLE ARTCB — mode DEBUG actif — CERTIFIED_100=false.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.2'  # R450 — ARTCD G4 reasoning pipeline

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.artcb.chain.knowledge_work import KnowledgeWorkRecord, create_knowledge_work_record
from src.artcb.ir.encoder import IREncoder
from src.artcb.ir.models import IRGraph
from src.artcb.knowledge.knowledge import (
    KnowledgeRecord,
    KnowledgeStatus,
    KnowledgeType,
    create_knowledge,
)
from src.artcb.knowledge.usage import UsagePurpose, UsageRecord, record_usage
from src.artcb.pol.scorer import PolMetrics, PolScorer
from src.artcb.reasoning.canonical import CanonicalReasoning, canonicalize_text
from src.artcb.trace.forensic import (
    AttemptOutcome,
    EvaluationContext,
    ForensicEventType,
    ForensicLedger,
    emit_forensic,
)

logger = logging.getLogger("artcb.reasoning.pipeline")

# ─── Erreurs pipeline ─────────────────────────────────────────────────────────


class PipelineError(ValueError):
    """Levée quand une entrée invalide empêche l'exécution du pipeline G4."""


class PipelineStageError(RuntimeError):
    """Levée quand une étape interne échoue de façon inattendue (stage documenté)."""


# ─── Résultat complet du pipeline ─────────────────────────────────────────────


@dataclass(frozen=True)
class PipelineResult:
    """Résultat d'un cycle de raisonnement complet G4.

    Champs :
      ir_graph          : graphe IR produit par IREncoder
      canonical         : CanonicalReasoning avec reasoning_id déterministe
      knowledge         : KnowledgeRecord frozen (statut ACTIVE)
      usage             : UsageRecord frozen (purpose=POL_CLAIM)
      pol_metrics       : PolMetrics avec pol_score et block_accepted
      work_record       : KnowledgeWorkRecord PENDING (non encore inscrit on-chain)
      input_text        : texte source (langue quelconque)
      producer_id       : identifiant agent/wallet producteur
      language_hint     : langue déclarée ('fr', 'en', etc.) — indicatif uniquement
      session_id        : identifiant de session (généré si absent)
      created_at        : timestamp ISO UTC de création
      unique_human_proven : TOUJOURS False — invariant ARTCB
      certified_100     : TOUJOURS False — invariant ARTCB
    """
    ir_graph: IRGraph
    canonical: CanonicalReasoning
    knowledge: KnowledgeRecord
    usage: UsageRecord
    pol_metrics: PolMetrics
    work_record: KnowledgeWorkRecord
    input_text: str
    producer_id: str
    language_hint: str
    session_id: str
    created_at: str
    unique_human_proven: bool = False   # invariant — jamais True
    certified_100: bool = False         # invariant — jamais True

    def to_summary(self) -> dict[str, Any]:
        """Résumé serialisable des identifiants et métriques clés."""
        return {
            "knowledge_id": self.knowledge.knowledge_id,
            "reasoning_id": self.canonical.reasoning_id(),
            "usage_id": self.usage.usage_id,
            "work_record_id": self.work_record.work_record_id,
            "pol_score": self.pol_metrics.pol_score,
            "block_accepted": self.pol_metrics.block_accepted,
            "pol_eligible": self.usage.pol_eligible,
            "language_hint": self.language_hint,
            "producer_id": self.producer_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "unique_human_proven": self.unique_human_proven,
            "certified_100": self.certified_100,
        }


# ─── Pipeline principal ───────────────────────────────────────────────────────


class ReasoningPipeline:
    """Pipeline G4 : text → IR → canonical → knowledge → PoL → KnowledgeWorkRecord.

    Usage :
        pipeline = ReasoningPipeline()
        result = pipeline.run(
            text="Le serveur valide la signature PQC",
            producer_id="agent_A",
            language_hint="fr",
        )
        print(result.to_summary())
    """

    # Longueur minimale d'un texte pour être traitable (en caractères)
    MIN_TEXT_LEN: int = 3
    # Longueur maximale avant tronque et avertissement (en caractères)
    MAX_TEXT_LEN: int = 10_000

    def __init__(
        self,
        *,
        encoder: IREncoder | None = None,
        pol_scorer: PolScorer | None = None,
        forensic_ledger: ForensicLedger | None = None,
    ) -> None:
        self._encoder = encoder or IREncoder()
        self._pol = pol_scorer or PolScorer()
        self._forensic = forensic_ledger  # None = pas de persistence (tests)

    def run(
        self,
        text: str,
        *,
        producer_id: str,
        work_id: str | None = None,
        language_hint: str = "und",
        session_id: str | None = None,
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str = "",
        trace_id: str = "",
    ) -> PipelineResult:
        """Exécute le pipeline complet G4 pour un texte entrant.

        Args:
            text           : texte source (toute langue reconnue par IREncoder)
            producer_id    : identifiant agent ou wallet producteur (obligatoire, non vide)
            work_id        : identifiant de travail économique (généré si absent)
            language_hint  : code langue ISO 639-1 ('fr', 'en', 'ar', …) — indicatif
            session_id     : identifiant session (généré si absent)
            created_at     : timestamp ISO UTC (généré si absent)
            metadata       : champs libres additionnels
            correlation_id : identifiant de corrélation forensic (généré si absent)
            trace_id       : identifiant de trace forensic (optionnel)

        Returns:
            PipelineResult frozen avec tous les maillons de la chaîne.

        Raises:
            PipelineError      : texte invalide, producer_id vide, ou autre entrée rejetée.
            PipelineStageError : erreur interne à une étape spécifique.
        """
        # ── Validation des entrées ───────────────────────────────────────────
        if not producer_id or not producer_id.strip():
            raise PipelineError("producer_id ne peut pas être vide")
        if text is None:
            raise PipelineError("text ne peut pas être None")
        if not isinstance(text, str):
            raise PipelineError(f"text doit être une str, reçu: {type(text).__name__}")
        text_stripped = text.strip()
        if len(text_stripped) < self.MIN_TEXT_LEN:
            raise PipelineError(
                f"text trop court ({len(text_stripped)} car) — minimum {self.MIN_TEXT_LEN}"
            )
        if len(text_stripped) > self.MAX_TEXT_LEN:
            logger.warning(
                "[G4-pipeline] text trop long (%d car), tronqué à %d",
                len(text_stripped), self.MAX_TEXT_LEN,
            )
            text_stripped = text_stripped[: self.MAX_TEXT_LEN]

        ts = created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        sid = session_id or f"g4-{uuid.uuid4().hex[:12]}"
        wid = work_id or f"work-{uuid.uuid4().hex[:16]}"
        corr_id = correlation_id or f"corr-{uuid.uuid4().hex[:16]}"
        meta = dict(metadata or {})
        meta.setdefault("language_hint", language_hint)

        # ── Étape 1 : IREncoder ──────────────────────────────────────────────
        try:
            ir_graph: IRGraph = self._encoder.encode(text_stripped, session_id=sid)
        except Exception as exc:  # noqa: BLE001
            emit_forensic(
                self._forensic,
                event_type=ForensicEventType.IR_ENCODE_FAIL,
                outcome=AttemptOutcome.INTERNAL_ERROR,
                evaluation_context=EvaluationContext.REASONING_PIPELINE,
                correlation_id=corr_id, trace_id=trace_id, session_id=sid,
                layer="reasoning", actor_ref=producer_id,
                algorithm_version=MODULE_VERSION,
                failure_reason_code="IR_ENCODE_ERROR",
                extra={"error": str(exc)[:200], "language_hint": language_hint},
            )
            raise PipelineStageError(f"[G4-E1-IREncoder] {exc}") from exc

        emit_forensic(
            self._forensic,
            event_type=ForensicEventType.IR_ENCODE_OK,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.REASONING_PIPELINE,
            correlation_id=corr_id, trace_id=trace_id, session_id=sid,
            layer="reasoning", actor_ref=producer_id,
            algorithm_version=MODULE_VERSION,
            state_after={"ir_node_count": len(ir_graph.nodes), "language_hint": language_hint},
        )

        # ── Étape 2 : CanonicalReasoning ─────────────────────────────────────
        try:
            canonical: CanonicalReasoning = canonicalize_text(text_stripped)
        except Exception as exc:  # noqa: BLE001
            emit_forensic(
                self._forensic,
                event_type=ForensicEventType.CANONICAL_FAIL,
                outcome=AttemptOutcome.INTERNAL_ERROR,
                evaluation_context=EvaluationContext.REASONING_PIPELINE,
                correlation_id=corr_id, trace_id=trace_id, session_id=sid,
                layer="reasoning", actor_ref=producer_id,
                failure_reason_code="CANONICAL_ERROR",
                extra={"error": str(exc)[:200]},
            )
            raise PipelineStageError(f"[G4-E2-Canonical] {exc}") from exc

        reasoning_id: str = canonical.reasoning_id()
        emit_forensic(
            self._forensic,
            event_type=ForensicEventType.CANONICAL_OK,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.REASONING_PIPELINE,
            correlation_id=corr_id, trace_id=trace_id, session_id=sid,
            layer="reasoning", actor_ref=producer_id, subject_ref=reasoning_id,
            algorithm_version=MODULE_VERSION,
            state_after={"reasoning_id": reasoning_id},
        )

        # ── Étape 3 : KnowledgeRecord ─────────────────────────────────────────
        try:
            knowledge: KnowledgeRecord = create_knowledge(
                reasoning_id=reasoning_id,
                producer_id=producer_id,
                knowledge_type=KnowledgeType.REASONING,
                status=KnowledgeStatus.ACTIVE,
                content={
                    "reasoning_id": reasoning_id,
                    "language_hint": language_hint,
                    "session_id": sid,
                },
                metadata={**meta, "pipeline": "G4-R451"},
                created_at=ts,
            )
        except Exception as exc:  # noqa: BLE001
            emit_forensic(
                self._forensic,
                event_type=ForensicEventType.KNOWLEDGE_CREATE_FAIL,
                outcome=AttemptOutcome.INTERNAL_ERROR,
                evaluation_context=EvaluationContext.REASONING_PIPELINE,
                correlation_id=corr_id, trace_id=trace_id, session_id=sid,
                layer="reasoning", actor_ref=producer_id, subject_ref=reasoning_id,
                failure_reason_code="KNOWLEDGE_ERROR",
                extra={"error": str(exc)[:200]},
            )
            raise PipelineStageError(f"[G4-E3-Knowledge] {exc}") from exc

        emit_forensic(
            self._forensic,
            event_type=ForensicEventType.KNOWLEDGE_CREATE_OK,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.REASONING_PIPELINE,
            correlation_id=corr_id, trace_id=trace_id, session_id=sid,
            layer="reasoning", actor_ref=producer_id,
            subject_ref=knowledge.knowledge_id,
            algorithm_version=MODULE_VERSION,
            state_after={"knowledge_id": knowledge.knowledge_id, "status": knowledge.status.value},
        )

        # ── Étape 4 : UsageRecord ─────────────────────────────────────────────
        try:
            usage: UsageRecord = record_usage(
                knowledge_id=knowledge.knowledge_id,
                consumer_id=producer_id,
                purpose=UsagePurpose.POL_CLAIM,
                metadata={**meta, "work_id": wid, "pipeline": "G4-R451"},
                used_at=ts,
                knowledge_status=knowledge.status.value,
            )
        except Exception as exc:  # noqa: BLE001
            emit_forensic(
                self._forensic,
                event_type=ForensicEventType.USAGE_RECORD_FAIL,
                outcome=AttemptOutcome.INTERNAL_ERROR,
                evaluation_context=EvaluationContext.REASONING_PIPELINE,
                correlation_id=corr_id, trace_id=trace_id, session_id=sid,
                layer="reasoning", actor_ref=producer_id,
                subject_ref=knowledge.knowledge_id,
                failure_reason_code="USAGE_ERROR",
                extra={"error": str(exc)[:200]},
            )
            raise PipelineStageError(f"[G4-E4-Usage] {exc}") from exc

        emit_forensic(
            self._forensic,
            event_type=ForensicEventType.USAGE_RECORD_OK,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.REASONING_PIPELINE,
            correlation_id=corr_id, trace_id=trace_id, session_id=sid,
            layer="reasoning", actor_ref=producer_id,
            subject_ref=usage.usage_id,
            algorithm_version=MODULE_VERSION,
            state_after={"usage_id": usage.usage_id, "pol_eligible": usage.pol_eligible},
        )

        # ── Étape 5 : PolMetrics ──────────────────────────────────────────────
        try:
            pol_metrics: PolMetrics = self._pol.score(
                ir_graph,
                knowledge_id=knowledge.knowledge_id,
                usage_id=usage.usage_id,
            )
        except Exception as exc:  # noqa: BLE001
            emit_forensic(
                self._forensic,
                event_type=ForensicEventType.POL_SCORE_FAIL,
                outcome=AttemptOutcome.INTERNAL_ERROR,
                evaluation_context=EvaluationContext.REASONING_PIPELINE,
                correlation_id=corr_id, trace_id=trace_id, session_id=sid,
                layer="reasoning", actor_ref=producer_id,
                subject_ref=knowledge.knowledge_id,
                failure_reason_code="POL_ERROR",
                extra={"error": str(exc)[:200]},
            )
            raise PipelineStageError(f"[G4-E5-PoL] {exc}") from exc

        emit_forensic(
            self._forensic,
            event_type=ForensicEventType.POL_SCORE_OK,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.REASONING_PIPELINE,
            correlation_id=corr_id, trace_id=trace_id, session_id=sid,
            layer="reasoning", actor_ref=producer_id,
            subject_ref=knowledge.knowledge_id,
            algorithm_version=MODULE_VERSION,
            state_after={
                "pol_score": pol_metrics.pol_score,
                "block_accepted": pol_metrics.block_accepted,
            },
        )

        # ── Étape 6 : KnowledgeWorkRecord ─────────────────────────────────────
        try:
            work_record: KnowledgeWorkRecord = create_knowledge_work_record(
                knowledge_id=knowledge.knowledge_id,
                work_id=wid,
                pol_score=pol_metrics.pol_score,
                block_accepted=pol_metrics.block_accepted,
                usage_id=usage.usage_id,
                producer_id=producer_id,
                metadata={**meta, "session_id": sid, "pipeline": "G4-R451"},
                created_at=ts,
            )
        except Exception as exc:  # noqa: BLE001
            emit_forensic(
                self._forensic,
                event_type=ForensicEventType.KNOWLEDGE_WORK_FAIL,
                outcome=AttemptOutcome.INTERNAL_ERROR,
                evaluation_context=EvaluationContext.REASONING_PIPELINE,
                correlation_id=corr_id, trace_id=trace_id, session_id=sid,
                layer="reasoning", actor_ref=producer_id,
                subject_ref=knowledge.knowledge_id,
                failure_reason_code="WORK_RECORD_ERROR",
                extra={"error": str(exc)[:200]},
            )
            raise PipelineStageError(f"[G4-E6-WorkRecord] {exc}") from exc

        # ── Événement forensic final : pipeline complet ───────────────────────
        emit_forensic(
            self._forensic,
            event_type=ForensicEventType.REASONING_PIPELINE_OK,
            outcome=AttemptOutcome.SUCCESS,
            evaluation_context=EvaluationContext.REASONING_PIPELINE,
            correlation_id=corr_id, trace_id=trace_id, session_id=sid,
            layer="reasoning", actor_ref=producer_id,
            subject_ref=work_record.work_record_id,
            algorithm_version=MODULE_VERSION,
            state_after={
                "knowledge_id": knowledge.knowledge_id,
                "usage_id": usage.usage_id,
                "work_record_id": work_record.work_record_id,
                "pol_score": pol_metrics.pol_score,
                "block_accepted": pol_metrics.block_accepted,
                "language_hint": language_hint,
                "unique_human_proven": False,
                "certified_100": False,
            },
            extra={"ir_node_count": len(ir_graph.nodes), "reasoning_id": reasoning_id},
        )

        logger.debug(
            "[G4-pipeline] DONE producer=%s lang=%s knowledge_id=%s pol=%.4f accepted=%s",
            producer_id, language_hint,
            knowledge.knowledge_id, pol_metrics.pol_score, pol_metrics.block_accepted,
        )

        return PipelineResult(
            ir_graph=ir_graph,
            canonical=canonical,
            knowledge=knowledge,
            usage=usage,
            pol_metrics=pol_metrics,
            work_record=work_record,
            input_text=text_stripped,
            producer_id=producer_id,
            language_hint=language_hint,
            session_id=sid,
            created_at=ts,
            unique_human_proven=False,
            certified_100=False,
        )
