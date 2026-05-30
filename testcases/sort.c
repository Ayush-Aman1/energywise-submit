#include <stdint.h>

#define N 128
#define STEP 4

int32_t data[N];

void sort_bubble(void) {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j += STEP) {
            if (data[j] > data[j + 1]) {
                int32_t tmp = data[j];
                data[j] = data[j + 1];
                data[j + 1] = tmp;
            }
        }
    }
}

void sort_select(void) {
    for (int i = 0; i < N; i++) {
        int min_idx = i;
        for (int j = 0; j < N; j += STEP) {
            if (data[j] < data[min_idx]) {
                min_idx = j;
            }
        }
        int32_t tmp = data[i];
        data[i] = data[min_idx];
        data[min_idx] = tmp;
    }
}