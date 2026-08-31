---
name: Replit liboqs runtime
description: Compatibility constraint for activating post-quantum crypto on the Replit Nix environment.
---

On Replit, the Nix-provided liboqs may be older than the installed
liboqs-python binding. The binding must load a matching native liboqs build
from the user-space install before the system library, otherwise imports can
fail on missing symbols and the API silently falls back to Ed25519.

The interactive workspace and an Autoscale deployment do not necessarily
share user-space files. A successful local build therefore does not prove
that the public deployment has liboqs available; the production startup image
must build or provision the matching native library itself.

**Why:** The system package and Python binding can be provisioned independently
and report as installed while remaining ABI-incompatible, and deployment
instances can start with a fresh home directory.

**How to apply:** Keep the native build tag aligned with the binding version,
install it in the persistent user-space OQS directory, and export that
directory through OQS_INSTALL_PATH and LD_LIBRARY_PATH before starting Uvicorn
in every runtime, including Autoscale.