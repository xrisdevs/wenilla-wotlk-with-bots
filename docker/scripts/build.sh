#!/usr/bin/env bash
# Configure, build and install TrinityCore from /src into /opt/trinitycore using a persistent /build dir.
set -euo pipefail
JOBS="${JOBS:-6}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
if [ ! -f /build/CMakeCache.txt ] || [ "${RECONFIGURE:-1}" = 1 ]; then
  cmake -S /src -B /build -G Ninja \
    -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
    -DCMAKE_INSTALL_PREFIX=/opt/trinitycore \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DTOOLS=1 -DSCRIPTS=static -DWITH_WARNINGS=0 -DCOPY_CONF=1
fi
cmake --build /build -j"$JOBS"
if [ "${INSTALL:-1}" = 1 ]; then cmake --install /build; else echo "skipping install (INSTALL=0)"; fi
echo "BUILD OK: $(date)"
ls -la /opt/trinitycore/bin
