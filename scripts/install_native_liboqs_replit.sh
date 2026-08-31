#!/usr/bin/env bash
# Compile liboqs 0.16.0 into $HOME/_oqs on Replit (no sudo / no apt).
# Matches liboqs-python 0.16.x so ML-DSA-65 is actually usable.
# Do not print secrets.
set -Eeuo pipefail
PREFIX="${OQS_INSTALL_PATH:-$HOME/_oqs}"
SRC="${LIBOQS_SRC:-$HOME/src/liboqs}"
TAG="${LIBOQS_TAG:-0.16.0}"

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
  git clone --depth 1 --branch "$TAG" https://github.com/open-quantum-safe/liboqs.git "$SRC"
fi
GEN=Unix\ Makefiles
if command -v ninja >/dev/null; then
  GEN=Ninja
fi
cmake -S "$SRC" -B "$SRC/build" \
  -G "$GEN" \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=ON \
  -DOQS_DIST_BUILD=OFF \
  -DOQS_MINIMAL_BUILD="SIG_ml_dsa_65;KEM_ml_kem_768" \
  -DOQS_USE_OPENSSL=ON
cmake --build "$SRC/build" --parallel
cmake --install "$SRC/build"
echo "installed $PREFIX tag=$TAG"
ls -l "$PREFIX"/lib/liboqs.so* "$PREFIX"/lib64/liboqs.so* 2>/dev/null || true
