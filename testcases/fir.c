// Benchmark: 16-tap FIR filter (canonical DSP workload).
// Exposes memory energy (sample array) and mul energy (multiply-accumulate).
//
// We compare TWO variants:
//   fir_naive:    inner loop runs 16 iters; each pays loop overhead.
//   fir_unrolled: inner loop unrolled 4x; same work, 4x less overhead.
//
// EnergyWise should report fir_unrolled as LOWER energy — the saving comes
// from amortizing the loop compare/branch/increment across 4 MACs instead
// of paying it on every MAC.
#include <stdint.h>

#define N 1024
#define TAPS 16

int16_t samples[N];
int16_t coeffs[TAPS];
int32_t output[N];

void fir_naive(void) {
    // Skip the leading samples that would need boundary handling so both
    // variants compute the same thing without per-iteration `if`s.
    for (int i = TAPS; i < N; i++) {
        int32_t acc = 0;
        for (int k = 0; k < TAPS; k++) {
            acc = acc + samples[i - k] * coeffs[k];
        }
        output[i] = acc;
    }
}

void fir_unrolled(void) {
    for (int i = TAPS; i < N; i++) {
        int32_t acc = 0;
        // Inner loop fully unrolled by 4 — no per-MAC loop overhead,
        // the bounds guard in fir_naive is also hoisted out (above).
        for (int k = 0; k < TAPS; k += 4) {
            acc = acc + samples[i - k]     * coeffs[k];
            acc = acc + samples[i - k - 1] * coeffs[k + 1];
            acc = acc + samples[i - k - 2] * coeffs[k + 2];
            acc = acc + samples[i - k - 3] * coeffs[k + 3];
        }
        output[i] = acc;
    }
}
