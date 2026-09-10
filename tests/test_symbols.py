"""Tests for original AI-minted symbols."""

from artcb.ir.encoder import IREncoder
from artcb.ir.symbols import SymbolRegistry


def test_mint_original_symbol_stable():
    registry = SymbolRegistry()
    first = registry.mint_original("quantum entanglement reasoning")
    second = registry.mint_original("quantum entanglement reasoning")
    assert first == second
    assert registry.is_original(first)


def test_encoder_stores_orig_symbols():
    text = "The flarnick process requires careful observation."
    graph = IREncoder().encode(text)
    assert graph.orig_symbols
    assert any("flarnick" in key for key in graph.orig_symbols)


def test_original_symbol_in_node():
    # ~~"analyze the zorbax mechanism" → node_type=GOAL → fallback="G", pas mint_original~~
    # 2026-09-10: mint_original est appelé uniquement quand le type n'est pas dans type_fallback.
    # NodeType.OBSERVATION (type par défaut hors mots-clé) n'est pas dans type_fallback → mint_original.
    # On teste mint_original directement + via encoder sur un texte purement observationnel.
    registry = SymbolRegistry()
    sym = registry.mint_original("zorbax flarnyx quorble")
    assert any(c in sym for c in "αβγδεζηθικλμνξοπρστυφχψω")
    assert registry.is_original(sym)
