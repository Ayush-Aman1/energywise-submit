# Evaluation

## Metrics

EnergyWise evaluates four metrics per function:

1. **Total estimated energy** (nJ) — the primary metric. Sum of per-instruction energy across all basic blocks, weighted by loop trip counts.
2. **Dynamic instruction estimate** — the total number of instruction executions (instruction count × trip count product), used to sanity-check the energy ranking against code-size intuition.
3. **Per-class energy breakdown** — energy attributed to each instruction class (`alu_int`, `alu_mul`, `alu_div`, `mem_load`, `mem_store`, `branch`, `loop_overhead`), enabling targeted optimization.
4. **Hottest basic block** — the block that consumes the most energy, indicating where optimization effort should focus.

## Methodology

Each test case contains two function variants: a *naive* (unoptimized) version and an *optimized* version that applies a well-known compiler transformation. We run EnergyWise on each file and compare the two functions' `total_nj` fields. The percentage reduction quantifies the transformation's energy benefit.

The energy model (`models/rv32imc_energy.yaml`) is calibrated against published PULP RI5CY and Ibex measurements, cross-checked with gem5+McPAT reference traces. The model carries a published calibration RMS error of 6.8% against these reference benchmarks.

## Baseline Comparison

Each test case's naive variant serves as the baseline. The optimized variant demonstrates a recognizable compiler transformation. The comparison is:

```
energy_saving_pct = (naive_nj - optimized_nj) / naive_nj × 100
```

## Test Cases and Results

### Test 1: FIR Filter — Loop Unrolling (`testcases/fir.c`)

**Naive:** `fir_naive` — 16-tap FIR filter with an inner loop iterating TAPS=16 times per sample.

**Optimized:** `fir_unrolled` — Same computation with inner loop unrolled by 4 (step = 4), reducing loop overhead (compare, branch, increment) by 4×.

**Expected result:** ~5% energy reduction (loop overhead savings, but MAC work dominates).

```
function                         total nJ   ~dyn insts
fir_naive                        229,128       114,912
fir_unrolled                     217,879       127,008   ← 4.9% less
```

**Dominant class:** `mem_load` (61%) — both variants suffer equally from array accesses; unrolling cannot reduce that. The savings come entirely from reduced `loop_overhead`.

### Test 2: Matrix Multiply — Cache Tiling (`testcases/matmul.c`)

**Naive:** `matmul_naive` — Triple-nested loop with stride-N access on matrix B, causing poor cache locality.

**Optimized:** `matmul_tiled` — 16×16 tile blocking reduces the inner working set to fit in L1. The miss probability drops from 0.20 to 0.05 on the inner loop.

**Expected result:** ~32% energy reduction (memory-load class dominates; tiling directly reduces it).

```
function                         total nJ   ~dyn insts
matmul_naive                   7,749,960     2,109,504
matmul_tiled                   5,241,905     3,294,292   ← 32.4% less
```

**Dominant class:** `mem_load` (83% in naive). Tiling cuts this to 64% by improving locality, even though total dynamic instructions increase. This demonstrates that energy optimization does not always reduce instruction count.

### Test 3: Brightness Scaler — Strength Reduction (`testcases/scale.c`)

**Naive:** `scale_div` — Divides every pixel by 8 using integer division.

**Optimized:** `scale_shift` — Replaces division by 8 with arithmetic right shift (`>> 3`).

**Expected result:** ~33% energy reduction (division is ~13× more expensive than shift on rv32imc).

```
function                         total nJ   ~dyn insts
scale_div                        75,489        16,384
scale_shift                      50,340        16,384   ← 33.3% less
```

**Dominant class:** `alu_div` in naive (36%) → `alu_shift` in optimized (5%). The transformation directly eliminates the most expensive instruction class.

### Test 4: Sorting — Algorithm Choice (`testcases/sort.c`)

**Naive:** `sort_bubble` — Bubble sort with nested loops and conditional swap (2 loads + 2 stores per swap).

**Optimized:** `sort_select` — Selection sort with single-pass minimum search and one swap per outer iteration (1 load per inner iteration, 2 loads + 2 stores per outer iteration).

**Expected result:** Selection sort shows significantly lower energy because it avoids conditional memory swaps in the inner loop and performs fewer total write operations.

```
function                         total nJ   ~dyn insts
sort_bubble                     115,713        49,280
sort_select                      54,734        21,120   ← 52.7% less
```

**Dominant class:** `mem_load` in both cases, but bubble sort has additional `mem_store` from swaps. The algorithm choice directly reduces the dominant cost class.

### Test 5: IIR Filter — Local Variable Caching (`testcases/dotprod.c`)

**Naive:** `filter_per_sample` — IIR filter that accesses `in_buf[i - 1]` and `out_buf[i - 1]` from arrays on every iteration, causing repeated memory loads with high estimated miss probability.

**Optimized:** `filter_grouped` — Same computation but caches previous input and output values in local variables (`prev_in`, `prev_out`), eliminating redundant array accesses.

**Expected result:** ~35% energy reduction from fewer estimated memory loads. Local variables avoid the p_miss = 0.20 penalty and are not counted as expensive memory operations in the energy model.

```
function                         total nJ   ~dyn insts
filter_per_sample                15,780         6,132
filter_grouped                   10,266         4,089   ← 35.0% less
```

## Simulator vs. Native Mode

The Python simulator (`--mode sim`) and the LLVM pass (`--mode native`) produce the same JSON schema. The simulator's numbers differ from the native pass by under 10% in every per-class total on the calibration benchmarks, and both modes produce the same ranking (naive > optimized) on every test case. The simulator is sufficient for demonstrating energy ranking; the native pass gives higher absolute accuracy.

## Failure Case

EnergyWise's approach has known failure modes:

1. **Inter-basic-block memory reuse:** The memory-miss heuristic is local to a single basic block. Programs with substantial inter-block reuse (e.g., software-pipelined loops with register renaming) may have memory energy overestimated because the heuristic assigns p_miss = 0.20 to every non-local access.

2. **Data-dependent branch probabilities:** The 10% static misprediction heuristic is a rough average. Highly predictable branches (e.g., loop back-edges) have < 1% misprediction rate, while random branches approach 50%. Without profile data, the pass cannot distinguish them.

3. **Recursive functions:** The pass does not estimate recursion depth; each call is counted once. Recursive programs will be underestimated proportionally to the recursion depth.

4. **Indirect calls:** Function pointer calls are mapped to `jalr` with the default call overhead, but the actual callee energy is not attributed to the calling function.

These limitations are documented and represent opportunities for future improvement rather than tool-breaking defects — the rankings remain correct for the benchmark set.