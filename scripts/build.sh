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

LLVM_OK=false
if command -v llvm-config &>/dev/null; then
    LLVM_VERSION=$(llvm-config --version 2>/dev/null | head -c3)
    echo "Found LLVM $LLVM_VERSION"

    BUILD_DIR="$ROOT/src/build"
    if [ ! -d "$BUILD_DIR" ]; then
        mkdir -p "$BUILD_DIR"
    fi

    cd "$BUILD_DIR"
    cmake -DLT_LLVM_INSTALL_DIR="$(llvm-config --prefix)" .. 2>&1 | tail -5
    make -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)" 2>&1 | tail -5

    if [ -f "$BUILD_DIR/libEnergyWise.so" ] || [ -f "$BUILD_DIR/libEnergyWise.dylib" ]; then
        echo "LLVM pass plugin: OK"
        LLVM_OK=true
    else
        echo "LLVM pass plugin: build attempted but library not found"
        echo "The Python simulator will still work fully."
    fi
else
    echo "LLVM not found (llvm-config not in PATH)"
    echo "The Python simulator mode works without LLVM."
    echo "For native mode, install LLVM 15/16/17 development headers."
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