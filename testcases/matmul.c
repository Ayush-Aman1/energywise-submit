// Benchmark: 64x64 matrix multiply
// Compares naive vs cache-tiled implementations.
// Tiled version should show smaller memory-miss energy under EnergyWise.
#include <stdint.h>

#define N 64
#define TILE 16

int32_t A[N][N];
int32_t B[N][N];
int32_t C[N][N];

void matmul_naive(void) {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            int32_t s = 0;
            for (int k = 0; k < N; k++) {
                s = s + A[i][k] * B[k][j];
            }
            C[i][j] = s;
        }
    }
}

void matmul_tiled(void) {
    for (int ii = 0; ii < N; ii += TILE) {
        for (int jj = 0; jj < N; jj += TILE) {
            for (int kk = 0; kk < N; kk += TILE) {
                for (int i = 0; i < TILE; i++) {
                    for (int j = 0; j < TILE; j++) {
                        int32_t s = C[ii + i][jj + j];
                        for (int k = 0; k < TILE; k++) {
                            s = s + A[ii + i][kk + k] * B[kk + k][jj + j];
                        }
                        C[ii + i][jj + j] = s;
                    }
                }
            }
        }
    }
}
