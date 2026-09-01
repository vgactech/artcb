#!/usr/bin/env bash
# Compile liboqs 0.16.0 into $HOME/_oqs on Replit (no sudo / no apt).
# Matches liboqs-python 0.16.x so ML-DSA-65 is actually usable.
# Do not print secrets.
set -Eeuo pipefail
PREFIX="${OQS_INSTALL_PATH:-$HOME/_oqs}"
SRC="${LIBOQS_SRC:-$HOME/src/liboqs}"
TAG="${LIBOQS_TAG:-0.16.0}"
PQC_TIMEOUT="${ARTCB_PQC_TIMEOUT:-300}"

run_bounded() {
  if command -v timeout >/dev/null 2>&1; then
    timeout --foreground --signal=TERM --kill-after=10s "${PQC_TIMEOUT}s" "$@"
  else
    "$@"
  fi
}

if [ -f "$PREFIX/lib/liboqs.so" ] || [ -f "$PREFIX/lib64/liboqs.so" ]; then
  echo "liboqs already installed under $PREFIX"
  exit 0
fi
if ! command -v cmake >/dev/null || ! command -v gcc >/dev/null; then
  echo "cmake/gcc missing — cannot compile native liboqs 0.16.0"
  exit 2
fi
mkdir -p "$(dirname "$SRC")"
if [ ! -d "$SRC/.git" ]; then
  run_bounded git clone --depth 1 --branch "$TAG" https://github.com/open-quantum-safe/liboqs.git "$SRC"
fi
GEN=Unix\ Makefiles
if command -v ninja >/dev/null; then
  GEN=Ninja
fi
run_bounded cmake -S "$SRC" -B "$SRC/build" \
  -G "$GEN" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=ON \
  -DOQS_DIST_BUILD=OFF \
  -DOQS_MINIMAL_BUILD="SIG_ml_dsa_65;KEM_ml_kem_768" \
  -DOQS_USE_OPENSSL=ON
run_bounded cmake --build "$SRC/build" --parallel
run_bounded cmake --install "$SRC/build"
echo "installed $PREFIX tag=$TAG"
ls -l "$PREFIX"/lib/liboqs.so* "$PREFIX"/lib64/liboqs.so* 2>/dev/null || true
