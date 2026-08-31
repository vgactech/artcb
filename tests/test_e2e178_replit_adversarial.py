"""Phase 178 — V-R01…V-R04 adversarial Replit audit. No wallet init. No secrets."""

from __future__ import annotations

from pathlib import Path

from nacl import signing

from artcb.crypto.hybrid import HYBRID_PREFIX, verify_hybrid
from artcb.crypto_policy import (
    HIGH_VALUE_MESSAGES,
    fallback_still_open,
    public_health_block,
)
from artcb.release import _release_integrity, release_identity

ROOT = Path(__file__).resolve().parents[1]


def test_vr01_pin_mismatch_and_ok(tmp_path: Path, monkeypatch) -> None:
    import artcb.release as rel

    monkeypatch.setattr(rel, "ROOT", tmp_path)
    monkeypatch.setenv("ARTCB_GIT_SHA", "3fd7aadb0b9acce53e59c736d8c5781364daec71")
    monkeypatch.setenv("ARTCB_REPLIT_PIN_SHA", "3fd7aadb0b9a")
    monkeypatch.delenv("ARTCB_GIT_BRANCH", raising=False)
    ident = rel.release_identity()
    assert ident["git_sha"].startswith("3fd7aad")
    assert ident["release_integrity"] == "ok"

    monkeypatch.setenv("ARTCB_REPLIT_PIN_SHA", "deadbeefcafebabe")
    ident2 = rel.release_identity()
    assert ident2["release_integrity"] == "pin_mismatch"


def test_vr01_source_mismatch_env_vs_file(tmp_path: Path, monkeypatch) -> None:
    import artcb.release as rel

    monkeypatch.setattr(rel, "ROOT", tmp_path)
    (tmp_path / ".artcb_release").write_text(
        "ARTCB_GIT_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nARTCB_GIT_BRANCH=x\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARTCB_GIT_SHA", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    monkeypatch.delenv("ARTCB_REPLIT_PIN_SHA", raising=False)
    ident = rel.release_identity()
    assert ident["release_integrity"] == "source_mismatch"
    assert _release_integrity("abc1234", ["abc1234"], "") == "ok"


def test_vr02_health_available_is_not_enforcement() -> None:
    on = public_health_block(True)
    off = public_health_block(False)
    assert on["available"] is True
    assert on["availability_is_not_enforcement"] is True
    assert on["high_value_hybrid_enforced"] is False
    assert on["ed25519_only_still_accepted"] is fallback_still_open()
    assert off["available"] is False
    assert "Ed25519" in off["algorithm"]
    assert off["availability_is_not_enforcement"] is True
    assert "block_append" in HIGH_VALUE_MESSAGES


def test_vr02_ready_503_without_pqc(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_GIT_SHA", "3fd7aadb0b9acce53e59c736d8c5781364daec71")
    import src.artcb.crypto.pqc as pqc_mod

    monkeypatch.setattr(pqc_mod, "pqc_available", lambda: False)
    monkeypatch.setattr(pqc_mod, "_PQC_AVAILABLE", False)
    client = TestClient(create_app())
    ready = client.get("/ready")
    # Bootstrap (no wallet) is 503 for identity; if wallet env is set, 503 for PQC.
    assert ready.status_code == 503
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    payload = health.json()
    assert "pqc" in payload, payload
    pqc = payload["pqc"]
    assert pqc["available"] is False
    assert pqc["availability_is_not_enforcement"] is True
    assert payload.get("release_integrity") in {"ok", "unknown", "source_mismatch", "pin_mismatch"}


def test_vr03_hybrid_and_rejects_bad_mldsa_but_ed25519_only_still_passes() -> None:
    msg = b"vr03-hybrid-vs-legacy"
    sk = signing.SigningKey.generate()
    ed_sig = sk.sign(msg).signature.hex()
    pub = sk.verify_key.encode()
    fake_hybrid = f"{HYBRID_PREFIX}ed25519:{ed_sig}|mldsa65:{'00' * 32}"
    assert (
        verify_hybrid(
            message=msg,
            signature_value=fake_hybrid,
            ed25519_public_key=pub,
            pqc_public_key=b"\x00" * 32,
        )
        is False
    )
    assert (
        verify_hybrid(
            message=msg,
            signature_value=f"ed25519:{ed_sig}",
            ed25519_public_key=pub,
            pqc_public_key=b"\x00" * 32,
        )
        is True
    )


def test_vr04_bootstrap_does_not_write_seed_or_wallet(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    data = tmp_path / "data"
    monkeypatch.setenv("ARTCB_DATA_DIR", str(data))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ARTCB_NODE_WALLET_ADDRESS", raising=False)
    client = TestClient(create_app())
    assert client.get("/live").json()["status"] == "alive"
    wallet_files = list(data.rglob("*")) if data.exists() else []
    joined = " ".join(str(p) for p in wallet_files)
    assert "seed" not in joined.lower()
    assert not any(p.name.endswith(".seed") for p in wallet_files)
    setup = ROOT / "src" / "api" / "setup_routes.py"
    text = setup.read_text(encoding="utf-8")
    assert "seed_hex" in text
    assert "logger.warning" in text
    assert "seed_hex" not in text.split("logger.warning")[1].split(")", 1)[0]


def test_vr04_git_sync_is_architecture_a() -> None:
    body = (ROOT / "scripts" / "replit_start.sh").read_text(encoding="utf-8")
    assert 'reset --hard "origin/' not in body
    assert "refusing git reset --hard" in body
    assert "ARTCB_REPLIT_PIN_SHA" in body
    shim = (ROOT / "scripts" / "replit_live_shim.py").read_text(encoding="utf-8")
    assert '"/ready"' in shim
    assert "503" in shim


def test_d039_recorded() -> None:
    from artcb.devnet_validation import DECISIONS_178, public_lock

    assert "D-039" in DECISIONS_178
    assert "Architecture A" in DECISIONS_178["D-039"]
    lock = public_lock()
    assert lock["decisions_178"]["D-039"]
