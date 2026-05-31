# EnergyWise

**Static Energy Estimation Pass for RISC-V (rv32imc)**

EnergyWise is an LLVM compiler pass that statically estimates the electrical energy consumption (in nanojoules) of C/C++ programs targeting a RISC-V rv32imc core — without executing the program on real hardware. It ranks functions and basic blocks by their energy contribution, enabling developers to identify where energy is spent and which transformations reduce it.

## Prerequisites

- Python 3.8+ with `pyyaml`
- (Optional) LLVM 15–20 development headers for native mode
- (Windows) CMake + Visual Studio Build Tools for LLVM plugin

```bash
pip3 install pyyaml
```

On macOS/Linux, make the scripts executable:
```bash
chmod +x build.sh run.sh
```

---

## Mode 1: Terminal Only

Use this mode for automated evaluation, CI, or headless environments.

### Run a Single Benchmark

```bash
python3 src/energywise.py testcases/matmul.c
```

### Run All Benchmarks

**Linux / macOS:**
```bash
./run.sh
```

**Windows:**
```cmd
run.bat
```

### Build the LLVM Plugin (Optional)

The Python simulator runs without LLVM. For native mode (higher-fidelity IR-level analysis), build the plugin:

**Linux / macOS:**
```bash
./build.sh
```

Or manually:
```bash
cd src
mkdir -p build && cd build
cmake -DLT_LLVM_INSTALL_DIR=$(llvm-config --prefix) ..
make -j$(nproc)
cd ../..
python3 src/energywise.py --mode native testcases/matmul.c
```

**Windows (Visual Studio):**
```cmd
build.bat
```

Or manually:
```cmd
cd src
mkdir build && cd build
cmake -DLT_LLVM_INSTALL_DIR=C:\LLVM -G "Visual Studio 17 2022" ..
cmake --build . --config Release
cd ..\..
python src\energywise.py --mode native testcases\matmul.c
```

### Run the LLVM Plugin Directly

```bash
# Step 1: Compile C to LLVM IR
clang --target=riscv32-unknown-elf -march=rv32imc -S -emit-llvm -O1 \
    -o testcases/matmul.ll testcases/matmul.c

# Step 2: Run the energy pass
#         (use .so on Linux, .dylib on macOS, .dll on Windows)
opt -load-pass-plugin src/build/libEnergyWise.so \
    -passes=energywise \
    -energy-model=models/rv32imc_energy.yaml \
    -energy-report=reports/matmul.json \
    -disable-output testcases/matmul.ll
```

### Command-Line Options

```
python3 src/energywise.py <source.c> [options]

  --mode sim|native       sim = Python simulator (default), native = LLVM pass
  --model <path>          Path to energy model YAML (default: models/rv32imc_energy.yaml)
  --report <path>         Output JSON report path (default: reports/<name>.json)
  --plugin <path>         Path to LLVM plugin (.so/.dylib/.dll) (native mode)
  --default-trip <N>      Fallback loop trip count (default: 32)
  --pretty                 Pretty-print JSON output
```

---

## Mode 2: Terminal + Web Dashboard

The web dashboard provides an interactive UI with animated pipeline visualization, per-function breakdowns, and upload support for custom C files.

### Start the Dashboard

```bash
python3 webui/server.py
```

Open **http://localhost:8080** in a browser. The dashboard provides:

- **Benchmark tabs** — switch between all 5 test cases with pre-loaded results
- **Upload tab (+Upload)** — drop a `.c` file or paste source code, then click **Analyze**
- **RUN ANALYSIS** — replays the animated pipeline + terminal for the current view
- **DEMO MODE** — auto-cycles through all benchmarks with title cards and a summary

You can also specify a custom port:
```bash
python3 webui/server.py 3000    # http://localhost:3000
```

### How It Works

