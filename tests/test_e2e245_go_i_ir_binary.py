"""Tests GO-I — IR Binaire natif + compression zstd/gzip.

Vérifie :
- Sérialisation/désérialisation roundtrip pour chaque encodage disponible
- En-tête magic + version corrects
- Détection magic invalide → ValueError
- Détection version inconnue → ValueError
- Payload tronqué → ValueError
- compression_stats retourne les bonnes métriques
- json+gzip toujours disponible (sans dépendances optionnelles)
- best_encoding retourne un encodage valide
"""

from __future__ import annotations

import struct
import uuid

import pytest

from artcb.ir.binary import (
    MAGIC,
    FORMAT_VERSION,
    HEADER_SIZE,
    ENC_JSON_GZIP,
    BinaryEncoding,
    best_encoding,
    compression_stats,
    graph_from_bytes,
    graph_to_bytes,
)
from artcb.ir.encoder import IREncoder
from artcb.ir.models import IRGraph


# ── Fixture ────────────────────────────────────────────────────────────────────

SAMPLE_TEXTS = [
    "Le projet ARTCB encode et mémorise la connaissance sur la blockchain.",
    "La décentralisation P2P permet une résilience accrue des données.",
    "Le PoL mesure la qualité sémantique de chaque bloc mémorisé.",
]


@pytest.fixture
def sample_graph() -> IRGraph:
    encoder = IREncoder()
    return encoder.encode(SAMPLE_TEXTS[0])


@pytest.fixture
def multi_node_graph() -> IRGraph:
    encoder = IREncoder()
    text = " ".join(SAMPLE_TEXTS)
    return encoder.encode(text)


# ── Format binaire ─────────────────────────────────────────────────────────────

def test_magic_bytes_present(sample_graph: IRGraph) -> None:
    """Les 4 premiers bytes sont le magic ARCB."""
    data = graph_to_bytes(sample_graph, "json+gzip")
    assert data[:4] == MAGIC


def test_format_version_in_header(sample_graph: IRGraph) -> None:
    """Le byte 4 est la version FORMAT_VERSION."""
    data = graph_to_bytes(sample_graph, "json+gzip")
    version = struct.unpack("B", data[4:5])[0]
    assert version == FORMAT_VERSION


def test_header_size_correct(sample_graph: IRGraph) -> None:
    """L'en-tête fait exactement HEADER_SIZE bytes."""
    data = graph_to_bytes(sample_graph, "json+gzip")
    payload_len = struct.unpack(">I", data[6:10])[0]
    assert len(data) == HEADER_SIZE + payload_len


# ── Roundtrip json+gzip (toujours disponible) ─────────────────────────────────

def test_roundtrip_json_gzip(sample_graph: IRGraph) -> None:
    """json+gzip : encode → decode doit reproduire le graphe identique."""
    data = graph_to_bytes(sample_graph, "json+gzip")
    recovered = graph_from_bytes(data)
    assert recovered.graph_id == sample_graph.graph_id
    assert recovered.source_text == sample_graph.source_text
    assert len(recovered.nodes) == len(sample_graph.nodes)
    assert len(recovered.edges) == len(sample_graph.edges)
    assert recovered.checksum == sample_graph.checksum


def test_roundtrip_json_gzip_multi_node(multi_node_graph: IRGraph) -> None:
    """Graphe multi-nœuds : roundtrip json+gzip conserve tous les nœuds."""
    data = graph_to_bytes(multi_node_graph, "json+gzip")
    recovered = graph_from_bytes(data)
    assert recovered.graph_id == multi_node_graph.graph_id
    assert len(recovered.nodes) == len(multi_node_graph.nodes)


def test_roundtrip_preserves_integrity(sample_graph: IRGraph) -> None:
    """verify_integrity() doit passer sur le graphe récupéré."""
    data = graph_to_bytes(sample_graph, "json+gzip")
    recovered = graph_from_bytes(data)
    assert recovered.verify_integrity() is True


# ── Roundtrip msgpack+gzip (si msgpack disponible) ────────────────────────────

def test_roundtrip_msgpack_gzip_if_available(sample_graph: IRGraph) -> None:
    """msgpack+gzip : roundtrip si msgpack installé, sinon skip."""
    try:
        import msgpack  # noqa: F401
    except ImportError:
        pytest.skip("msgpack non installé")

    data = graph_to_bytes(sample_graph, "msgpack+gzip")
    recovered = graph_from_bytes(data)
    assert recovered.graph_id == sample_graph.graph_id
    assert recovered.source_text == sample_graph.source_text
    assert recovered.verify_integrity() is True


# ── Roundtrip msgpack+zstd (si les deux disponibles) ─────────────────────────

