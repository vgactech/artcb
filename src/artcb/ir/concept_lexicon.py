"""Language-neutral ConceptID lexicon — FR / EN / ES aliases → ARTCB codes.

Rapport 238 §30 + probe 254/257: ConceptID must not be a text hash.
The live gap was not ConceptID itself (type+sym) — it was the encoder
assigning a *different* symbol per language because triggers were French-only
and FACT fallback minted a unique original per sentence.

This table is the first production layer: same semantic lemma → same code.
Unknown words still mint (honest non-convergence). Do not claim universal
translation. The probe triple (server / verify / signature) is in the table.
"""

from __future__ import annotations

# Longer keys first so "verificar" wins over "veri".
ACTION_ALIASES: dict[str, str] = {
    "verificar": "V1",
    "verifica": "V1",
    "vérifier": "V1",
    "verifier": "V1",
    "vérifi": "V1",
    "verifi": "V1",
    "verify": "V1",
    "verifies": "V1",
    "checking": "V1",
    "authenticate": "V1",
    "authentifier": "V1",
    "autenticar": "V1",
    "validar": "V1",
    "validate": "V1",
    "observer": "O1",
    "observe": "O1",
    "observar": "O1",
    "regard": "O1",
    "watch": "O1",
    "comparer": "C1",
    "compare": "C1",
    "comparar": "C1",
    "compar": "C1",
    "créer": "K1",
    "creer": "K1",
    "create": "K1",
    "crear": "K1",
    "apprend": "A1",
    "learn": "A1",
    "aprender": "A1",
    "mémor": "M1",
    "memor": "M1",
    "remember": "M1",
    "relier": "R1",
    "relate": "R1",
    "relacionar": "R1",
    "déduire": "D1",
    "deduire": "D1",
    "deduce": "D1",
    "deducir": "D1",
}

OBJECT_ALIASES: dict[str, str] = {
    "signature": "S2",
    "signatures": "S2",
    "firma": "S2",
    "firmas": "S2",
    # R318 2026-09-11T19:40:00Z — voiture/car/coche same lemma (was FAIL live matrix).
    "voitures": "C2",
    "voiture": "C2",
    "cars": "C2",
    "car": "C2",
    "coches": "C2",
    "coche": "C2",
    "servidor": "N1",
    "serveurs": "N1",
    "serveur": "N1",
    "servers": "N1",
    "server": "N1",
    "nœud": "N1",
    "noeud": "N1",
    "nodos": "N1",
    "nodo": "N1",
    "nodes": "N1",
    "node": "N1",
    "blockchain": "M3",
    "blockchains": "M3",
    "bloques": "B1",
    "bloque": "B1",
    "blocks": "B1",
    "block": "B1",
    "blocs": "B1",
    "bloc": "B1",
    "connaissance": "M3",
    "knowledge": "M3",
    "conocimiento": "M3",
    "mémoire": "M2",
    "memoire": "M2",
    "memory": "M2",
    "memoria": "M2",
    "preuve": "P2",
    "proof": "P2",
    "prueba": "P2",
    "monde": "M1",
    "world": "M1",
    "mundo": "M1",
    "problème": "P1",
    "probleme": "P1",
    "problem": "P1",
    "problema": "P1",
    "solution": "S1",
    "solutions": "S1",
    "contexte": "M2",
    "context": "M2",
    "contexto": "M2",
}

# Classification keywords — keep French originals and add EN/ES.
DECISION_EXTRA = ("decid", "choose", "chosen", "elegir", "elegid", "decidir")
HYPOTHESIS_EXTRA = ("perhaps", "maybe", "hypothesis", "tal vez", "quizá", "hipótes")
REASON_EXTRA = ("because", "therefore", "thus", "porque", "por eso", "entonces")
GOAL_EXTRA = ("goal", "objective", "we must", "objetivo", "debemos")
PROOF_EXTRA = ("proof", "source", "reference", "prueba", "fuente", "referencia")
EVENT_EXTRA = ("yesterday", "today", "tomorrow", "ayer", "hoy", "mañana", "when ", "cuando")
CONTEXT_EXTRA = ("context", "session", "conversation", "project", "contexto", "proyecto")


def _sorted_keys(table: dict[str, str]) -> list[str]:
    return sorted(table, key=len, reverse=True)


ACTION_KEYS = _sorted_keys(ACTION_ALIASES)
OBJECT_KEYS = _sorted_keys(OBJECT_ALIASES)


def _tokens(text_lower: str) -> set[str]:
    """Whole-word tokens only — R318: 'car' must not hit inside 'verificar'."""
    import re

    return {m.group(0) for m in re.finditer(r"[a-zàâäéèêëïîôùûüçñ]+", text_lower)}


def action_code(text_lower: str) -> str | None:
    toks = _tokens(text_lower)
    # Prefer exact token match; fall back to substring for multi-word stems
    # like "vérifi" only when key length >= 4 (avoids 'car' ⊂ 'verificar').
    for key in ACTION_KEYS:
        if key in toks:
            return ACTION_ALIASES[key]
    for key in ACTION_KEYS:
        if len(key) >= 4 and key in text_lower:
            return ACTION_ALIASES[key]
    return None


def object_codes(text_lower: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    toks = _tokens(text_lower)
    for key in OBJECT_KEYS:
        hit = key in toks or (len(key) >= 4 and key in text_lower)
        if not hit:
            continue
        # R318: FR conjunction "car" inside a clause must not mint vehicle C2.
        if key in {"car", "cars"} and len(toks) > 1 and "voiture" not in toks and "coche" not in toks:
            continue
        code = OBJECT_ALIASES[key]
        if code not in seen:
            seen.add(code)
            found.append(code)
    return sorted(found)
