"""R348b — HTTP raw-body rejects seed_hex even if challenge invalid."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARTCB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ARTCB_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARTCB_ALLOW_MULTI_WALLET", "true")
    return TestClient(create_app())


def test_associate_rejects_seed_hex_in_raw_body(client: TestClient) -> None:
    r = client.post(
        "/api/v1/identity/user-node/associate",
        json={
            "user_address": "artcb1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "user_public_key_hex": "ab" * 32,
            "challenge": "a" * 32,
            "signature_hex": "b" * 64,
            "role": "client",
            "seed_hex": "deadbeef",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"].startswith("private_key_fields_forbidden")
