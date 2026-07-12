# 🛡️ HIPnosis Guard

**"We don't only migrate you; we keep you migrated."**

A one-shot port has value. The recurring value is stopping the team from quietly
reintroducing CUDA or 32-lane (warp) assumptions on the next pull request. HIPnosis
Guard is a static CI gate that runs the **same wavefront-64 detector** that produced
your Port Passport — no GPU, no network, pure static analysis.

## What it catches

| Rule | Severity | What it flags |
|---|---|---|
| **W01–W03** | correctness | 32-bit ballot masks, truncated popcounts on a 64-lane wavefront |
| **W04–W07** | suspicious | hardcoded warp width 32, lane arithmetic, cooperative-group partitions, fixed `warpSize` |
| **CUDA-INCLUDE** | correctness | residual `#include <cuda_runtime.h>` |
| **CUDA-API** | correctness | residual `cudaXxx` calls that weren't translated |
| **WARP32-DEFINE** | correctness | `#define WARP_SIZE 32` and friends |
| **LAUNCH** | suspicious | CUDA-style `<<<...>>>` launch syntax |

`correctness` findings **block the merge**; `suspicious` findings annotate but don't
block (tune with `--fail-on suspicious`).

## Run it locally

```bash
# from the orchestrator/ directory (needs pydantic)
python -m core.guard path/to/src/          # scan a dir
python -m core.guard --fail-on correctness file.hip
```

Clean output:

```
HIPnosis Guard: 0 blocking, 0 warning(s), 0 total.
✓ Clean — no CUDA residue or wavefront-64 hazards.
```

Reintroduce a bug:

```
  ✕ kernel.hip:13  [W01]  32-bit mask — on wave64 the mask/result are 64-bit
  ✕ kernel.hip:2   [WARP32-DEFINE]  Hardcoded warp size of 32 — AMD wavefronts are 64.
✕ Merge would be blocked: portability regressions reintroduced.
```

## In CI

HIPnosis writes `.github/workflows/hipnosis-guard.yml` into every port it ships, so
the workflow travels with the PR. On GitHub Actions the findings appear as inline
`::error file=…,line=…::` annotations on the diff, and a `correctness` finding fails
the check.

The template lives at [`orchestrator/templates/hipnosis-guard.yml`](../orchestrator/templates/hipnosis-guard.yml);
this repo dogfoods it in [`.github/workflows/hipnosis-guard.yml`](../.github/workflows/hipnosis-guard.yml),
linting [`examples/guard/`](../examples/guard/).

## Demo (30 seconds)

1. In a ported repo, add `#define WARP_SIZE 32` or a `__ballot_sync(0xffffffff)`.
2. Open a PR.
3. The **HIPnosis Guard** check fails, annotating the exact line, and the merge is blocked.

The bug HIPnosis removed can't sneak back in.
