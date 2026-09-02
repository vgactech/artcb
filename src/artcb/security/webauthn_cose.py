"""Minimal CBOR + COSE P-256 helpers for WebAuthn (no raw biometric storage).

Only the subset needed for `none` attestation and ES256 assertions.
Never logs key material.
"""

from __future__ import annotations

import struct
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

COSE_KTY = 1
COSE_ALG = 3
COSE_CRV = -1
COSE_X = -2
COSE_Y = -3
KTY_EC2 = 2
ALG_ES256 = -7
CRV_P256 = 1


class CborError(ValueError):
    """CBOR object is not a WebAuthn COSE key / attestation map we accept."""


def _major(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([(major << 5) | n])
    if n < 256:
        return bytes([(major << 5) | 24, n])
    if n < 65536:
        return bytes([(major << 5) | 25]) + struct.pack(">H", n)
    if n < 2**32:
        return bytes([(major << 5) | 26]) + struct.pack(">I", n)
    return bytes([(major << 5) | 27]) + struct.pack(">Q", n)


def cbor_dumps(obj: Any) -> bytes:
    if obj is False:
        return b"\xf4"
    if obj is True:
        return b"\xf5"
    if obj is None:
        return b"\xf6"
    if isinstance(obj, int):
        if obj >= 0:
            return _major(0, obj)
        return _major(1, -1 - obj)
    if isinstance(obj, bytes):
        return _major(2, len(obj)) + obj
    if isinstance(obj, str):
        raw = obj.encode("utf-8")
        return _major(3, len(raw)) + raw
    if isinstance(obj, list):
        return _major(4, len(obj)) + b"".join(cbor_dumps(x) for x in obj)
    if isinstance(obj, dict):
        items = [(cbor_dumps(k), cbor_dumps(v)) for k, v in obj.items()]
        items.sort(key=lambda kv: kv[0])
        return _major(5, len(items)) + b"".join(k + v for k, v in items)
    raise CborError(f"unsupported cbor type {type(obj).__name__}")


def _read_len(data: bytes, i: int, extra: int) -> tuple[int, int]:
    if extra < 24:
        return extra, i
    if extra == 24:
        return data[i], i + 1
    if extra == 25:
        return struct.unpack(">H", data[i : i + 2])[0], i + 2
    if extra == 26:
        return struct.unpack(">I", data[i : i + 4])[0], i + 4
    if extra == 27:
        return struct.unpack(">Q", data[i : i + 8])[0], i + 8
    raise CborError("indefinite cbor is not accepted")


def cbor_loads(data: bytes, index: int = 0) -> tuple[Any, int]:
    if index >= len(data):
        raise CborError("truncated cbor")
    b = data[index]
    index += 1
    major, extra = b >> 5, b & 31
    if major == 7:
        if extra == 20:
            return False, index
        if extra == 21:
            return True, index
        if extra == 22:
            return None, index
        raise CborError("unsupported simple/float")
    n, index = _read_len(data, index, extra)
    if major == 0:
        return n, index
    if major == 1:
        return -1 - n, index
    if major == 2:
        return data[index : index + n], index + n
    if major == 3:
        return data[index : index + n].decode("utf-8"), index + n
    if major == 4:
        out = []
        for _ in range(n):
            item, index = cbor_loads(data, index)
            out.append(item)
        return out, index
    if major == 5:
        out: dict[Any, Any] = {}
        for _ in range(n):
            k, index = cbor_loads(data, index)
            v, index = cbor_loads(data, index)
            out[k] = v
        return out, index
    raise CborError(f"unsupported major {major}")


def cose_ec2_p256(public_key: EllipticCurvePublicKey) -> bytes:
    nums = public_key.public_numbers()
    x = nums.x.to_bytes(32, "big")
    y = nums.y.to_bytes(32, "big")
    return cbor_dumps(
        {
            COSE_KTY: KTY_EC2,
            COSE_ALG: ALG_ES256,
            COSE_CRV: CRV_P256,
            COSE_X: x,
            COSE_Y: y,
        }
    )


def public_key_from_cose(cose: bytes) -> EllipticCurvePublicKey:
    obj, _ = cbor_loads(cose)
    if not isinstance(obj, dict):
        raise CborError("cose key is not a map")
    if obj.get(COSE_KTY) != KTY_EC2 or obj.get(COSE_ALG) != ALG_ES256:
        raise CborError("only ES256 P-256 is accepted")
    if obj.get(COSE_CRV) != CRV_P256:
        raise CborError("only P-256 is accepted")
    x = obj.get(COSE_X)
    y = obj.get(COSE_Y)
    if not isinstance(x, bytes) or not isinstance(y, bytes) or len(x) != 32 or len(y) != 32:
        raise CborError("invalid P-256 coordinates")
    nums = ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1())
    return nums.public_key()


def public_key_raw(public_key: EllipticCurvePublicKey) -> bytes:
    return public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def der_from_raw_rs(signature: bytes) -> bytes:
    """WebAuthn sometimes uses raw r||s (64 bytes); cryptography wants DER."""
    if len(signature) == 64:
        r = int.from_bytes(signature[:32], "big")
        s = int.from_bytes(signature[32:], "big")
        return encode_dss_signature(r, s)
    return signature
