// Synthetic fixture for the wave64 linter test suite.
// One clean, unambiguous example of each W01..W07 pattern at a known
// line number, followed by negative cases (commented-out / stringified
// occurrences) that MUST NOT trigger any finding.
//
// This file is NOT meant to compile; it exists only to exercise the
// deterministic catalog in core.wave64.

#include <cuda_runtime.h>
#include <cooperative_groups.h>

namespace cg = cooperative_groups;

// ===== W01: 32-bit ballot mask =====
__global__ void k01(unsigned *out) {
    use_mask(__ballot(0xffffffff));   // W01 fires on this line
    out[0] = 0;
}

// ===== W02: ballot result assigned to 32-bit variable =====
__global__ void k02(unsigned *out) {
    unsigned r02 = __ballot(0x1);     // W02 fires on this line (mask 0x1 ≠ 0xffffffff)
    out[0] = r02;
}

// ===== W03: __popc(__ballot(...)) — must be __popcll for 64-bit =====
__global__ void k03(int *out) {
    int c03 = __popc(__ballot(0x1));  // W03 fires on this line
    out[0] = c03;
}

// ===== W04: __shfl with hardcoded width 32 =====
__global__ void k04(int *out) {
    int v04 = __shfl_sync(0xffffffff, 1, 32);  // W04 fires on this line
    out[0] = v04;
}

// ===== W05: lane arithmetic assuming warp of 32 =====
__global__ void k05(int *out) {
    int lane05 = threadIdx.x & 31;    // W05 fires on this line
    out[0] = lane05;
}

// ===== W06: cooperative-groups partition of size 32 =====
__global__ void k06(int *out) {
    auto w06 = cg::tiled_partition<32>(cg::this_thread_block());  // W06 fires on this line
    out[0] = 0;
}

// ===== W07: hardcoded WARP_SIZE 32 (both forms) =====
#define WARP_SIZE 32                   // W07 fires on this line (define form)
constexpr WARP = 32; int warp = WARP; // W07 fires on this line (constexpr form)
__global__ void k07(int *out) {
    out[0] = WARP_SIZE;
}

// ===== NEGATIVE — must NOT trigger any pattern =====
int neg1 = 0; // __ballot(0xffffffff) trailing line comment
/* __ballot(0xffffffff) and __shfl_sync(0xffffffff, 1, 32) inside
   a block comment that spans multiple lines, must not trigger */
const char *neg2 = "__ballot(0xffffffff) and __popc(__ballot(0x1))";
int neg3 = threadIdx.x / 64;  // correct wave64 lane step — W05 guard passes,
//                               but / 64 is NOT in the (32|31|5) alternation.
