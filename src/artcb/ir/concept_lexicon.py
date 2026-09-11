"""Language-neutral ConceptID lexicon — multi-locale aliases → ARTCB codes.

Rapport 238 §30 + probe 254/257: ConceptID must not be a text hash.
The live gap was not ConceptID itself (type+sym) — it was the encoder
assigning a *different* symbol per language because triggers were French-only
and FACT fallback minted a unique original per sentence.

This table is the first production layer: same semantic lemma → same code.
Unknown words still mint (honest non-convergence). Do not claim universal
translation. The probe triple (server / verify / signature) is in the table.

Naming (R319 2026-09-11T20:10:00Z) — do not confuse:
  - ``C2`` = lexicon *object code* / scenario symbol for vehicle lemmas
    (voiture/car/coche → code ``C2`` → IR sym ``O1C2``).
  - ``K3e7dc01c5cf83cd8`` = concrete *ConceptID* hash derived from type+sym.
  - Scenario battery id ``C2-A``…``C2-E`` = test ladder, not a ConceptID.
These are three namespaces. Lexical PASS on C2≠C2-D E2E PASS.

R321 2026-09-11T21:00:00Z — UI locales + Latin:
  FR EN ES PT IT RU ZH (+ LA philological). Tokenizer accepts Latin,
  Cyrillic and CJK so ``автомобиль`` / ``汽车`` can hit the table.
  Synonym layer closes the R319 ``automobile`` GAP for vehicle C2.
  Energy ``E3`` + consume action ``U1`` support L4 phrase bags.
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
    # R321 consume / use — L4 phrases (FR…ZH + LA).
    "потребляет": "U1",
    "потреблять": "U1",
    "consomme": "U1",
    "consommer": "U1",
    "consumes": "U1",
    "consume": "U1",
    "consumit": "U1",
    "consuma": "U1",
    "consome": "U1",
    "consumir": "U1",
    "消耗": "U1",
}

OBJECT_ALIASES: dict[str, str] = {
    "signature": "S2",
    "signatures": "S2",
    "firma": "S2",
    "firmas": "S2",
    # R318 2026-09-11T19:40:00Z — voiture/car/coche same lemma (was FAIL live matrix).
    # R321 2026-09-11T21:00:00Z — FR EN ES PT IT RU LA ZH vehicle synonyms → C2.
    "транспортное": "C2",  # partial of транспортное средство — token hit
    "автомобиль": "C2",
    "автомобили": "C2",
    "automobiles": "C2",
    "automobile": "C2",
    "automóveis": "C2",
    "automóvel": "C2",
    "automóviles": "C2",
    "automóvil": "C2",
    "automobili": "C2",
    "vehiculum": "C2",
    "véhicules": "C2",
    "véhicule": "C2",
    "vehicules": "C2",
    "vehicule": "C2",
    "vehicles": "C2",
    "vehicle": "C2",
    "vehículos": "C2",
    "vehículo": "C2",
    "veículos": "C2",
    "veículo": "C2",
    "veicoli": "C2",
    "veicolo": "C2",
    "vetture": "C2",
    "vettura": "C2",
    "voitures": "C2",
    "voiture": "C2",
    "cars": "C2",
    "car": "C2",
    "coches": "C2",
    "coche": "C2",
    "carros": "C2",
    "carro": "C2",
    "autos": "C2",
    "auto": "C2",
    "raeda": "C2",
    "currus": "C2",
    "машина": "C2",
    "машины": "C2",
    "轿车": "C2",
    "汽车": "C2",
    "车辆": "C2",
    # Energy — L4 bag partner for vehicle consume phrases.
    "энергией": "E3",
    "энергии": "E3",
    "энергия": "E3",
    "énergies": "E3",
    "énergie": "E3",
    "energies": "E3",
    "energie": "E3",
    "energy": "E3",
    "energías": "E3",
    "energía": "E3",
    "energias": "E3",
    "energia": "E3",
    "energiam": "E3",
    "能源": "E3",
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

# R324 2026-09-12T01:20:00Z — intensity/quantity modifiers (fidelity beaucoup≠peu).
# Without these, L4 bag U1C2E3 collapsed opposite adverbs → FAIL_COLLAPSE.
MODIFIER_ALIASES: dict[str, str] = {
    # high — L4 multilingual “a lot / mucha / …”
    "beaucoup": "QH",
    "lots": "QH",
    "lot": "QH",
    "mucha": "QH",
    "mucho": "QH",
    "muita": "QH",
    "muito": "QH",
    "molta": "QH",
    "molto": "QH",
    "много": "QH",
    "multam": "QH",
    "multa": "QH",
    "大量": "QH",
    # low — must diverge from QH
    "peu": "QL",
    "little": "QL",
    "few": "QL",
    "poca": "QL",
    "poco": "QL",
    "pouca": "QL",
    "pouco": "QL",
    "мало": "QL",
    "parum": "QL",
    "少量": "QL",
    # R325 2026-09-12T01:50:00Z — modality (negation handled in modifier_codes)
    "peut": "MOD",
    "peux": "MOD",
    "pouvoir": "MOD",
    "can": "MOD",
    "may": "MOD",
    "might": "MOD",
    "could": "MOD",
    "doesn't": "NEG",
    "does not": "NEG",
    "cannot": "NEG",
    "can't": "NEG",
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
MODIFIER_KEYS = _sorted_keys(MODIFIER_ALIASES)

# Latin + Cyrillic + CJK (R321). Short ASCII lemmas stay token-exact to avoid
# auto⊂autonomie / car⊂cartography false hits.
_TOKEN_RE = __import__("re").compile(
    r"[a-zàâäéèêëïîôùûüçñæœ]+"
    r"|[а-яё]+"
    r"|[\u4e00-\u9fff]+",
)


def _token_list(text_lower: str) -> list[str]:
    """Ordered whole-word tokens — R318: 'car' must not hit inside 'verificar'."""
    return [m.group(0) for m in _TOKEN_RE.finditer(text_lower)]


def _tokens(text_lower: str) -> set[str]:
    return set(_token_list(text_lower))


def _key_hits(key: str, toks: set[str], text_lower: str) -> bool:
    """Match lexicon key without ASCII false-substring collisions (R321)."""
    if key in toks:
        return True
    if len(key) < 2:
        return False
    if any(ord(c) > 127 for c in key):
        return key in text_lower
    # ASCII stems: substring only when long enough (avoids auto/car collisions).
    return len(key) >= 5 and key in text_lower


# English NP heads: "the car" / "a car" are vehicles, not FR conjunction "car".
_EN_CAR_DETERMINERS = frozenset(
    {"the", "a", "an", "my", "your", "his", "her", "their", "this", "that", "our", "one"}
)


def _car_is_english_vehicle(text_lower: str) -> bool:
    """True when 'car'/'cars' is an English noun phrase head (R319)."""
    toks = _token_list(text_lower)
    for i, tok in enumerate(toks):
        if tok not in {"car", "cars"}:
            continue
        if i > 0 and toks[i - 1] in _EN_CAR_DETERMINERS:
            return True
        if len(toks) == 1:
            return True
    return False


def action_code(text_lower: str) -> str | None:
    toks = _tokens(text_lower)
    for key in ACTION_KEYS:
        if _key_hits(key, toks, text_lower):
            return ACTION_ALIASES[key]
    return None


def object_codes(text_lower: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    toks = _tokens(text_lower)
    for key in OBJECT_KEYS:
        if not _key_hits(key, toks, text_lower):
            continue
        # R318: FR conjunction "car" must not mint vehicle C2.
        # ~~R318 multi-token blanket skip~~ barred R319 2026-09-11T20:15:00Z —
        # it also dropped English "The car consumes…" (false negative).
        # Keep skip only when "car" is NOT an English NP head and not voiture/coche.
        if key in {"car", "cars"} and len(toks) > 1:
            if "voiture" in toks or "coche" in toks or _car_is_english_vehicle(text_lower):
                pass
            else:
                continue
        code = OBJECT_ALIASES[key]
        if code not in seen:
            seen.add(code)
            found.append(code)
    return sorted(found)


def modifier_codes(text_lower: str) -> list[str]:
    """R324 — quantity/intensity codes (QH/QL) for fidelity of adverbs.

    R325 — also NEG (ne…pas / not) and MOD (peut/can) when token-hit.
    """
    found: list[str] = []
    seen: set[str] = set()
    toks = _tokens(text_lower)
    # FR ne…pas / EN not — before alias table so "pas" alone is not enough
    if ("ne" in toks and "pas" in toks) or ("not" in toks):
        seen.add("NEG")
        found.append("NEG")
    for key in MODIFIER_KEYS:
        if not _key_hits(key, toks, text_lower):
            continue
        # EN "lot" is short — require vehicle/energy context to avoid noise
        if key == "lot" and not (
            toks & {"car", "cars", "energy", "energie", "énergie"}
            or "C2" in object_codes(text_lower)
            or "E3" in object_codes(text_lower)
        ):
            continue
        code = MODIFIER_ALIASES[key]
        if code not in seen:
            seen.add(code)
            found.append(code)
    return sorted(found)
