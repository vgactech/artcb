"""ARTCB Language modules — 14 initial languages (R448).

Each language module is independent: developed, tested, versioned separately.
Architecture: lang_module → LexicalEntry → ConceptID → ARTCB symbol.
"""
from __future__ import annotations
MODULE_VERSION = '1.0.1'  # R448 — architecture modules linguistiques

from .registry import LanguageRegistry, get_registry

__all__ = ["LanguageRegistry", "get_registry"]
