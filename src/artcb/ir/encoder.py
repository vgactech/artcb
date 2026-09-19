"""Encodage texte humain → graphe IR ARTCB v0.1 (fallback rule-based)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import logging
import uuid
from dataclasses import dataclass

from src.artcb.ir.concept_lexicon import (
    CONTEXT_EXTRA,
    DECISION_EXTRA,
    EVENT_EXTRA,
    GOAL_EXTRA,
    HYPOTHESIS_EXTRA,
    PROOF_EXTRA,
    REASON_EXTRA,
    action_code,
    modifier_codes,
    object_codes,
)
from src.artcb.ir.grammar import (
    CONTEXT_KEYWORDS,
    DECISION_KEYWORDS,
    EVENT_KEYWORDS,
    GOAL_KEYWORDS,
    HYPOTHESIS_KEYWORDS,
    PROOF_KEYWORDS,
    REASON_KEYWORDS,
    EdgeType,
    NodeType,
)
from src.artcb.ir.macros import apply_macros_to_graph
from src.artcb.ir.models import IREdge, IRGraph, IRNode, sha256_text
from src.artcb.ir.symbols import SymbolRegistry

logger = logging.getLogger("artcb.ir.encoder")


@dataclass
class SentenceSpan:
    text: str
    start: int
    end: int


# R360 — seuils de scalabilité du graphe complet.
#
# Sous MAX_COMPLETE_GRAPH_NODES nœuds : graphe complet N(N-1) arcs CONNECTS.
# Au-delà : fenêtre glissante ±SLIDING_WINDOW_K voisins par nœud.
#   Exemple : pour K=5, chaque nœud est connecté aux 5 précédents et 5 suivants.
#   Arcs = min(N(N-1), 2*K*N) ≈ O(K·N) linéaire.
# Cela préserve la sémantique « co-présence contextuelle proche »
# sans explosion quadratique sur les grands documents.
MAX_COMPLETE_GRAPH_NODES: int = 20   # graphe complet en dessous
SLIDING_WINDOW_K: int = 5            # voisins de chaque côté au-dessus


class IREncoder:
    """Encode text into IR graph with guaranteed reversibility via source_text + spans."""

    def __init__(
        self,
        symbol_registry: SymbolRegistry | None = None,
        enable_cache: bool = True,
        max_complete_nodes: int = MAX_COMPLETE_GRAPH_NODES,
        sliding_window_k: int = SLIDING_WINDOW_K,
    ) -> None:
        self._registry = symbol_registry or SymbolRegistry()
        self._cache: dict[str, IRGraph] = {} if enable_cache else None
        self._cache_enabled = enable_cache
        self._max_complete_nodes = max_complete_nodes
        self._sliding_window_k = sliding_window_k

    def encode(self, text: str, session_id: str | None = None) -> IRGraph:
        # Cache optimization: Check if text already encoded
        if self._cache_enabled and self._cache is not None:
            text_hash = sha256_text(text)
            if text_hash in self._cache:
                cached = self._cache[text_hash]
                logger.debug("Cache HIT text_hash=%s reusing graph", text_hash[:16])
                # Return copy with new session_id if provided
                new_graph_id = session_id or f"g_{uuid.uuid4().hex[:12]}"
                return cached.model_copy(update={"graph_id": new_graph_id})

        # Cache MISS or cache disabled: perform full encoding
        if not text or not text.strip():
            raise ValueError("Le texte à encoder ne peut pas être vide.")

        graph_id = session_id or f"g_{uuid.uuid4().hex[:12]}"
        spans = self._split_into_spans(text)
        logger.debug("Encodage graph_id=%s spans=%d chars=%d", graph_id, len(spans), len(text))

        nodes: list[IRNode] = []
        edges: list[IREdge] = []

        for index, span in enumerate(spans, start=1):
            node_id = f"n{index}"
            node_type = self._classify_sentence(span.text)
            symbol = self._build_symbol(span.text, node_type)
            nodes.append(
                IRNode(
                    id=node_id,
                    t=node_type.value,
                    sym=symbol,
                    txt=span.text,
                    checksum=sha256_text(span.text),
                    start=span.start,
                    end=span.end,
                )
            )

        # R359/R360 — construction des arcs CONNECTS.
        #
        # Mode GRAPHE COMPLET (N ≤ max_complete_nodes, défaut 20) :
        #   Pour chaque paire ordonnée (i,j) avec i≠j → arc CONNECTS.
        #   Total = N(N-1) arcs. Garantit la connectivité directe maximale.
        #
        # Mode FENÊTRE GLISSANTE (N > max_complete_nodes) :
        #   Chaque nœud i est connecté aux nœuds dans [i-K, i+K] \ {i}.
        #   Total ≈ 2·K·N arcs (linéaire, O(K·N)).
        #   Préserve la co-présence contextuelle proche sans explosion quadratique.
        #
        # Dans les deux modes :
        #   TEMPORAL : uniquement entre consécutifs (i→i+1), N-1 arcs.
        #   CAUSES   : uniquement si marqueur causal détecté, jamais inventé.
        n = len(nodes)
        use_complete = n <= self._max_complete_nodes

        if use_complete:
            # Graphe complet : toutes les paires ordonnées
            connects_pairs: list[tuple[int, int]] = [
                (i, j) for i in range(n) for j in range(n) if i != j
            ]
        else:
            # Fenêtre glissante : voisins dans ±K
            k = self._sliding_window_k
            connects_pairs = [
                (i, j)
                for i in range(n)
                for j in range(max(0, i - k), min(n, i + k + 1))
                if i != j
            ]
            logger.debug(
                "R360 fenêtre glissante activée : N=%d > seuil=%d → %d paires CONNECTS (K=%d)",
                n, self._max_complete_nodes, len(connects_pairs), k,
            )

        for i, j in connects_pairs:
            ni, nj = nodes[i], nodes[j]
            edges.append(
                IREdge(**{"from": ni.id, "to": nj.id, "rel": EdgeType.CONNECTS.value, "w": 1.0})
            )

        # TEMPORAL : consécutifs uniquement, dans les deux modes
        for i in range(n - 1):
            ni, nj = nodes[i], nodes[i + 1]
            edges.append(
                IREdge(**{"from": ni.id, "to": nj.id, "rel": EdgeType.TEMPORAL.value, "w": 1.0})
            )
            # CAUSES : uniquement si marqueur détecté, jamais inventé
            if self._has_causal_link(spans[i].text, spans[i + 1].text):
                edges.append(
                    IREdge(**{"from": ni.id, "to": nj.id, "rel": EdgeType.CAUSES.value, "w": 0.8})
                )

        join_sep = self._detect_join_separator(text, spans)
        graph = IRGraph(
            graph_id=graph_id,
            source_text=text,
            nodes=nodes,
            edges=edges,
            checksum=sha256_text(text),
            join_sep=join_sep,
            orig_symbols=self._registry.export(),
        )

        if not graph.verify_integrity():
            raise RuntimeError("Échec vérification intégrité après encodage.")

        graph = apply_macros_to_graph(graph)

        # Store in cache for future reuse
        if self._cache_enabled and self._cache is not None:
            text_hash = sha256_text(text)
            self._cache[text_hash] = graph
            logger.debug("Cache STORE text_hash=%s", text_hash[:16])

        logger.debug(
            "Encodage terminé nodes=%d edges=%d macros=%d compression=%.2f cache_size=%d",
            len(graph.nodes),
            len(graph.edges),
            len(graph.macros),
            self.compression_ratio(graph),
            len(self._cache) if self._cache else 0,
        )
        return graph

    @staticmethod
    def compression_ratio(graph: IRGraph) -> float:
        if not graph.source_text:
            return 0.0
        ir_size = len(graph.to_json(indent=None))
        return round(1.0 - (ir_size / len(graph.source_text)), 4)

    def _split_into_spans(self, text: str) -> list[SentenceSpan]:
        spans: list[SentenceSpan] = []
        cursor = 0
        length = len(text)

        while cursor < length:
            while cursor < length and text[cursor].isspace():
                cursor += 1
            if cursor >= length:
                break

            boundary = self._find_sentence_end(text, cursor)
            segment = text[cursor:boundary]
            if segment.strip():
                spans.append(SentenceSpan(text=segment, start=cursor, end=boundary))
            cursor = boundary

        if not spans:
            spans.append(SentenceSpan(text=text, start=0, end=len(text)))

        return spans

    @staticmethod
    def _find_sentence_end(text: str, start: int) -> int:
        length = len(text)
        i = start
        while i < length:
            char = text[i]
            if char in ".!?…":
                j = i + 1
                while j < length and text[j] in "\"'»)":
                    j += 1
                if j >= length or text[j].isspace() or text[j] == "\n":
                    return j if j < length else length
            i += 1
        return length

    @staticmethod
    def _detect_join_separator(text: str, spans: list[SentenceSpan]) -> str:
        if len(spans) < 2:
            return ""
        between = text[spans[0].end : spans[1].start]
        if between:
            return between
        return " "

    @staticmethod
    def _keyword_hit(text: str, keys: tuple[str, ...]) -> bool:
        """Substring for long lemmas; word-boundary for short ones.

        ``car `` matched inside Spanish ``verificar la`` and flipped type to R.
        """
        import re

        for key in keys:
            token = key.strip()
            if not token:
                continue
            if len(token) <= 3:
                if re.search(rf"\b{re.escape(token)}\b", text):
                    return True
            elif key in text:
                return True
        return False

    def _classify_sentence(self, sentence: str) -> NodeType:
        lowered = sentence.lower()
        # R318: lone EN "car" (vehicle / C2) must not become French conjunction REASON.
        # R319: English "the/a/… car …" must not hit REASON via grammar keyword "car ".
        from src.artcb.ir.concept_lexicon import (
            _car_is_english_vehicle,
            _tokens,
            object_codes,
        )

        toks = _tokens(lowered.strip())
        if len(toks) == 1 and object_codes(lowered):
            return NodeType.FACT
        en_vehicle = _car_is_english_vehicle(lowered) and "C2" in object_codes(lowered)
        if self._keyword_hit(lowered, DECISION_KEYWORDS + DECISION_EXTRA):
            return NodeType.DECISION
        if self._keyword_hit(lowered, HYPOTHESIS_KEYWORDS + HYPOTHESIS_EXTRA):
            return NodeType.HYPOTHESIS
        if not en_vehicle and self._keyword_hit(lowered, REASON_KEYWORDS + REASON_EXTRA):
            return NodeType.REASON
        if self._keyword_hit(lowered, GOAL_KEYWORDS + GOAL_EXTRA):
            return NodeType.GOAL
        if self._keyword_hit(lowered, PROOF_KEYWORDS + PROOF_EXTRA):
            return NodeType.PROOF
        if self._keyword_hit(lowered, EVENT_KEYWORDS + EVENT_EXTRA):
            return NodeType.EVENT
        if self._keyword_hit(lowered, CONTEXT_KEYWORDS + CONTEXT_EXTRA):
            return NodeType.CONTEXT
        return NodeType.FACT

    def _build_symbol(self, sentence: str, node_type: NodeType) -> str:
        """Language-neutral symbol: all matching object codes, sorted.

        One object (first match) made FR/EN/ES diverge when the first
        hit was 'serveur' vs 'signature'. Collecting every lemma keeps
        ConceptID stable for the same semantic bag.
        """
        lowered = sentence.lower()
        action = action_code(lowered) or "O1"
        objs = object_codes(lowered)
        mods = modifier_codes(lowered)
        if not objs:
            type_fallback = {
                NodeType.DECISION: "K1",
                NodeType.HYPOTHESIS: "H",
                NodeType.REASON: "R1",
                NodeType.GOAL: "G",
                NodeType.PROOF: "P",
                NodeType.EVENT: "E",
                NodeType.CONTEXT: "M2",
            }
            objs = [type_fallback.get(node_type, self._registry.mint_original(sentence))]
        # R324: append sorted modifiers so beaucoup (QH) ≠ peu (QL).
        return f"{action}{''.join(objs)}{''.join(mods)}"

    @staticmethod
    def _has_causal_link(previous: str, current: str) -> bool:
        causal_markers = ("donc", "ainsi", "par conséquent", "par consequent", "alors", "c'est pourquoi")
        return any(marker in current.lower() for marker in causal_markers)
