"""Grammaire et constantes IR ARTCB v0.1."""

from __future__ import annotations

from enum import StrEnum


class NodeType(StrEnum):
    FACT = "F"
    EVENT = "E"
    REASON = "R"
    HYPOTHESIS = "H"
    DECISION = "D"
    GOAL = "G"
    PROOF = "P"
    CONTEXT = "C"
    MACRO = "M"


class EdgeType(StrEnum):
    CAUSES = "→"
    IMPLIES = "⇒"
    DEPENDS = "⊃"
    TEMPORAL = "→t"
    CONTRADICTS = "⊥"
    SUPPORTS = "⊢"
    COMPRESSES = "≡"
    # R359 — arc structurel bidirectionnel du graphe complet.
    # Signifie "co-présent dans le même contexte".
    # Ne doit PAS être interprété comme une relation causale ou temporelle.
    CONNECTS = "↔"


IR_VERSION = "0.1"

ACTION_CODES = {
    "observer": "O1",
    "comparer": "C1",
    "creer": "K1",
    "verifier": "V1",
    "apprendre": "A1",
    "memoriser": "M1",
    "relier": "R1",
    "deduire": "D1",
}

OBJECT_CODES = {
    "monde": "M1",
    "memoire": "M2",
    "connaissance": "M3",
    "probleme": "P1",
    "solution": "S1",
}

DECISION_KEYWORDS = ("décid", "decid", "choisi", "chois", "retenu", "validé", "valide")
HYPOTHESIS_KEYWORDS = ("hypoth", "peut-être", "peut etre", "probable", "suppos", "si ")
REASON_KEYWORDS = ("parce que", "car ", "donc", "ainsi", "cependant", "en effet", "alors")
GOAL_KEYWORDS = ("objectif", "but ", "prochaine étape", "prochaine etape", "nous devons")
PROOF_KEYWORDS = ("preuve", "démonstr", "demonstr", "cite", "source", "référence", "reference")
EVENT_KEYWORDS = ("hier", "aujourd", "demain", "lors", "quand ", "après", "apres", "avant ")
CONTEXT_KEYWORDS = ("contexte", "session", "conversation", "projet")

ACTION_TRIGGERS = {
    "observer": "O1",
    "regard": "O1",
    "compar": "C1",
    "créer": "K1",
    "creer": "K1",
    "créé": "K1",
    "cree": "K1",
    "vérifi": "V1",
    "verifi": "V1",
    "apprend": "A1",
    "mémor": "M1",
    "memor": "M1",
    "relier": "R1",
    "dédu": "D1",
    "dedu": "D1",
}

OBJECT_TRIGGERS = {
    "monde": "M1",
    "mémoire": "M2",
    "memoire": "M2",
    "connaissance": "M3",
    "problème": "P1",
    "probleme": "P1",
    "solution": "S1",
    "contexte": "M2",
    "fastapi": "S1",
    "graphe": "M3",
    "blockchain": "M3",
    "architecture": "S1",
}
