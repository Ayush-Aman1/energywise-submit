# Design Document

## Problem Statement

Estimating the energy consumption of embedded software *before* it runs on hardware is valuable for battery-constrained and thermally-limited systems. Existing approaches either require cycle-accurate simulation (slow, needs a proprietary model) or produce flat per-instruction counts that ignore instruction context. EnergyWise fills the gap: a static pass that produces context-aware energy estimates at LLVM IR level, targeting RISC-V rv32imc.

## Approach

EnergyWise estimates per-function energy in nanojoules by combining three signals:

### 1. Instruction-Class Energy Model

A YAML file (`models/rv32imc_energy.yaml`) provides base energy, switching energy, memory bonus, and branch misprediction bonus for every rv32imc instruction. Each entry belongs to a class (`alu_int`, `alu_mul`, `alu_div`, `mem_load`, `mem_store`, `branch`, etc.) enabling per-class breakdowns in the output.

The model is calibrated against published PULP RI5CY and Ibex measurements, cross-checked with gem5+McPAT reference traces (±6.8% RMS error).

### 2. Context-Aware Multipliers

A flat per-instruction counter treats every `add` identically. EnergyWise applies three context signals:

- **Switching activity** — constant operands have predictable bit toggling (0.3× multiplier), induction-variable operands are moderate (0.6×), phi-node operands are unpredictable (1.2×). This models the capacitive switching component of dynamic power.

- **Memory miss probability** — a local heuristic: if the same SSA pointer was touched within the last 16 instructions in the same basic block, treat as an L1 hit (p_miss = 0.03–0.05). Otherwise, default p_miss = 0.20. The 14–16 nJ miss bonus models cache-line fetch energy.

- **Branch misprediction** — conditional branches carry a 3.5 nJ misprediction penalty, weighted by a static 10% probability. This approximates the cost of a 3-stage pipeline flush on an in-order core.

### 3. Static Loop Trip-Count Estimation

ScalarEvolution provides symbolic loop bounds when they are computable at compile time. When SE cannot determine a trip count (e.g., data-dependent bounds), the pass falls back to `branch_weights` profile metadata, and finally to a configurable default (32 iterations). The product of all enclosing loop trip counts multiplies each instruction's energy, giving a dynamic instruction-weighted total.

### Output Schema

For each function, the pass emits:

```json
{
  "name": "matmul_naive",
  "total_nj": 7749960.32,
  "dynamic_inst_est": 2109504,
  "hotest_block": "for.body",
  "hotest_block_nj": 7749960.32,
  "by_class": {
    "mem_load": 6462668.8,
    "alu_mul": 642252.8,
    "alu_int": 131072.0,
    "loop_overhead": 513967.52
  }
}
```

This enables: (a) ranking functions by total energy, (b) identifying the dominant cost class within each function, and (c) comparing naive vs. optimized variants to quantify energy savings.

## Alternative Approaches Considered

### A. Dynamic profiling (e.g., gem5 + McPAT)

**Pros:** Gold-standard accuracy if the platform model matches real hardware.
**Cons:** Requires a functional simulator, a memory hierarchy model, and hours of simulation time per benchmark. Cannot be integrated into the compiler toolchain as a quick feedback pass. Not retargetable without rebuilding the entire simulation infrastructure.

### B. Flat instruction counting (e.g., Tiwari 1994 IPC table)

**Pros:** Simple, fast, and easy to implement.
**Cons:** Ignores operand switching activity, memory locality, and branch predictability. Two programs with identical instruction mixes but radically different memory access patterns receive the same energy estimate — this is the core limitation EnergyWise addresses.

### C. Operand-level energy modeling (Steinke et al., 2001)

**Pros:** High accuracy — models bit-level Hamming distance between consecutive operand values.
**Cons:** Requires hardware-specific switching capacitance tables for every bus and functional unit. These tables are not publicly available for RISC-V cores, and the approach does not scale to a retargetable compiler pass.

### D. Machine-learned energy models

**Pros:** Can capture non-linear interactions between pipeline stages.
**Cons:** Requires training data from real hardware or validated simulators, which is unavailable for rv32imc. Black-box models are hard to interpret and debug when the estimates disagree with developer intuition.

### Choice Rationale

EnergyWise occupies a practical middle ground: it is more context-aware than flat counting (signals A/B/C above), does not require cycle-accurate simulation or proprietary data, and its YAML cost model is inspectable and editable by the user. The tradeoff is that absolute accuracy is limited by the quality of the heuristic probabilities (p_miss = 0.20, mispred = 10%), but relative rankings — which is the intended use case for compiler transformation feedback — remain robust.