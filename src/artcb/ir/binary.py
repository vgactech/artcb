"""IR Binaire natif ARTCB — GO-I.

Format binaire compact pour les graphes IR :
  - Sérialisation MessagePack (msgpack) pour les structures de données
  - Compression zstd pour réduire la taille sur le réseau/disque
  - Fallback gzip si zstd non disponible (rétrocompatibilité)
  - Magic bytes + version pour détecter le format

Structure d'un bloc binaire IR :
  [4 bytes magic] [1 byte format_version] [1 byte encoding] [4 bytes payload_len] [payload]

Encodings :
  0x01 = msgpack + zstd
  0x02 = msgpack + gzip (fallback)
  0x03 = json + gzip (rétrocompatibilité)
"""

from __future__ import annotations

import gzip
import json
import logging
import struct
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.artcb.ir.models import IRGraph

logger = logging.getLogger("artcb.ir.binary")

# Magic bytes : ASCII "ARCB"
MAGIC = b"ARCB"
FORMAT_VERSION = 1

# Encodings
ENC_MSGPACK_ZSTD = 0x01
ENC_MSGPACK_GZIP = 0x02
ENC_JSON_GZIP = 0x03

# Taille de l'en-tête binaire : 4 (magic) + 1 (version) + 1 (encoding) + 4 (len) = 10 bytes
HEADER_SIZE = 10

BinaryEncoding = Literal["msgpack+zstd", "msgpack+gzip", "json+gzip"]


def _have_zstd() -> bool:
    try:
        import zstandard  # noqa: F401
        return True
    except ImportError:
        return False


def _have_msgpack() -> bool:
    try:
        import msgpack  # noqa: F401
        return True
    except ImportError:
        return False


def best_encoding() -> BinaryEncoding:
    """Retourne le meilleur encodage disponible sur cette machine."""
    if _have_msgpack() and _have_zstd():
        return "msgpack+zstd"
    if _have_msgpack():
        return "msgpack+gzip"
    return "json+gzip"


def _enc_byte(encoding: BinaryEncoding) -> int:
    if encoding == "msgpack+zstd":
        return ENC_MSGPACK_ZSTD
    if encoding == "msgpack+gzip":
        return ENC_MSGPACK_GZIP
    return ENC_JSON_GZIP


def _enc_from_byte(b: int) -> BinaryEncoding:
    if b == ENC_MSGPACK_ZSTD:
        return "msgpack+zstd"
    if b == ENC_MSGPACK_GZIP:
        return "msgpack+gzip"
    if b == ENC_JSON_GZIP:
        return "json+gzip"
    raise ValueError(f"Encoding byte inconnu : 0x{b:02x}")


def _serialize(data: dict, encoding: BinaryEncoding) -> bytes:
    """Sérialise un dict Python selon l'encodage choisi."""
    if encoding in ("msgpack+zstd", "msgpack+gzip"):
        import msgpack
        raw = msgpack.packb(data, use_bin_type=True)
    else:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")

    if encoding == "msgpack+zstd":
        import zstandard
        cctx = zstandard.ZstdCompressor(level=3)
        return cctx.compress(raw)
    elif encoding in ("msgpack+gzip", "json+gzip"):
        return gzip.compress(raw, compresslevel=6)
    return raw  # pragma: no cover


def _deserialize(payload: bytes, encoding: BinaryEncoding) -> dict:
    """Désérialise un payload bytes selon l'encodage."""
    if encoding == "msgpack+zstd":
        import zstandard
        dctx = zstandard.ZstdDecompressor()
        raw = dctx.decompress(payload)
    elif encoding in ("msgpack+gzip", "json+gzip"):
        raw = gzip.decompress(payload)
    else:  # pragma: no cover
        raw = payload

    if encoding in ("msgpack+zstd", "msgpack+gzip"):
        import msgpack
        return msgpack.unpackb(raw, raw=False)
    else:
        return json.loads(raw.decode("utf-8"))


