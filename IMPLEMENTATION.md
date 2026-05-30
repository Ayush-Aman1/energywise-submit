# Implementation Document

## Architecture

EnergyWise consists of two implementations that share the same energy model and produce identical JSON output:

1. **LLVM Pass Plugin** (`src/EnergyEstimationPass.cpp`) — a C++17 out-of-tree LLVM plugin using the new pass manager. This is the primary, high-fidelity implementation.

2. **Python Simulator** (`src/energywise.py`) — a pure-Python structural analyzer that parses C source with regex-based pattern matching. It produces the same JSON schema but with lower fidelity (no real IR, no ScalarEvolution). It exists so the project can be demonstrated without an LLVM installation.

## LLVM Pass: EnergyEstimationPass

### Registration

The pass registers as a module pass under the name `energywise`:

```cpp
extern "C" LLVM_ATTRIBUTE_WEAK PassPluginLibraryInfo llvmGetPassPluginInfo() {
    return {
        LLVM_PLUGIN_API_VERSION, "EnergyWise", LLVM_VERSION_STRING,
        [](PassBuilder &PB) {
            PB.registerPipelineParsingCallback(
                [](StringRef Name, ModulePassManager &MPM, ...) {
                    if (Name == "energywise") {
                        MPM.addPass(EnergyEstimationPass());
                        return true;
                    }
                    return false;
                });
        }
    };
}
```

Usage: `opt -load-pass-plugin ./libEnergyWise.so -passes=energywise ...`

### Analysis Dependencies

The pass requests:
- `LoopAnalysis` — to discover loop nesting and compute trip-count products
- `ScalarEvolutionAnalysis` — to extract constant trip counts from loop headers
- `BranchProbabilityAnalysis` (commented out, reserved for future per-branch misprediction weighting)

### Energy Model Loading

At plugin initialization, the `EnergyModel` class parses the YAML cost model file specified by the `-energy-model` flag. The parser is intentionally minimal (no libyaml dependency) because the model file has a fixed, regular structure. It reads:

- Per-instruction entries: `base_nj`, `switching_nj`, `memory_bonus_miss`, `misprediction_bonus_nj`, and `class`
- IR-level fallback defaults: `default_alu_nj`, `default_mem_nj`, `default_branch_nj`, `default_call_overhead_nj`

### Opcode Mapping

`mapOpcode()` converts each LLVM IR opcode to an `(mnemonic, kind)` pair. LLVM IR does not have a 1:1 mapping to RISC-V instructions, so the mapping is approximate:

| LLVM Opcode | RISC-V Mnemonic | Kind |
|-------------|----------------|------|
| Add | add | alu |
| Mul | mul | alu |
| Load | lw | mem |
| Store | sw | mem |
| Br/Switch | beq | branch |
| Call/Invoke | jalr | call |
| GetElementPtr | add | alu |
| ... | ... | ... |

When the mapped mnemonic is not in the model table, the pass falls back to the IR-default cost for that kind.

### Switching-Activity Heuristic

```cpp
static double switchingMultiplier(const Instruction &I) {
    // Examine each operand:
    //   - Constant  -> multiplier 0.3  (stable toggling)
    //   - PHINode  -> multiplier 1.2  (path-dependent alternation)
    //   - Induction var (defined in same loop, feeds a phi) -> 0.6
    //   - Otherwise -> 1.0
}
```

This heuristic approximates the Hamming distance of operand bits between successive executions of the instruction. Constants produce minimal switching; phi-node operands produce maximal switching because they alternate between incoming paths.

### Memory-Reuse Heuristic

For load/store instructions, the pass looks back at most 16 instructions in the same basic block for a previous access to the same SSA pointer value:

- Same pointer, recent load → p_miss = 0.05 (likely L1 hit)
- Same pointer, recent store → p_miss = 0.03 (likely store-forwarded)
- Otherwise → p_miss = 0.20 (conservative default)

The miss probability times `memory_bonus_miss` (14 nJ for loads, 16 nJ for stores) is added to the instruction energy.

### Analysis Dependencies

The pass operates as a pure module pass without requiring function-level analysis passes (ScalarEvolution, LoopInfo, etc.), which maximizes portability across LLVM versions. Trip counts default to the configurable `-energy-default-trip` parameter (default: 32). Future versions can integrate ScalarEvolution for symbolic trip counts by running the pass after loop simplification.

This design choice was made because the new pass manager's module-pass-to-function-analysis proxy has version-specific behavior that varies across LLVM 15–20. By keeping the pass self-contained, it compiles and runs on any LLVM version without modification.

### Trip-Count Estimation

Each instruction's base energy is scaled by the product of enclosing loop trip counts. The pass uses a configurable default (32, via `-energy-default-trip`) for all loops, ensuring deterministic and portable behavior. This default produces correct *relative* rankings even though absolute numbers may differ from profile-guided analysis.

### JSON Output

After processing all functions, the pass writes a `json::Object` with:

```json
{
    "module": "<module name>",
    "model": "<model path>",
    "total_nj": <float>,
    "functions": [
        {
            "name": "<function name>",
            "total_nj": <float>,
            "dynamic_inst_est": <int>,
            "hotest_block": "<block name>",
            "hotest_block_nj": <float>,
            "by_class": { "<class>": <energy_nj>, ... }
        }
    ]
}
```

Output path is controlled by `-energy-report` (default: `energy_report.json`).

## Python Simulator

The simulator (`energywise.py --mode sim`) mirrors the pass logic in pure Python:

1. Strips C comments and resolves `#define` macros
2. Identifies function definitions with regex
3. For each function body, recursively detects nested `for`/`while` loops with literal bounds
4. Within each code segment, counts:
   - Arithmetic operators → ALU energy
   - Array indexing / pointer dereferences → memory energy + miss penalty
   - Function calls → call overhead
   - `if`/`switch` statements → branch energy
5. Multiplies by loop trip counts and nesting heuristic
6. Applies cache-locality heuristic: small inner loops (≤32 iterations) get reduced miss probability

The simulator produces the same JSON schema, enabling the test cases to be evaluated without LLVM.

## Build System

```text
src/CMakeLists.txt
├── cmake_minimum_required(VERSION 3.13.4)
├── project(EnergyWise LANGUAGES CXX)
├── find_package(LLVM 15|16|17)
├── add_library(EnergyWise SHARED EnergyEstimationPass.cpp)
└── target_link_libraries(LLVMCore LLVMSupport LLVMAnalysis LLVMPasses)
```

The plugin is built as a shared library (`libEnergyWise.so` / `libEnergyWise.dylib`) with `-fno-rtti` matching the LLVM build, and is loaded by `opt` at runtime via `-load-pass-plugin`.

## Command-Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `-energy-model` | `models/rv32imc_energy.yaml` | Path to YAML cost model |
| `-energy-report` | `energy_report.json` | Output JSON report path |
| `-energy-default-trip` | `32` | Fallback loop trip count |