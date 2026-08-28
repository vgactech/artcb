"""ctypes bindings to libartcb_chain (C).

Hash ABI:
- v1 (historic): index|ts|prev|graph|merkle|pol
- v2: same plus |v2|<economic_root> when EconomicRoot is present
Old blocks without hash_version/economic_root still verify with v1.
"""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path

logger = logging.getLogger("artcb.chain.ffi")

ARTCB_HASH_HEX_LEN = 65
ARTCB_MAX_ERR = 512
HASH_VERSION_V1 = 1
HASH_VERSION_V2 = 2

_LIB: ctypes.CDLL | None = None


def _library_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "c" / "libartcb_chain.so"


def load_library() -> ctypes.CDLL:
    global _LIB
    if _LIB is not None:
        return _LIB
    path = _library_path()
    if not path.exists():
        raise FileNotFoundError(
            f"libartcb_chain.so not built — run: make -C {path.parent}"
        )
    _LIB = ctypes.CDLL(str(path))
    _LIB.artcb_sha256_hex.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    _LIB.artcb_sha256_hex.restype = ctypes.c_int
    _LIB.artcb_build_canonical.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_double,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    _LIB.artcb_build_canonical.restype = ctypes.c_int
    _LIB.artcb_hash_canonical.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _LIB.artcb_hash_canonical.restype = ctypes.c_int
    _LIB.artcb_verify_chain_file.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t]
    _LIB.artcb_verify_chain_file.restype = ctypes.c_int
    _LIB.artcb_count_blocks.argtypes = [ctypes.c_char_p]
    _LIB.artcb_count_blocks.restype = ctypes.c_int
    if hasattr(_LIB, "artcb_build_canonical_v2"):
        _LIB.artcb_build_canonical_v2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_double,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_size_t,
        ]
        _LIB.artcb_build_canonical_v2.restype = ctypes.c_int
    if hasattr(_LIB, "artcb_hash_abi_version"):
        _LIB.artcb_hash_abi_version.argtypes = []
        _LIB.artcb_hash_abi_version.restype = ctypes.c_int
    logger.debug("Loaded C library path=%s v2=%s", path, has_economic_root_abi())
    return _LIB


def has_economic_root_abi() -> bool:
    try:
        lib = load_library()
    except FileNotFoundError:
        return False
    return hasattr(lib, "artcb_build_canonical_v2")


def hash_abi_version() -> int:
    if not has_economic_root_abi():
        return HASH_VERSION_V1
    lib = load_library()
    if hasattr(lib, "artcb_hash_abi_version"):
        return int(lib.artcb_hash_abi_version())
    return HASH_VERSION_V2


def sha256_hex(data: str) -> str:
    lib = load_library()
    out = ctypes.create_string_buffer(ARTCB_HASH_HEX_LEN)
    encoded = data.encode("utf-8")
    rc = lib.artcb_sha256_hex(encoded, len(encoded), out)
    if rc != 0:
        raise RuntimeError("artcb_sha256_hex failed")
    return out.value.decode("ascii")


def _hash_canonical(canonical: bytes) -> str:
    lib = load_library()
    out = ctypes.create_string_buffer(ARTCB_HASH_HEX_LEN)
    rc = lib.artcb_hash_canonical(canonical, out)
    if rc != 0:
        raise RuntimeError("artcb_hash_canonical failed")
    return out.value.decode("ascii")


def build_block_hash(
    index: int,
    timestamp: str,
    prev_hash: str,
    graph_root: str,
    merkle_root: str,
    pol_score: float,
    economic_root: str | None = None,
) -> str:
    """Hash a block. Pass economic_root for v2; omit/empty keeps v1 (old blocks)."""
    lib = load_library()
    canonical = ctypes.create_string_buffer(16384)
    root = (economic_root or "").strip()
    if root and has_economic_root_abi():
        rc = lib.artcb_build_canonical_v2(
            index,
            timestamp.encode("utf-8"),
            prev_hash.encode("utf-8"),
            graph_root.encode("utf-8"),
            merkle_root.encode("utf-8"),
            pol_score,
            root.encode("utf-8"),
            canonical,
            16384,
        )
        if rc != 0:
            raise RuntimeError("artcb_build_canonical_v2 failed")
        digest = _hash_canonical(canonical.value)
        logger.debug("C v2 hash index=%s eco=%s -> %s", index, root[:12], digest[:16])
        return digest
    rc = lib.artcb_build_canonical(
        index,
        timestamp.encode("utf-8"),
        prev_hash.encode("utf-8"),
        graph_root.encode("utf-8"),
        merkle_root.encode("utf-8"),
        pol_score,
        canonical,
        16384,
    )
    if rc != 0:
        raise RuntimeError("artcb_build_canonical failed")
    digest = _hash_canonical(canonical.value)
    if root and not has_economic_root_abi():
        logger.debug(
            "C ABI lacks v2 — v1 hash used; caller must mix EconomicRoot into merkle"
        )
    return digest


def verify_chain_file(path: Path) -> tuple[bool, str]:
    lib = load_library()
    err = ctypes.create_string_buffer(ARTCB_MAX_ERR)
    rc = lib.artcb_verify_chain_file(str(path).encode("utf-8"), err, ARTCB_MAX_ERR)
    message = err.value.decode("utf-8", errors="replace")
    return rc == 0, message


def count_blocks(path: Path) -> int:
    lib = load_library()
    if not path.exists():
        return 0
    return int(lib.artcb_count_blocks(str(path).encode("utf-8")))
