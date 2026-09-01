#!/usr/bin/env bash
# Compile native liboqs into $HOME/_oqs so ML-DSA-65 is available.
# Safe to re-run. Does not print secrets.
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
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
  ls -l "$PREFIX"/lib/liboqs.so* "$PREFIX"/lib64/liboqs.so* 2>/dev/null || true
  exit 0
fi

run_bounded sudo apt-get update -y
run_bounded sudo apt-get install -y cmake gcc g++ ninja-build libssl-dev git pkg-config
mkdir -p "$(dirname "$SRC")"
if [ ! -d "$SRC/.git" ]; then
  run_bounded git clone --depth 1 --branch "$TAG" https://github.com/open-quantum-safe/liboqs.git "$SRC"
fi
run_bounded cmake -S "$SRC" -B "$SRC/build" \
  -GNinja \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DBUILD_SHARED_LIBS=ON \
  -DOQS_DIST_BUILD=OFF \
  -DOQS_MINIMAL_BUILD="SIG_ml_dsa_65;KEM_ml_kem_768" \
  -DOQS_USE_OPENSSL=ON
run_bounded cmake --build "$SRC/build" --parallel
run_bounded cmake --install "$SRC/build"
echo "installed $PREFIX"
ls -l "$PREFIX"/lib/liboqs.so* "$PREFIX"/lib64/liboqs.so* 2>/dev/null || true
