// Header for the SCAN-phase fixture. Exists so .cuh files are also
// picked up by the file walk and counted in loc_kernels. Includes a
// second cublas surface (cuBLAS handle typedef) so the include path
// is exercised even if kernel.cu's <cublas_v2.h> were missing.

#ifndef SCAN_REPO_AUX_CUH
#define SCAN_REPO_AUX_CUH

#include <cuda_runtime.h>
#include <cublas_v2.h>

// Touch a cuBLAS identifier so the call-side lib detector also fires
// from a header context (proves include + call paths both work).
typedef cublasHandle_t hipno_blas_handle_t;

#endif
