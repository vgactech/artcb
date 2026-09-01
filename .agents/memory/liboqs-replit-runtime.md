---
name: Replit liboqs runtime
description: Compatibility constraint for activating post-quantum crypto on the Replit Nix environment.
---

On Replit, the Nix-provided liboqs may be older than the installed
liboqs-python binding. The binding must load a matching native liboqs build
from the user-space install before the system library, otherwise imports can
fail on missing symbols and the API silently falls back to Ed25519.

**Why:** The system package and Python binding can be provisioned independently
and report as installed while remaining ABI-incompatible.

**How to apply:** Keep the native build tag aligned with the binding version,
install it in the persistent user-space OQS directory, and export that
directory through OQS_INSTALL_PATH and LD_LIBRARY_PATH before starting Uvicorn.