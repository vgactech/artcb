"""End-to-end ARTCB user used by a development agent.

C'est-à-dire :

    humain (wallet + mot de passe)
        → POST /auth/login → sess_
        → agent (X-ARTCB-Agent-Id)
        → POST /ai/memo visibility=private
        → GET /auth/me  (adresse réelle, pas la clé opérateur)

Never print password, seed, or session token.
Never create a public converging block (DOMAIN_COMMITMENT) from this path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from artcb.wallet.manager import WalletManager

DEFAULT_WALLET = "artcb-autodev"
DEFAULT_AGENT_ID = "cursor-autodev"


@dataclass
class AutodevIdentity:
    wallet_name: str
    address: str
    created: bool


class AutodevUser:
    """Local wallet + HTTP session for auto-development."""

    def __init__(
        self,
        *,
        wallet_name: str = DEFAULT_WALLET,
        password: str | None = None,
        agent_id: str = DEFAULT_AGENT_ID,
        allow_public: bool = False,
    ) -> None:
        self.wallet_name = wallet_name
        self._password = password or os.environ.get("ARTCB_AUTODEV_PASSWORD") or ""
        self.agent_id = agent_id
        self.allow_public = allow_public or os.environ.get("ARTCB_AUTODEV_ALLOW_PUBLIC") == "1"
        self.session_token: str | None = None
        self.address: str | None = None

    def ensure_wallet(self) -> AutodevIdentity:
        if not self._password or len(self._password) < 8:
            raise ValueError("ARTCB_AUTODEV_PASSWORD required (min 8 chars)")
        wm = WalletManager()
        path = wm.wallet_dir / f"{self.wallet_name}.key"
        if path.exists():
            wallet = wm.load_wallet(name=self.wallet_name, user_password=self._password)
            self.address = wallet.address
            return AutodevIdentity(self.wallet_name, wallet.address, created=False)
        wallet = wm.create_wallet(name=self.wallet_name, user_password=self._password)
        self.address = wallet.address
        return AutodevIdentity(self.wallet_name, wallet.address, created=True)

    def headers(self) -> dict[str, str]:
        if not self.session_token:
            raise RuntimeError("not_logged_in")
        return {
            "Authorization": f"Bearer {self.session_token}",
            "X-ARTCB-Agent-Id": self.agent_id,
        }

    def login(self, client: Any) -> dict[str, Any]:
        r = client.post(
            "/api/v1/auth/login",
            json={"name": self.wallet_name, "password": self._password},
        )
        if getattr(r, "status_code", 0) != 200:
            raise RuntimeError(f"login_failed http={getattr(r, 'status_code', '?')}")
        body = r.json()
        self.session_token = body.get("session_token")
        self.address = body.get("address") or self.address
        return {
            "ok": True,
            "wallet_name": body.get("wallet_name"),
            "address": self.address,
            "token_printed": False,
        }

    def whoami(self, client: Any) -> dict[str, Any]:
        r = client.get("/api/v1/auth/me", headers=self.headers())
        if getattr(r, "status_code", 0) != 200:
            raise RuntimeError(f"whoami_failed http={getattr(r, 'status_code', '?')}")
        return r.json()

    def record(
        self,
        client: Any,
        *,
        content: str,
        memo_type: str = "decision",
        visibility: str = "private",
    ) -> dict[str, Any]:
        if visibility == "public" and not self.allow_public:
            raise RuntimeError("public_memo_forbidden_without_ARTCB_AUTODEV_ALLOW_PUBLIC")
        r = client.post(
            "/api/v1/ai/memo",
            json={
                "content": content,
                "memo_type": memo_type,
                "visibility": visibility,
                "session_id": self.agent_id,
                "inject_context": False,
            },
            headers=self.headers(),
        )
        if getattr(r, "status_code", 0) != 200:
            raise RuntimeError(f"record_failed http={getattr(r, 'status_code', '?')}")
        return r.json()
