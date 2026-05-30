#include <stdint.h>

#define N 512
#define ALPHA 7

int32_t in_buf[N];
int32_t out_buf[N];

void filter_per_sample(void) {
    for (int i = 1; i < N; i++) {
        out_buf[i] = in_buf[i] * ALPHA + in_buf[i - 1] * 3 + out_buf[i - 1] * 5;
    }
}

void filter_grouped(void) {
    int32_t prev_in = in_buf[0];
    int32_t prev_out = 0;
    for (int i = 1; i < N; i++) {
        int32_t curr = in_buf[i];
        int32_t result = curr * ALPHA + prev_in * 3 + prev_out * 5;
        out_buf[i] = result;
        prev_in = curr;
        prev_out = result;
    }
}