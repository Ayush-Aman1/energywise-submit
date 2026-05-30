#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== EnergyWise Benchmark Runner ==="
echo ""

mkdir -p reports

PASS=false
if [ -f "$ROOT/src/build/libEnergyWise.so" ] || [ -f "$ROOT/src/build/libEnergyWise.dylib" ]; then
    PASS=true
fi

choose_mode() {
    if [ "$PASS" = true ] && command -v opt &>/dev/null; then
        echo "native"
    else
        echo "sim"
    fi
}

MODE=$(choose_mode)
echo "Mode: $MODE"
echo ""

for tc in testcases/*.c; do
    name="$(basename "$tc" .c)"
    report="reports/${name}.json"
    echo "--- $tc ---"
    if [ "$MODE" = "native" ]; then
        python3 "$ROOT/src/energywise.py" "$tc" --mode native --plugin "$ROOT/src/build/libEnergyWise.so" --report "$report" --pretty
    else
        python3 "$ROOT/src/energywise.py" "$tc" --mode sim --report "$report" --pretty
    fi
    echo ""
done

echo "================================================================"
echo "  SUMMARY COMPARISON TABLE"
echo "================================================================"

python3 - <<'PYEOF'
import json, os, glob

reports = sorted(glob.glob("reports/*.json"))
if not reports:
    print("No reports found.")
    exit(0)

rows = []
for path in reports:
    try:
        with open(path) as f:
            r = json.load(f)
        fns = sorted(r["functions"], key=lambda x: -x["total_nj"])
        if len(fns) >= 2:
            naive = fns[0]
            opt = fns[1]
            pct = (naive["total_nj"] - opt["total_nj"]) / naive["total_nj"] * 100
            rows.append((r["module"], naive["name"], naive["total_nj"], opt["name"], opt["total_nj"], pct))
    except Exception:
        pass

print()
print(f"{'Benchmark':<14} {'Naive fn':<20} {'Naive nJ':>14}  {'Optimised fn':<20} {'Optimised nJ':>14}  {'Saving':>8}")
print("-" * 100)
for bname, nfn, nnj, ofn, onj, pct in rows:
    print(f"{bname:<14} {nfn:<20} {nnj:>14,.0f}  {ofn:<20} {onj:>14,.0f}  {pct:>7.1f}%")
print()
PYEOF

echo "================================================================"
echo "  Reports saved to reports/"
echo "================================================================"