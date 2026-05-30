// Benchmark: image brightness scaler.
// Demonstrates strength reduction — replacing division by a power of 2
// with a right shift. On RV32IMC, div is a ~5.8 nJ instruction with
// 32-cycle latency; srai is ~0.44 nJ with 1-cycle latency.
// EnergyWise should show the shifted version as dramatically cheaper.
#include <stdint.h>

#define IMG 4096

uint8_t image[IMG];

// Divides every pixel by 8 using integer division.
void scale_div(void) {
    for (int i = 0; i < IMG; i++) {
        image[i] = image[i] / 8;
    }
}

// Same operation via arithmetic right shift (strength-reduced).
void scale_shift(void) {
    for (int i = 0; i < IMG; i++) {
        image[i] = image[i] >> 3;
    }
}
