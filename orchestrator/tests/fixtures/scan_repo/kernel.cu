// Synthetic fixture for the SCAN phase test suite.
//
// Designed to exercise every branch of core/phases/scan.py:
//   * cuda* API calls counted by regex (cudaMalloc x3, cudaMemcpy x4,
//     cudaDeviceSynchronize x1).
//   * cuBLAS library detected both via #include <cublas_v2.h> and via
//     a direct cublas* identifier call.
//   * Wave64 patterns W01 + W02 (W01 because of __ballot(_sync)?
//     with mask 0xffffffff; W02 because the result is assigned to an
//     `unsigned` / 32-bit variable). See core/wave64 catalog.
//   * No PTX inline assembly → the difficulty heuristic must NOT
//     take the "hard" branch on the PTX leg.
//   * LoC intentionally modest (<2000), so combined with the cublas
//     lib it lands in "medium" per the §5.3 heuristic.

#include <cuda_runtime.h>
#include <cublas_v2.h>
#include "aux.cuh"

__global__ void vadd(const float *a, const float *b, float *c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}

__global__ void reduce_sum(const float *in, float *out, int n) {
    // W01 + W02: ballot on a 32-bit mask assigned to a 32-bit var.
    unsigned mask_a = __ballot_sync(0xffffffff, threadIdx.x < 32);
    unsigned mask_b = __ballot(0xffffffff);
    if ((threadIdx.x & 31) == 0) {
        out[threadIdx.x >> 5] = mask_a + mask_b;
    }
}

extern "C" void launch_vadd(const float *a, const float *b, float *c, int n) {
    float *da = nullptr;
    float *db = nullptr;
    float *dc = nullptr;
    cudaMalloc((void **)&da, n * sizeof(float));        // cudaMalloc #1
    cudaMalloc((void **)&db, n * sizeof(float));        // cudaMalloc #2
    cudaMalloc((void **)&dc, n * sizeof(float));        // cudaMalloc #3
    cudaMemcpy(da, a, n * sizeof(float), cudaMemcpyHostToDevice);   // cudaMemcpy #1
    cudaMemcpy(db, b, n * sizeof(float), cudaMemcpyHostToDevice);   // cudaMemcpy #2
    cudaMemcpy(dc, c, n * sizeof(float), cudaMemcpyDeviceToHost);   // cudaMemcpy #3
    vadd<<<(n + 255) / 256, 256>>>(da, db, dc, n);
    cudaDeviceSynchronize();
    cudaMemcpy(c, dc, n * sizeof(float), cudaMemcpyDeviceToHost);   // cudaMemcpy #4
    // ^ total: cudaMalloc x3, cudaMemcpy x4, cudaDeviceSynchronize x1
    cudaFree(da);
    cudaFree(db);
    cudaFree(dc);
}
