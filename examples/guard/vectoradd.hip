// examples/guard/vectoradd.hip — a clean, wavefront-portable HIP kernel.
// HIPnosis Guard lints this file on every push/PR; it must stay green.
// No residual CUDA, no 32-lane assumptions. warpSize is queried at runtime.
#include <hip/hip_runtime.h>

__global__ void vector_add(const float* a, const float* b, float* c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}

// Cross-lane reduction that is correct on both 32- and 64-lane hardware:
// it reads warpSize at runtime instead of hardcoding 32.
__device__ float warp_reduce_sum(float v) {
    for (int offset = warpSize / 2; offset > 0; offset /= 2) {
        v += __shfl_down(v, offset);
    }
    return v;
}