def test_roundtrip_msgpack_zstd_if_available(sample_graph: IRGraph) -> None:
    """msgpack+zstd : roundtrip si msgpack + zstandard installés, sinon skip."""
    try:
        import msgpack  # noqa: F401
        import zstandard  # noqa: F401
    except ImportError:
        pytest.skip("msgpack ou zstandard non installé")

    data = graph_to_bytes(sample_graph, "msgpack+zstd")
    recovered = graph_from_bytes(data)
    assert recovered.graph_id == sample_graph.graph_id
    assert recovered.source_text == sample_graph.source_text
    assert recovered.verify_integrity() is True


# ── Compression (taille) ──────────────────────────────────────────────────────

def test_binary_smaller_than_raw_json(multi_node_graph: IRGraph) -> None:
    """Le format binaire compressé doit être plus petit que le JSON non compressé."""
    import json as _json

    raw_json_size = len(_json.dumps(multi_node_graph.to_canonical_dict(), ensure_ascii=False).encode("utf-8"))
    binary = graph_to_bytes(multi_node_graph, "json+gzip")
    # Le binaire doit être plus compact que le JSON brut
    assert len(binary) < raw_json_size, (
        f"Binaire ({len(binary)}) >= JSON brut ({raw_json_size}) — compression inefficace"
    )


def test_compression_stats_structure(sample_graph: IRGraph) -> None:
    """compression_stats retourne json_size + encodings dict avec au moins json+gzip."""
    stats = compression_stats(sample_graph)
    assert "json_size" in stats
    assert stats["json_size"] > 0
    assert "encodings" in stats
    assert "json+gzip" in stats["encodings"]
    entry = stats["encodings"]["json+gzip"]
    assert "size" in entry
    assert "ratio" in entry
    assert entry["size"] > 0


def test_compression_stats_ratio_positive(multi_node_graph: IRGraph) -> None:
    """Le ratio de compression doit être > 0 pour un graphe non trivial."""
    stats = compression_stats(multi_node_graph)
    ratio = stats["encodings"]["json+gzip"]["ratio"]
    # Pour un vrai graphe texte, la compression doit faire gagner de l'espace
    assert ratio > 0, f"Ratio attendu > 0, obtenu {ratio}"


# ── Erreurs de décodage ────────────────────────────────────────────────────────

def test_bad_magic_raises() -> None:
    """Magic invalide → ValueError."""
    data = b"XXXX" + bytes(HEADER_SIZE - 4)
    with pytest.raises(ValueError, match="Magic invalide"):
        graph_from_bytes(data)


def test_bad_version_raises(sample_graph: IRGraph) -> None:
    """Version inconnue → ValueError."""
    data = bytearray(graph_to_bytes(sample_graph, "json+gzip"))
    data[4] = 99  # version inconnue
    with pytest.raises(ValueError, match="Version binaire inconnue"):
        graph_from_bytes(bytes(data))


def test_truncated_payload_raises(sample_graph: IRGraph) -> None:
    """Payload tronqué → ValueError."""
    data = graph_to_bytes(sample_graph, "json+gzip")
    # On coupe la moitié du payload
    truncated = data[: HEADER_SIZE + (len(data) - HEADER_SIZE) // 2]
    with pytest.raises(ValueError, match="tronqué"):
        graph_from_bytes(truncated)


def test_too_short_raises() -> None:
    """Données trop courtes (< HEADER_SIZE) → ValueError."""
    with pytest.raises(ValueError, match="trop courtes"):
        graph_from_bytes(b"AR")


# ── best_encoding ──────────────────────────────────────────────────────────────

def test_best_encoding_returns_valid() -> None:
    """best_encoding() retourne toujours un encodage valide."""
    enc = best_encoding()
    assert enc in ("msgpack+zstd", "msgpack+gzip", "json+gzip")


def test_best_encoding_roundtrip(sample_graph: IRGraph) -> None:
    """best_encoding() produit un encodage que graph_from_bytes peut lire."""
    enc = best_encoding()
    data = graph_to_bytes(sample_graph, enc)
    recovered = graph_from_bytes(data)
    assert recovered.graph_id == sample_graph.graph_id


# ── Invariant de taille ────────────────────────────────────────────────────────

def test_multiple_graphs_independent(sample_graph: IRGraph, multi_node_graph: IRGraph) -> None:
    """Deux graphes sérialisés indépendamment ne s'interfèrent pas."""
    d1 = graph_to_bytes(sample_graph, "json+gzip")
    d2 = graph_to_bytes(multi_node_graph, "json+gzip")

    r1 = graph_from_bytes(d1)
    r2 = graph_from_bytes(d2)

    assert r1.graph_id == sample_graph.graph_id
    assert r2.graph_id == multi_node_graph.graph_id
    assert r1.graph_id != r2.graph_id