def graph_to_bytes(graph: IRGraph, encoding: BinaryEncoding | None = None) -> bytes:
    """Sérialise un graphe IR en format binaire compact.

    Args:
        graph: Le graphe IR à sérialiser.
        encoding: Encodage à utiliser. None = meilleur disponible.

    Returns:
        Bytes au format ARCB binaire.
    """
    from src.artcb.ir.models import IRGraph as _IRGraph  # noqa: F401

    if encoding is None:
        encoding = best_encoding()

    data = graph.to_canonical_dict()
    payload = _serialize(data, encoding)

    # En-tête : magic(4) + version(1) + encoding(1) + payload_len(4) = 10 bytes
    header = (
        MAGIC
        + struct.pack("B", FORMAT_VERSION)
        + struct.pack("B", _enc_byte(encoding))
        + struct.pack(">I", len(payload))
    )

    result = header + payload
    logger.debug(
        "graph_to_bytes graph_id=%s encoding=%s json_ref=%d binary=%d ratio=%.1f%%",
        graph.graph_id,
        encoding,
        len(json.dumps(graph.to_canonical_dict(), ensure_ascii=False).encode("utf-8")),
        len(result),
        (1.0 - len(result) / max(1, len(json.dumps(graph.to_canonical_dict(), ensure_ascii=False).encode("utf-8")))) * 100,
    )
    return result


def graph_from_bytes(data: bytes) -> IRGraph:
    """Désérialise un graphe IR depuis le format binaire ARTCB.

    Args:
        data: Bytes au format ARCB binaire.

    Returns:
        IRGraph reconstruit.

    Raises:
        ValueError: si le magic ou la version sont invalides.
    """
    from src.artcb.ir.models import IRGraph

    if len(data) < HEADER_SIZE:
        raise ValueError(f"Données trop courtes : {len(data)} bytes (min {HEADER_SIZE})")

    magic = data[:4]
    if magic != MAGIC:
        raise ValueError(f"Magic invalide : {magic!r} (attendu {MAGIC!r})")

    version = struct.unpack("B", data[4:5])[0]
    if version != FORMAT_VERSION:
        raise ValueError(f"Version binaire inconnue : {version} (supportée : {FORMAT_VERSION})")

    enc_byte = struct.unpack("B", data[5:6])[0]
    encoding = _enc_from_byte(enc_byte)

    payload_len = struct.unpack(">I", data[6:10])[0]
    payload = data[HEADER_SIZE: HEADER_SIZE + payload_len]

    if len(payload) != payload_len:
        raise ValueError(
            f"Payload tronqué : {len(payload)} bytes (attendu {payload_len})"
        )

    graph_dict = _deserialize(payload, encoding)
    return IRGraph.from_dict(graph_dict)


def compression_stats(graph: IRGraph) -> dict:
    """Retourne les statistiques de compression pour un graphe donné.

    Args:
        graph: Le graphe IR à analyser.

    Returns:
        Dict avec tailles et ratios pour chaque encodage disponible.
    """
    json_bytes = json.dumps(graph.to_canonical_dict(), ensure_ascii=False).encode("utf-8")
    json_size = len(json_bytes)

    stats: dict = {"json_size": json_size, "encodings": {}}

    for enc in ("msgpack+zstd", "msgpack+gzip", "json+gzip"):
        enc_typed: BinaryEncoding = enc  # type: ignore[assignment]
        if enc_typed == "msgpack+zstd" and not (_have_msgpack() and _have_zstd()):
            continue
        if enc_typed == "msgpack+gzip" and not _have_msgpack():
            continue
        try:
            b = graph_to_bytes(graph, enc_typed)
            stats["encodings"][enc] = {
                "size": len(b),
                "ratio": round((1.0 - len(b) / max(1, json_size)) * 100, 1),
            }
        except Exception as exc:  # pragma: no cover
            stats["encodings"][enc] = {"error": str(exc)}

    # Toujours ajouter json+gzip comme référence
    if "json+gzip" not in stats["encodings"]:
        b = graph_to_bytes(graph, "json+gzip")
        stats["encodings"]["json+gzip"] = {
            "size": len(b),
            "ratio": round((1.0 - len(b) / max(1, json_size)) * 100, 1),
        }

    return stats
