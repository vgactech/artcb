"""ARTCB Knowledge Layer — KnowledgeID, UsageID, provenance, composition (R434).

Ce package implémente la couche de connaissance du langage IA ARTCB :

    Raisonnement (CanonicalReasoning)
         ↓
    KnowledgeID  (identifiant stable d'une connaissance produite)
         ↓
    ↙         ↘
  stockage   transmission
    ↓              ↓
  Agent B      Agent C
    ↓              ↓
  UsageID      UsageID
    ↓
  PoL → Reward

Architecture :
  - knowledge.py  : KnowledgeRecord, KnowledgeID, create_knowledge()
  - usage.py      : UsageRecord, UsageID, record_usage()
  - provenance.py : ProvenanceChain — lignée A→B→C
  - composition.py: compose_knowledge() — combinaison de plusieurs KnowledgeIDs
  - store.py      : KnowledgeStore — persistance JSON + recherche par ID
"""

from src.artcb.knowledge.knowledge import (
    KnowledgeRecord,
    KnowledgeStatus,
    create_knowledge,
)
from src.artcb.knowledge.usage import (
    UsageRecord,
    record_usage,
)
from src.artcb.knowledge.provenance import ProvenanceChain, ProvenanceLink
from src.artcb.knowledge.composition import compose_knowledge
from src.artcb.knowledge.store import KnowledgeStore

__all__ = [
    "KnowledgeRecord",
    "KnowledgeStatus",
    "create_knowledge",
    "UsageRecord",
    "record_usage",
    "ProvenanceChain",
    "ProvenanceLink",
    "compose_knowledge",
    "KnowledgeStore",
]
