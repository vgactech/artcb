"""Module Réflexe ARTCB — Priorité automatique (R350–R354, 2026-09-17).

Ce module gère l'activation automatique du réflexe ARTCB :
- Détection des déclencheurs (mémoire, thinking, raisonnement)
- Priorisation des chantiers
- Amélioration autonome de l'agent
- Synchronisation Bob IDE ↔ Cursor
"""
from src.artcb.reflex.core import ReflexEngine, ReflexTrigger, ReflexPriority

__all__ = ["ReflexEngine", "ReflexTrigger", "ReflexPriority"]
