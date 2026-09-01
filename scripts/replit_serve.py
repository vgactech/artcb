#!/usr/bin/env python3
"""Bind uvicorn in the same process that imported FastAPI.

Autoscale died when replit_autoscale.sh did:

  python -c 'from src.api.main import app'   # 40s, shim still on :5000
  kill shim
  exec uvicorn src.api.main:app              # imports AGAIN, port empty → 500

This process imports once while ARTCB_SHIM_PID still serves /live, then
kills the shim and calls uvicorn.run(app) immediately (no second import).
"""

from __future__ import annotations

import os
import signal
import time


def _stop_shim(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)


def main() -> None:
    port = int(os.environ.get("ARTCB_PORT", "5000"))
    shim_pid = int(os.environ.get("ARTCB_SHIM_PID", "0") or "0")
    from src.api.main import app
    import uvicorn

    _stop_shim(shim_pid)
    time.sleep(0.05)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
