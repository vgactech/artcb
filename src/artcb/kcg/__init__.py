"""Knowledge Contribution Graph (KCG) — GO-F + GO-G 2026-09-07.

GO-F : événements CONSULT/USE + UsageID, sans fee.
GO-G : Reasoning Fee (transfert wallet→wallet, jamais mint).

Architecture :
  KnowledgeEntry  — unité de connaissance (graph_id + producteur + metadata)
  ConsultEvent    — CONSULT : accès à K
  UseEvent        — USE : utilisation effective + mesure delta
  KCGStore        — persistance JSONL append-only
  KCGIndex        — index en mémoire
  KCGFeeEngine    — Reasoning Fee transfert (GO-G)
  KCGLedger       — interface ledger pour les transferts
"""

from .events import ConsultEvent, UseEvent, KnowledgeEntry
from .store import KCGStore, KCGIndex
from .fee import KCGFeeEngine, KCGLedger, FeeResult, InsufficientFundsError

__all__ = [
    "ConsultEvent",
    "UseEvent",
    "KnowledgeEntry",
    "KCGStore",
    "KCGIndex",
    "KCGFeeEngine",
    "KCGLedger",
    "FeeResult",
    "InsufficientFundsError",
]
