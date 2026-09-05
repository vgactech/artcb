"""Non-invasive checks for the optional native liboqs runtime.

Importing ``oqs`` can compile liboqs automatically when its shared library is
missing. That is useful for a manual crypto setup, but it must not happen while
an HTTP application is importing: it can block the healthcheck for minutes.
"""

from __future__ import annotations

import ctypes.util
import os
from pathlib import Path


def native_liboqs_available() -> bool:
    """Return whether a usable liboqs shared library already exists.

    This function deliberately never imports ``oqs``. A false result means the
    application should use its documented fallback and leave PQC installation
    to an explicit/background provisioning step.

    Supports Linux (.so), macOS (.dylib) and the default liboqs-python install
    path ~/._oqs (created automatically by the Python binding on first import).
    """

    if ctypes.util.find_library("oqs") or ctypes.util.find_library("liboqs"):
        return True

    install_root = Path(os.getenv("OQS_INSTALL_PATH", str(Path.home() / "_oqs")))
    candidates = (
        # Linux
        install_root / "lib" / "liboqs.so",
        install_root / "lib64" / "liboqs.so",
        install_root / "lib" / "liboqs.so.0",
        install_root / "lib64" / "liboqs.so.0",
        # macOS (liboqs-python installe dans ~/_oqs par défaut)
        install_root / "lib" / "liboqs.dylib",
        install_root / "lib64" / "liboqs.dylib",
        Path.home() / "_oqs" / "lib" / "liboqs.dylib",
    )
    return any(path.is_file() for path in candidates)
