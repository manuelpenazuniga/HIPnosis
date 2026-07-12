"""tests/test_guard.py — HIPnosis Guard (gate estático de portabilidad para CI).

Verifica que:
  1. Un kernel HIP limpio pasa (exit 0, sin hallazgos).
  2. Un __ballot_sync(0xffffffff) reintroducido → correctness → BLOQUEA (exit 1).
  3. CUDA residual (include + cudaMalloc) → correctness → bloquea.
  4. #define WARP_SIZE 32 → correctness → bloquea.
  5. Un shfl width=32 (suspicious) NO bloquea con --fail-on correctness (default).
"""
from __future__ import annotations

from pathlib import Path

from core import guard


def _write(tmp_path: Path, name: str, body: str) -> str:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_clean_hip_kernel_passes(tmp_path):
    src = _write(tmp_path, "ok.hip", (
        "#include <hip/hip_runtime.h>\n"
        "__global__ void add(float* a, float* b){ int i=blockIdx.x; a[i]+=b[i]; }\n"
    ))
    findings = guard.guard_paths([src])
    assert findings == []
    assert guard.main([src]) == 0


def test_reintroduced_ballot_blocks(tmp_path):
    src = _write(tmp_path, "bad.cu", (
        "#include <hip/hip_runtime.h>\n"
        "__global__ void k(int n){ unsigned m = __ballot_sync(0xffffffff, threadIdx.x<n); }\n"
    ))
    findings = guard.guard_paths([src])
    assert any(f.rule in ("W01", "W02") and f.severity == "correctness" for f in findings), findings
    assert guard.main([src]) == 1


def test_residual_cuda_api_blocks(tmp_path):
    src = _write(tmp_path, "leftover.cpp", (
        "#include <cuda_runtime.h>\n"
        "void f(){ float* d; cudaMalloc(&d, 16); }\n"
    ))
    findings = guard.guard_paths([src])
    rules = {f.rule for f in findings}
    assert "CUDA-INCLUDE" in rules and "CUDA-API" in rules, findings
    assert guard.main([src]) == 1


def test_warp32_define_blocks(tmp_path):
    src = _write(tmp_path, "warp.h", "#define WARP_SIZE 32\n")
    findings = guard.guard_paths([src])
    assert any(f.rule == "WARP32-DEFINE" and f.severity == "correctness" for f in findings)
    assert guard.main([src]) == 1


def test_suspicious_only_does_not_block_by_default(tmp_path):
    # __shfl_down con width=32 explícito → W04 (suspicious). Sin correctness → no bloquea.
    src = _write(tmp_path, "shfl.hip", (
        "#include <hip/hip_runtime.h>\n"
        "__device__ int r(int v){ return __shfl_down(v, 1, 32); }\n"
    ))
    findings = guard.guard_paths([src])
    assert findings, "debe haber al menos un hallazgo suspicious"
    assert all(f.severity == "suspicious" for f in findings), findings
    assert guard.main([src]) == 0            # default --fail-on correctness
    assert guard.main(["--fail-on", "suspicious", src]) == 1   # estricto → bloquea


def test_comments_are_ignored_for_residual_cuda(tmp_path):
    src = _write(tmp_path, "commented.hip", (
        "#include <hip/hip_runtime.h>\n"
        "// cudaMalloc was here — now hipMalloc\n"
        "void f(){ float* d; hipMalloc(&d, 16); }\n"
    ))
    assert guard.guard_paths([src]) == []
    assert guard.main([src]) == 0
