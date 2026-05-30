#!/usr/bin/env python3
"""
EnergyWise driver.

Two modes:

  1. Native mode (requires LLVM + riscv32-clang):
        python energywise.py --native bench/fir.c
     Compiles -> IR -> opt-with-plugin -> JSON report.

  2. Simulator mode (pure Python, zero external deps beyond PyYAML):
        python energywise.py --sim bench/fir.c
     Parses the C file with a tiny-lexer + structural analyzer, imitates
     what the LLVM pass would do. Fidelity is ~lower, but it works on
     any laptop for the demo and produces the same JSON schema.
"""

from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

try:
    import yaml  # PyYAML
except ImportError:
    print("Install pyyaml:  pip install pyyaml", file=sys.stderr); sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "rv32imc_energy.yaml"
REPORTS_DIR = ROOT / "reports"


# -----------------------------------------------------------------------------
# Model
# -----------------------------------------------------------------------------
@dataclass
class CostRow:
    base_nj: float = 0.0
    switching_nj: float = 0.0
    memory_bonus_miss: float = 0.0
    misprediction_bonus_nj: float = 0.0
    iclass: str = "unknown"


class EnergyModel:
    def __init__(self, path: Path):
        self.path = path
        with open(path) as f:
            self.raw = yaml.safe_load(f)
        self.meta = self.raw.get("meta", {})
        self.table: Dict[str, CostRow] = {}
        for mnem, row in self.raw.get("instructions", {}).items():
            self.table[mnem] = CostRow(
                base_nj=row.get("base_nj", 0.0),
                switching_nj=row.get("switching_nj", 0.0),
                memory_bonus_miss=row.get("memory_bonus_miss", 0.0),
                misprediction_bonus_nj=row.get("misprediction_bonus_nj", 0.0),
                iclass=row.get("class", "unknown"),
            )
        self.fallback = self.raw.get("ir_fallback", {})

    def cost(self, mnemonic: str) -> CostRow:
        return self.table.get(mnemonic, CostRow())


# -----------------------------------------------------------------------------
# Native mode: thin shell around opt
# -----------------------------------------------------------------------------
def _find_tool(name: str) -> str:
    for candidate in [
        name,
        f"/opt/homebrew/opt/llvm/bin/{name}",
        f"/usr/local/opt/llvm/bin/{name}",
    ]:
        if Path(candidate).is_file() or shutil.which(candidate):
            return candidate
    return name


def run_native(src: Path, model: Path, out_report: Path, plugin: Path) -> dict:
    ll = src.with_suffix(".ll")
    clang = _find_tool("clang")
    opt = _find_tool("opt")
    subprocess.check_call([
        clang, "--target=riscv32-unknown-elf",
        "-march=rv32imc", "-S", "-emit-llvm",
        "-O1", "-o", str(ll), str(src)
    ])
    subprocess.check_call([
        opt, f"-load-pass-plugin={plugin}",
        "-passes=energywise",
        f"-energy-model={model}",
        f"-energy-report={out_report}",
        "-disable-output", str(ll)
    ])
    return json.loads(out_report.read_text())


# -----------------------------------------------------------------------------
# Simulator mode: a deliberately-small C "analyzer".
#
# We don't try to be a real compiler frontend. We just count the structural
# signals the pass would use on IR, at the source level:
#
#   * arithmetic ops        -> ALU energy
#   * array / pointer deref -> memory energy (+miss penalty if stride-heavy)
#   * function calls        -> call overhead
#   * loops                 -> multiplier (uses literal bounds when present,
#                              else falls back to energy-default-trip)
#   * if/switch             -> branch energy
#
# The numbers won't match opt output to 6 digits; they'll match in shape,
# which is what the UI visualizations compare.
# -----------------------------------------------------------------------------
ARITH_RE   = re.compile(r'[+\-*/%]=?|<<|>>|&|\||\^')
CALL_RE    = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
DEREF_RE   = re.compile(r'(\*\s*[A-Za-z_]\w*|\[[^\]]+\])')
FOR_RE     = re.compile(
    r'\bfor\s*\(\s*\w+\s*\w+\s*=\s*(\-?\d+)\s*;\s*\w+\s*[<>]=?\s*(\-?\d+)\s*;\s*'
    r'\w+\s*(?:\+\+|--|\+=\s*(\d+)|-=\s*(\d+))'
)
WHILE_RE   = re.compile(r'\bwhile\s*\(')
IF_RE      = re.compile(r'\bif\s*\(')
SWITCH_RE  = re.compile(r'\bswitch\s*\(')
FUNCDEF_RE = re.compile(r'^\s*(?:[\w\*\s]+?)\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{', re.M)
_C_KEYWORDS = {"if", "for", "while", "switch", "return", "else", "do",
               "sizeof", "typedef", "struct", "union", "enum", "case"}

MUL_CALL_HINTS = {"pow", "multiply", "mul", "dot"}
DIV_CALL_HINTS = {"div", "mod"}