The dashboard server (`webui/server.py`) serves the HTML UI and exposes two API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/benchmarks` | GET | Lists all built-in test cases with source code |
| `/api/benchmark/<name>` | GET | Runs the simulator on a built-in test case |
| `/api/analyze` | POST | Accepts `{ "source": "...", "filename": "..." }`, runs the simulator, returns JSON |

The server invokes `src/energywise.py --mode sim` under the hood, so no LLVM installation is needed for the dashboard.

---

## Demo

| File | Description |
|------|-------------|
| `Demo/Recording_Demo.mp4` | Video walkthrough: terminal run, web dashboard, and failure case |
| `Demo/WhatsApp Image 2026-05-31 at 19.02.34.jpeg` | Screenshot: terminal output with comparison table |
| `Demo/WhatsApp Image 2026-05-31 at 19.02.35.jpeg` | Screenshot: web dashboard showing energy breakdown |
| `Demo/WhatsApp Image 2026-05-31 at 19.02.35 (1).jpeg` | Screenshot: web dashboard showing optimization recommendation |
| `CD of 6th sem EL.pptx` | Project presentation slides |

---

## Project Structure

```
.
├── README.md
├── DESIGN.md
├── IMPLEMENTATION.md
├── EVALUATION.md
├── build.sh                       Build LLVM plugin + install deps (macOS/Linux)
├── build.bat                      Build LLVM plugin (Windows)
├── run.sh                         Run all benchmarks (macOS/Linux)
├── run.bat                        Run all benchmarks (Windows)
├── CD of 6th sem EL.pptx          Project presentation slides
├── Demo/
│   ├── Recording_Demo.mp4          Video walkthrough of terminal + dashboard
│   ├── WhatsApp Image *.jpeg      Screenshots: terminal output and dashboard
├── src/
│   ├── EnergyEstimationPass.cpp   LLVM new-PM plugin (C++17)
│   ├── CMakeLists.txt             Out-of-tree build for the plugin
│   └── energywise.py              Dual-mode driver (sim + native)
├── models/
│   └── rv32imc_energy.yaml        Instruction energy cost model
├── testcases/
│   ├── fir.c                      FIR filter: naive vs unrolled
│   ├── matmul.c                   Matrix multiply: naive vs cache-tiled
│   ├── scale.c                    Brightness scaler: division vs shift
│   ├── sort.c                     Sorting: bubble vs selection
│   └── dotprod.c                  IIR filter: per-sample vs local-cached
├── webui/
│   ├── index.html                 Interactive dashboard (standalone HTML)
│   └── server.py                  Backend server (POST /api/analyze)
└── reports/                        Generated JSON reports (output)
```

## Test Cases

| File | Variant A (naive) | Variant B (optimized) | Optimization Class |
|------|-------------------|----------------------|---------------------|
| fir.c | fir_naive | fir_unrolled | Loop unrolling |
| matmul.c | matmul_naive | matmul_tiled | Cache tiling |
| scale.c | scale_div | scale_shift | Strength reduction |
| sort.c | sort_bubble | sort_select | Algorithm choice |
| dotprod.c | filter_per_sample | filter_grouped | Local variable caching |

## Output Format

Each run produces a JSON report:

```json
{
  "module": "matmul.c",
  "model": "rv32imc_energy.yaml",
  "total_nj": 12991865.80,
  "functions": [
    {
      "name": "matmul_naive",
      "total_nj": 7749960.32,
      "dynamic_inst_est": 2109504,
      "hotest_block": "matmul_naive.entry",
      "by_class": { "mem_load": 6462668.8, "alu_mul": 642252.8, ... }
    }
  ]
}
```

## Verified Results

| Benchmark | Naive nJ | Optimized nJ | Reduction | Class |
|-----------|----------|-------------|-----------|-------|
| fir.c | 229,128 | 217,879 | 4.9% | Control-flow |
| matmul.c | 7,749,960 | 5,241,905 | 32.4% | Memory |
| scale.c | 75,489 | 50,340 | 33.3% | Arithmetic |
| sort.c | 115,713 | 54,734 | 52.7% | Algorithm choice |
| dotprod.c | 15,780 | 10,266 | 35.0% | Register caching |

## How It Works

The pass walks every Function → BasicBlock → Instruction in the LLVM IR (or, in simulator mode, parses the C source structurally). For each instruction:

1. **Map** the opcode to a RISC-V rv32imc mnemonic and instruction class (ALU, memory, branch, etc.)
2. **Apply** the per-instruction energy cost from the YAML model: `E = E_base + α_switch × E_switch`
3. **Weight** by switching-activity heuristics: constant operands (0.3×), induction variables (0.6×), phi nodes (1.2×)
4. **Add** memory miss penalty: `+ p_miss × E_miss_bonus` where p_miss is estimated by a local reuse-distance heuristic
5. **Multiply** by the loop trip-count product (configurable fallback, default 32 iterations per loop)
6. **Emit** a per-function JSON report with total energy, dynamic instruction count, hottest block, and per-class breakdowns

## Limitations

- The energy model is calibrated against published PULP/Ibex measurements, not silicon. Absolute numbers are reference-relative; rankings are reliable.
- Memory-reuse heuristics are local to a single basic block (inter-block reuse is not tracked).
- The Python simulator is a structural approximation. Use native mode for publication-grade numbers.
- Branch misprediction probability is a static 10% estimate per conditional branch.