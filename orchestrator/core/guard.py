"""core/guard.py — HIPnosis Guard: gate estático de portabilidad para CI (L4).

"HIPnosis no solo te migra; evita que vuelvas a quedar locked-in." Una vez que un
repo está porteado a ROCm, este gate corre en cada PR y BLOQUEA los cambios que
reintroducen dependencia de CUDA o supuestos de warp de 32 lanes — exactamente
los bugs silenciosos que el pipeline de HIPnosis caza.

Reutiliza el MISMO detector wave64 (``core.wave64``) validado contra kernels
reales, más un scan de API CUDA residual. Sin GPU, sin red: análisis estático puro.

Uso::

    python -m core.guard <archivos-o-dirs...>
    python -m core.guard --fail-on correctness src/

Salida: anotaciones de GitHub Actions (``::error file=…,line=…::…``) cuando corre
en CI (``GITHUB_ACTIONS=true``), o un reporte legible en consola. Exit code != 0
si hay hallazgos de la severidad configurada (``correctness`` por defecto) — así
el check de CI falla y el merge se bloquea.

Capa L4: importa ``core.wave64`` (L3) y ``core.schemas`` (L1). No toca ``state``,
``llm`` ni ``oracle`` — es una herramienta de línea de comandos independiente.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.wave64 import lint_file

# Extensiones de fuente CUDA/HIP que revisamos.
_SOURCE_EXT = {".cu", ".cuh", ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hip"}

# CUDA residual: includes del runtime y llamadas a la API cudaXxx que NO deberían
# sobrevivir a un port. Ignoramos comentarios de forma cruda (línea que arranca con //).
_CUDA_INCLUDE = re.compile(r"#\s*include\s*[<\"]cuda(_runtime|_runtime_api|)\.h[>\"]")
_CUDA_API = re.compile(r"\bcuda[A-Z]\w+")
_LAUNCH = re.compile(r"<<<.+?>>>")

_SEVERITY_ORDER = {"suspicious": 0, "correctness": 1}


@dataclass
class GuardFinding:
    file: str
    line: int
    rule: str           # p.ej. "W01", "CUDA-API", "CUDA-INCLUDE", "LAUNCH"
    severity: str       # "correctness" | "suspicious"
    message: str


def _iter_sources(paths: Iterable[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and f.suffix in _SOURCE_EXT:
                    out.append(str(f))
        elif path.is_file() and path.suffix in _SOURCE_EXT:
            out.append(str(path))
    return out


def _scan_residual_cuda(path: str) -> list[GuardFinding]:
    """Detecta CUDA residual (include del runtime, API cudaXxx, launch <<<>>>)."""
    findings: list[GuardFinding] = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings
    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        if line.startswith("//"):
            continue
        if _CUDA_INCLUDE.search(raw):
            findings.append(GuardFinding(path, i, "CUDA-INCLUDE", "correctness",
                "Residual CUDA runtime include — the port should use <hip/hip_runtime.h>"))
        for m in _CUDA_API.finditer(raw):
            findings.append(GuardFinding(path, i, "CUDA-API", "correctness",
                f"Residual CUDA API call '{m.group(0)}' — not translated to HIP"))
        if _LAUNCH.search(raw):
            findings.append(GuardFinding(path, i, "LAUNCH", "suspicious",
                "CUDA-style kernel launch syntax <<<...>>> — verify it is HIP-portable"))
    return findings


# Regla explícita para el supuesto warp32 que el detector wave64 no cubre como
# #define: un `#define WARP_SIZE 32` (o warpSize hardcodeado) reintroduce el bug.
_WARP32_DEFINE = re.compile(r"#\s*define\s+\w*WARP\w*\s+32\b", re.IGNORECASE)


def _scan_warp32_define(path: str) -> list[GuardFinding]:
    findings: list[GuardFinding] = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings
    for i, raw in enumerate(lines, start=1):
        if raw.strip().startswith("//"):
            continue
        if _WARP32_DEFINE.search(raw):
            findings.append(GuardFinding(path, i, "WARP32-DEFINE", "correctness",
                "Hardcoded warp size of 32 — AMD wavefronts are 64. Query warpSize at runtime."))
    return findings


def guard_paths(paths: Iterable[str]) -> list[GuardFinding]:
    """Corre todas las reglas sobre las fuentes en ``paths``."""
    findings: list[GuardFinding] = []
    for src in _iter_sources(paths):
        # 1. Wave64 (el detector real, validado): W01-W07.
        for w in lint_file(src):
            findings.append(GuardFinding(
                file=src, line=w.line, rule=w.pattern_id,
                severity=w.severity, message=w.explanation,
            ))
        # 2. CUDA residual + supuesto warp32.
        findings.extend(_scan_residual_cuda(src))
        findings.extend(_scan_warp32_define(src))
    return findings


def _blocks(f: GuardFinding, fail_on: str) -> bool:
    return _SEVERITY_ORDER.get(f.severity, 0) >= _SEVERITY_ORDER.get(fail_on, 1)


def _report(findings: list[GuardFinding], fail_on: str) -> int:
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    blocking = [f for f in findings if _blocks(f, fail_on)]
    warnings = [f for f in findings if not _blocks(f, fail_on)]

    for f in findings:
        level = "error" if _blocks(f, fail_on) else "warning"
        title = f"HIPnosis Guard · {f.rule}"
        if in_ci:
            # Anotación nativa de GitHub Actions (aparece en el diff del PR).
            print(f"::{level} file={f.file},line={f.line},title={title}::{f.message}")
        else:
            mark = "✕" if level == "error" else "•"
            print(f"  {mark} {f.file}:{f.line}  [{f.rule}]  {f.message}")

    if in_ci:
        summary = (f"HIPnosis Guard: {len(blocking)} blocking, {len(warnings)} warnings")
        print(f"::notice title=HIPnosis Guard::{summary}")
    else:
        print(f"\nHIPnosis Guard: {len(blocking)} blocking, {len(warnings)} warning(s), "
              f"{len(findings)} total.")
        if blocking:
            print("✕ Merge would be blocked: portability regressions reintroduced.")
        elif not findings:
            print("✓ Clean — no CUDA residue or wavefront-64 hazards.")

    return 1 if blocking else 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    fail_on = "correctness"
    paths: list[str] = []
    it = iter(argv)
    for a in it:
        if a == "--fail-on":
            fail_on = next(it, "correctness")
        elif a in ("-h", "--help"):
            print("usage: python -m core.guard [--fail-on correctness|suspicious] <paths...>")
            return 0
        else:
            paths.append(a)
    if not paths:
        paths = ["."]
    findings = guard_paths(paths)
    return _report(findings, fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
