#!/usr/bin/env python3
"""Write Doppler SSH_PRIVATE_KEY to ~/.ssh/artcb_ovh_deploy (mode 600).

Never prints the key. Requires DOPPLER_TOKEN. Default project/config:
artcb-blockchain / dev.

Exit 0 if the file was written. Exit 2 if the secret is missing.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT = os.environ.get("DOPPLER_PROJECT", "artcb-blockchain")
CONFIG = os.environ.get("DOPPLER_CONFIG", "dev")
SECRET_NAME = os.environ.get("ARTCB_DOPPLER_SSH_SECRET", "SSH_PRIVATE_KEY")
DEST = Path(os.environ.get("ARTCB_SSH_KEY", str(Path.home() / ".ssh" / "artcb_ovh_deploy")))


def main() -> int:
    token = os.environ.get("DOPPLER_TOKEN", "").strip()
    if not token:
        print("DOPPLER_TOKEN absent — cannot load SSH key from Doppler", file=sys.stderr)
        return 2
    url = (
        "https://api.doppler.com/v3/configs/config/secrets"
        f"?project={PROJECT}&config={CONFIG}"
    )
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Doppler HTTP {exc.code} (token never printed)", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError) as exc:
        print(f"Doppler network error: {type(exc).__name__}", file=sys.stderr)
        return 1
    secrets = payload.get("secrets") or {}
    meta = secrets.get(SECRET_NAME) or {}
    raw = (meta.get("computed") or meta.get("raw") or "")
    if not raw.strip():
        print(f"Doppler secret {SECRET_NAME} missing or empty", file=sys.stderr)
        return 2
    if "BEGIN" not in raw or "PRIVATE" not in raw:
        print(f"Doppler secret {SECRET_NAME} is not a PEM/OpenSSH private key", file=sys.stderr)
        return 1
    norm = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not norm.endswith("\n"):
        norm += "\n"
    DEST.parent.mkdir(mode=0o700, exist_ok=True)
    DEST.write_text(norm, encoding="utf-8")
    DEST.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"wrote {DEST} mode=600 bytes={DEST.stat().st_size} (key not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
