#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== EnergyWise Build Script ==="
echo ""

PYTHON_OK=false
if command -v python3 &>/dev/null; then
    if python3 -c "import yaml" 2>/dev/null; then
        PYTHON_OK=true
    fi
fi

if [ "$PYTHON_OK" = false ]; then
    echo "Installing Python dependency: pyyaml"
    pip3 install pyyaml
fi

echo "Python simulator: OK"

find_llvm_config() {
    if command -v llvm-config &>/dev/null; then
        llvm-config --prefix
        return 0
    fi
    for path in \
        /opt/homebrew/opt/llvm/bin/llvm-config \
        /usr/local/opt/llvm/bin/llvm-config \
        /usr/lib/llvm/bin/llvm-config; do
        if [ -x "$path" ]; then
            "$path" --prefix
            return 0
        fi
    done
    for ver in 20 19 18 17 16 15 14; do
        if [ -x "/usr/lib/llvm-$ver/bin/llvm-config" ]; then
            "/usr/lib/llvm-$ver/bin/llvm-config" --prefix
            return 0
        fi
    done
    return 1
}

LLVM_PREFIX=""
if LLVM_PREFIX=$(find_llvm_config); then
    LLVM_VERSION="$("$LLVM_PREFIX/bin/llvm-config" --version 2>/dev/null || echo "unknown")"
    echo "Found LLVM $LLVM_VERSION at $LLVM_PREFIX"

    BUILD_DIR="$ROOT/src/build"
    if [ ! -d "$BUILD_DIR" ]; then
        mkdir -p "$BUILD_DIR"
    fi

    cd "$BUILD_DIR"
    cmake -DLT_LLVM_INSTALL_DIR="$LLVM_PREFIX" .. 2>&1 | tail -5
    make -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)" 2>&1 | tail -5

    if [ -f "$BUILD_DIR/libEnergyWise.so" ] || [ -f "$BUILD_DIR/libEnergyWise.dylib" ]; then
        echo "LLVM pass plugin: OK"
        LLVM_OK=true
    else
        echo ""
        echo "*** Plugin build did not produce libEnergyWise.so / .dylib"
        echo "*** Possible causes: LLVM version mismatch or missing development headers."
        echo "*** The Python simulator still works — re-run with --mode sim."
        LLVM_OK=false
    fi
else
    echo ""
    echo "LLVM not found. The Python simulator mode works without LLVM."
    echo ""
    echo "To enable native (LLVM pass) mode, install LLVM + Clang development headers:"
    echo "  macOS:  brew install llvm"
    echo "  Ubuntu: sudo apt install llvm-dev clang"
    echo "  Fedora: sudo dnf install llvm-devel clang"
    LLVM_OK=false
fi

echo ""
echo "Build complete."
if [ "$LLVM_OK" = true ]; then
    echo "  - Simulator mode:  python3 src/energywise.py testcases/<file>.c"
    echo "  - Native mode:     python3 src/energywise.py --mode native testcases/<file>.c"
else
    echo "  - Simulator mode:  python3 src/energywise.py testcases/<file>.c"
fi
echo ""
echo "Run all benchmarks:  ./run.sh"