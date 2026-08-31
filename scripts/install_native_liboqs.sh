#!/usr/bin/env bash
# Compile native liboqs into $HOME/_oqs so ML-DSA-65 is available.
# Safe to re-run. Does not print secrets.
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
PREFIX="${OQS_INSTALL_PATH:-$HOME/_oqs}"
SRC="${LIBOQS_SRC:-$HOME/src/liboqs}"
TAG="${LIBOQS_TAG:-0.16.0}"

if [ -f "$PREFIX/lib/liboqs.so" ] || [ -f "$PREFIX/lib64/liboqs.so" ]; then
  echo "liboqs already installed under $PREFIX"
  ls -l "$PREFIX"/lib/liboqs.so* "$PREFIX"/lib64/liboqs.so* 2>/dev/null || true
  exit 0
fi

sudo apt-get update -y
sudo apt-get install -y cmake gcc g++ ninja-build libssl-dev git pkg-config
mkdir -p "$(dirname "$SRC")"
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --branch "$TAG" https://github.com/open-quantum-safe/liboqs.git "$SRC"
fi
cmake -S "$SRC" -B "$SRC/build" \
  -GNinja \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=ON \
  -DOQS_DIST_BUILD=OFF \
  -DOQS_MINIMAL_BUILD="SIG_ml_dsa_65;KEM_ml_kem_768" \
  -DOQS_USE_OPENSSL=ON
cmake --build "$SRC/build" --parallel
cmake --install "$SRC/build"
echo "installed $PREFIX"
ls -l "$PREFIX"/lib/liboqs.so* "$PREFIX"/lib64/liboqs.so* 2>/dev/null || true