@dataclass
class SimFunction:
    name: str
    total_nj: float = 0.0
    dynamic_inst_est: int = 0
    hotest_block: str = ""
    hotest_block_nj: float = 0.0
    by_class: Dict[str, float] = field(default_factory=dict)


def _energy_for(mnem: str, model: EnergyModel, mem_miss_p: float = 0.0) -> (float, str):
    c = model.cost(mnem)
    if c.base_nj == 0.0:
        # fallback
        kind = "alu"
        if mnem in ("lw", "sw", "lb", "lh", "sb", "sh"):
            kind = "mem"
        if mnem.startswith(("b", "j")):
            kind = "branch"
        e = {"alu":  model.fallback.get("default_alu_nj", 0.42),
             "mem":  model.fallback.get("default_mem_nj", 1.85),
             "branch": model.fallback.get("default_branch_nj", 0.55)}[kind]
        return e, kind
    energy = c.base_nj + c.switching_nj
    if mem_miss_p > 0 and c.memory_bonus_miss > 0:
        energy += mem_miss_p * c.memory_bonus_miss
    return energy, c.iclass


def _analyze_body(body: str, model: EnergyModel, default_trip: int,
                  block_label: str, miss_prob: float = 0.20) -> dict:
    """Analyze one contiguous block of C code (a function body or a loop body).

    `miss_prob` is the probability that memory accesses inside this block miss
    in the L1 cache. Callers pass a smaller value when the block sits inside
    a tiled/blocked loop (better locality).
    """
    acc = {"total": 0.0, "dyn": 0, "by_class": {}}

    def add(mnem: str, multiplier: int = 1, mem_miss: float = 0.0):
        e, cls = _energy_for(mnem, model, mem_miss)
        e *= multiplier
        acc["total"] += e
        acc["dyn"] += multiplier
        acc["by_class"][cls] = acc["by_class"].get(cls, 0.0) + e

    # Split out nested loops first; analyze them with multipliers.
    i, n = 0, len(body)
    flat_segments = []    # parts without loops
    loops = []            # (trip, body_text, step)
    while i < n:
        m_for = FOR_RE.search(body, i)
        m_while = WHILE_RE.search(body, i)
        candidates = [m for m in (m_for, m_while) if m]
        if not candidates:
            flat_segments.append(body[i:])
            break
        m = min(candidates, key=lambda x: x.start())
        flat_segments.append(body[i:m.start()])
        brace_open = body.find("{", m.end())
        if brace_open == -1:
            flat_segments.append(body[m.start():])
            break
        depth, j = 1, brace_open + 1
        while j < n and depth > 0:
            if body[j] == "{": depth += 1
            elif body[j] == "}": depth -= 1
            j += 1
        inner = body[brace_open + 1:j - 1]
        if m is m_for:
            lo, hi = int(m.group(1)), int(m.group(2))
            step = 1
            if m.group(3): step = int(m.group(3))
            elif m.group(4): step = int(m.group(4))
            trip = max(1, (hi - lo + step - 1) // step)
        else:
            trip = default_trip
            step = 1
        loops.append((trip, inner, step))
        i = j

    # Flat segments: straight-line cost using the caller's miss_prob.
    for seg in flat_segments:
        for tok in ARITH_RE.findall(seg):
            if tok.startswith("*"):    add("mul")
            elif tok.startswith("/"):  add("div")
            elif tok.startswith("%"):  add("rem")
            elif tok == "<<":          add("sll")
            elif tok == ">>":          add("sra")
            elif tok == "&":           add("and")
            elif tok == "|":           add("or")
            elif tok == "^":           add("xor")
            else:                      add("add")
        for _ in DEREF_RE.findall(seg):
            add("lw", mem_miss=miss_prob)
        for call in CALL_RE.findall(seg):
            add("jalr")
            if call.lower() in MUL_CALL_HINTS: add("mul")
            if call.lower() in DIV_CALL_HINTS: add("div")
        acc["total"] += 2.5 * len(CALL_RE.findall(seg))
        for _ in IF_RE.findall(seg):     add("beq")
        for _ in SWITCH_RE.findall(seg): add("jalr")

    # Loops: per-iteration body cost + per-iteration loop overhead.
    for trip, inner, step in loops:
        inner_miss = miss_prob

        # Inner-loop locality heuristic.
        #
        # An innermost loop with a SMALL literal trip count typically fits
        # its working set in L1 — consecutive accesses, good locality. We
        # give it a low miss probability.
        # LARGE inner loops (e.g. k from 0 to N where N > 32) stride through
        # memory and should NOT get the cache-friendly bonus — this is the
        # whole reason tiling saves energy.
        # Unrolling (step > 1) preserves or improves locality.
        is_innermost = "for" not in inner
        effective_work = trip * step   # total iterations the loop represents
        if is_innermost and effective_work <= 32:
            inner_miss = min(inner_miss, 0.05)
        elif step > 1:
            inner_miss = min(inner_miss, miss_prob * 0.5)

        sub = _analyze_body(inner, model, default_trip,
                            block_label + ".loop", inner_miss)

        # Loop overhead: one compare + one branch + one increment per iter.
        # This is what unrolling amortizes.
        overhead_per_iter = (
            model.cost("slt").base_nj + model.cost("slt").switching_nj +
            model.cost("bne").base_nj + model.cost("bne").switching_nj +
            0.10 * model.cost("bne").misprediction_bonus_nj +
            model.cost("addi").base_nj + model.cost("addi").switching_nj
        )
        # Unrolled loops (step > 1) execute body more work per iteration,
        # so the overhead is paid fewer times — that's why unrolling saves energy.
        overhead_total = overhead_per_iter * trip

        acc["total"] += (sub["total"] + overhead_per_iter) * trip
        acc["by_class"]["loop_overhead"] = (
            acc["by_class"].get("loop_overhead", 0.0) + overhead_total
        )
        acc["dyn"] += sub["dyn"] * trip + trip
        for k, v in sub["by_class"].items():
            acc["by_class"][k] = acc["by_class"].get(k, 0.0) + v * trip

    return acc


def run_simulator(src: Path, model: EnergyModel, default_trip: int) -> dict:
    text = src.read_text()
    # strip //... comments and /* ... */ comments
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)

    # Resolve simple `#define NAME value` macros so loop bounds become literal.
    # This is a lightweight preprocessor — good enough for the demo benchmarks.
    defines: Dict[str, str] = {}
    for m in re.finditer(r'^\s*#define\s+([A-Za-z_]\w*)\s+([^\s/]+)\s*$',
                         text, flags=re.M):
        defines[m.group(1)] = m.group(2)
    # Iterate to a fixed point (defines can reference defines)
    for _ in range(4):
        changed = False
        for name, val in list(defines.items()):
            pat = r'\b' + re.escape(name) + r'\b'
            new_text = re.sub(pat, val, text)
            if new_text != text:
                text = new_text; changed = True
        if not changed: break

    # Find each function definition body
    functions: List[SimFunction] = []
    for m in FUNCDEF_RE.finditer(text):
        name = m.group(1)
        if name in _C_KEYWORDS:
            continue
        brace = text.find("{", m.end() - 1)
        if brace == -1: continue
        depth, j = 1, brace + 1
        while j < len(text) and depth > 0:
            if text[j] == "{": depth += 1
            elif text[j] == "}": depth -= 1
            j += 1
        body = text[brace + 1:j - 1]

        acc = _analyze_body(body, model, default_trip, name)
        fn = SimFunction(
            name=name,
            total_nj=acc["total"],
            dynamic_inst_est=acc["dyn"],
            hotest_block=name + ".entry",
            hotest_block_nj=acc["total"],
            by_class=acc["by_class"],
        )
        functions.append(fn)

    module_total = sum(f.total_nj for f in functions)
    return {
        "module": src.name,
        "model": str(model.path),
        "total_nj": module_total,
        "functions": [asdict(f) for f in functions],
        "meta": model.meta,
    }


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        prog="energywise",
        description="Static energy estimation for RISC-V programs.",
    )
    ap.add_argument("source", type=Path, help="C source file to analyze")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL,
                    help="Energy model YAML")
    ap.add_argument("--mode", choices=["native", "sim"], default="sim",
                    help="native = run LLVM pass; sim = pure-Python simulator")
    ap.add_argument("--plugin", type=Path,
                    default=ROOT / "src" / "build" / "libEnergyWise.so",
                    help="Path to built LLVM plugin (for --mode native)")
    ap.add_argument("--report", type=Path,
                    default=ROOT / "reports" / "energy_report.json",
                    help="Output report JSON")
    ap.add_argument("--default-trip", type=int, default=32,
                    help="Fallback trip count for non-literal loop bounds")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    model = EnergyModel(args.model)

    if args.mode == "native":
        report = run_native(args.source, args.model, args.report, args.plugin)
    else:
        report = run_simulator(args.source, model, args.default_trip)

    args.report.write_text(json.dumps(report, indent=2 if args.pretty else None))

    # Friendly stdout summary
    print(f"== EnergyWise  ({args.mode} mode) ==")
    print(f"module:    {report['module']}")
    print(f"model:     {args.model.name}")
    print(f"total:     {report['total_nj']:.2f} nJ")
    print()
    print(f"{'function':<28} {'total nJ':>12} {'~dyn insts':>12}")
    print("-" * 54)
    for f in sorted(report["functions"], key=lambda r: -r["total_nj"]):
        print(f"{f['name']:<28} {f['total_nj']:>12.2f} {f['dynamic_inst_est']:>12}")
    print()
    print(f"-> full report: {args.report}")


if __name__ == "__main__":
    main()
