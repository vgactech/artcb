"""Knowledge Contribution Graph (KCG) — GO-F 2026-09-07.

Enregistre les événements de consultation et d'utilisation de la connaissance.
GO-F : événements CONSULT/USE + UsageID, sans fee (fee = GO-G).
GO-G : Reasoning Fee (transfert wallet→wallet) — s'appuie sur ce module.

Architecture :
  KnowledgeEntry  — unité de connaissance (graph_id + producteur + metadata)
  ConsultEvent    — CONSULT : un agent/humain a découvert et accédé à K
  UseEvent        — USE : un agent/humain a utilisé K et mesuré un delta
  KCGStore        — persistance JSONL append-only (data/kcg/events.jsonl)
  KCGIndex        — index en mémoire (chargé au démarrage)
"""

from .events import ConsultEvent, UseEvent, KnowledgeEntry
from .store import KCGStore, KCGIndex

__all__ = [
    "ConsultEvent",
    "UseEvent",
    "KnowledgeEntry",
    "KCGStore",
    "KCGIndex",
]
