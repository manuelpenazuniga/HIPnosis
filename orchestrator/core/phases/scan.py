"""core/phases/scan.py — FASE 1 SCAN (inventario + wave64 + dificultad).

Capa L4 (phase). Importa ``core.schemas`` (contratos) y ``core.wave64``
(L2, el linter que detecta suposiciones de warp=32). NUNCA importa
hacia arriba: state / api / oracle / llm. Toda la inteligencia de
scan es DETERMINISTA — el LLM no participa (blueprint §5.1-§5.3, F-17).

Contrato público:
    scan(repo_dir)                        -> ScanResult
    portability_report_data(scan_result)  -> dict

El ``portability_report_data`` devuelve los NÚMEROS que el template del
certificado necesita. El ``executive_summary`` queda como string vacío
porque esa parte la redacta Gemma 3 (T12/report), nunca esta capa.
"""

from __future__ import annotations

import os
import re
from collections import Counter

from core import wave64
from core.schemas import ScanResult, Wave64Finding
from core.wave64 import _strip_comments_and_strings


# ---------------------------------------------------------------------------
# Regex compiladas (F-17: explicadas, no inventadas en runtime).
# ---------------------------------------------------------------------------

# Whitelist de API CUDA estilo CamelCase: cudaMalloc, cudaMemcpy, etc.
# El prefijo `cuda` + mayúscula obligatoria evita matchear identificadores
# del usuario que casualmente empiecen con "cuda" en minúsculas.
_CUDA_API_RE = re.compile(r"\bcuda[A-Z]\w+")

# Librerías de NVIDIA: cublas / curand / cufft / cudnn. Case-insensitive
# porque en código real van casi siempre en minúsculas aunque el spec
# las escriba en mayúsculas. Se normaliza a minúsculas al final.
_CULIB_CALL_RE = re.compile(r"\bcu(blas|rand|fft|dnn)\w*", re.IGNORECASE)
_CULIB_INCLUDE_RE = re.compile(
    r"<\s*cu(blas|rand|fft|dnn)\w*\.h[^>]*>", re.IGNORECASE
)

# PTX inline asm: `asm("...")` o `asm volatile("...")`. Se busca en todo
# el repo (no solo .cu) porque a veces vive en headers de kernels.
_PTX_INLINE_ASM_RE = re.compile(r"\basm\s*(volatile)?\s*\(")

# Extensiones que cuentan como "código CUDA" para loc_kernels.
_CUDA_EXTS = (".cu", ".cuh")
# Extensiones que cuentan para el inventario de archivos source.
_SOURCE_EXTS = (".cu", ".cuh", ".h", ".hpp", ".cpp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _walk_sources(repo_dir: str) -> list[str]:
    """Devuelve rutas RELATIVAS a ``repo_dir`` para archivos source
    reconocidos (``.cu .cuh .h .hpp .cpp``), en orden estable."""
    seen: set[str] = set()
    out: list[str] = []
    for root, _dirs, files in os.walk(repo_dir):
        for name in files:
            if not name.endswith(_SOURCE_EXTS):
                continue
            rel = os.path.relpath(os.path.join(root, name), repo_dir)
            # normalizar separadores en Windows/Linux mixtos
            rel = rel.replace(os.sep, "/")
            if rel in seen:
                continue
            seen.add(rel)
            out.append(rel)
    out.sort()
    return out


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _line_count(path: str) -> int:
    """Líneas totales del archivo (en blanco o no). El blueprint §5.1
    dice 'loc_kernels' = total de líneas, no LOC no-vacías."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def _detect_libs_from_text(text: str, libs: set[str]) -> None:
    # Strippear comentarios/strings para que "// see cublas docs" no
    # sea contado como uso. La heurística de libs es robusta igual
    # porque los includes viven en líneas "activas" del preprocesador,
    # pero los identificadores sueltos (cublasHandle_t) SÍ pueden
    # aparecer en comentarios.
    code = _strip_comments_and_strings(text)
    for m in _CULIB_CALL_RE.finditer(code):
        libs.add("cu" + m.group(1).lower())
    for m in _CULIB_INCLUDE_RE.finditer(code):
        libs.add("cu" + m.group(1).lower())


def _detect_ptx_in_text(text: str) -> bool:
    return _PTX_INLINE_ASM_RE.search(text) is not None


def _detect_build_system(repo_dir: str) -> str:
    if os.path.isfile(os.path.join(repo_dir, "CMakeLists.txt")):
        return "cmake"
    if os.path.isfile(os.path.join(repo_dir, "Makefile")):
        return "make"
    # Blueprint §5.1: default a "make" si no se detecta nada.
    return "make"


def _classify_difficulty(*, has_ptx: bool, libs: list[str], loc: int) -> str:
    """Heurística FIJA de blueprint §5.3. Sin LLM.

      easy   ↔ (0 PTX ∧ 0 libs ∧ loc < 2000)
      hard   ↔ (hay PTX ∨ "cudnn" en libs ∨ loc > 10000)
      medium ↔ lo demás
    """
    libs_set = set(libs)
    if not has_ptx and not libs_set and loc < 2000:
        return "easy"
    if has_ptx or "cudnn" in libs_set or loc > 10000:
        return "hard"
    return "medium"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def scan(repo_dir: str) -> ScanResult:
    """FASE 1 — Inventario + wave64 + dificultad. Sin LLM, sin subprocess,
    sin red. Toma ~milisegundos sobre repos HeCBench típicos.

    Pasos (blueprint §5.1-§5.3):
      1. Walk de ``repo_dir`` para inventario de archivos.
      2. Conteo de API calls por regex sobre .cu/.cuh.
      3. Detección de libs (cuBLAS/RAND/FFT/DNN) por include o por call.
      4. Detección de PTX inline asm.
      5. ``core.wave64.lint`` sobre cada .cu/.cuh.
      6. Heurística de dificultad §5.3 (sin LLM).
    """
    if not os.path.isdir(repo_dir):
        raise NotADirectoryError(f"scan(): repo_dir no existe: {repo_dir}")

    files = _walk_sources(repo_dir)

    files_cuda = [f for f in files if f.endswith(_CUDA_EXTS)]

    api_calls: Counter[str] = Counter()
    libs: set[str] = set()
    has_ptx = False
    loc_kernels = 0
    wave64_findings: list[Wave64Finding] = []

    for rel in files_cuda:
        abs_path = os.path.join(repo_dir, rel)
        loc_kernels += _line_count(abs_path)
        text = _read_text(abs_path)

        # Para los conteos por regex aplicamos el stripper de
        # comentarios/strings de wave64: un comentario `// use cudaMalloc`
        # no es un call site. LOC se cuenta sobre el archivo original
        # (el spec dice "total de líneas", no "LOC no-vacías").
        code = _strip_comments_and_strings(text)

        api_calls.update(_CUDA_API_RE.findall(code))
        _detect_libs_from_text(text, libs)
        if not has_ptx and _detect_ptx_in_text(text):
            has_ptx = True

        # Wave64: scan usa el linter determinista de L2 (catálogo cerrado).
        # Pasamos `rel` como filename para que los hallazgos lleven la
        # ruta RELATIVA al repo, no la absoluta del droplet.
        wave64_findings.extend(wave64.lint(text, filename=rel))

    # Orden estable: libs alfabéticas, api_calls por nombre.
    libs_sorted = sorted(libs)
    api_calls_dict = dict(sorted(api_calls.items()))

    build_system = _detect_build_system(repo_dir)

    difficulty = _classify_difficulty(
        has_ptx=has_ptx, libs=libs_sorted, loc=loc_kernels
    )

    return ScanResult(
        files_cuda=files_cuda,
        loc_kernels=loc_kernels,
        api_calls=api_calls_dict,
        libs=libs_sorted,
        build_system=build_system,
        wave64_findings=wave64_findings,
        difficulty=difficulty,
    )


def portability_report_data(scan: ScanResult) -> dict:
    """Datos ESTRUCTURADOS para el template del certificado de port.

    Los NÚMEROS salen de acá (F-17) — el LLM no toca conteos. El
    ``executive_summary`` queda vacío: otra capa (T12/report) lo
    redacta con Gemma. Esta función es PURA sobre el ``ScanResult``.
    """
    sev_counts: Counter[str] = Counter()
    for f in scan.wave64_findings:
        sev_counts[f.severity] += 1

    return {
        "files_cuda": list(scan.files_cuda),
        "loc_kernels": scan.loc_kernels,
        "api_calls": dict(scan.api_calls),
        "libs": list(scan.libs),
        "build_system": scan.build_system,
        "difficulty": scan.difficulty,
        "wave64_findings": [f.model_dump() for f in scan.wave64_findings],
        "wave64_counts": {
            "total": len(scan.wave64_findings),
            "correctness": sev_counts.get("correctness", 0),
            "suspicious": sev_counts.get("suspicious", 0),
        },
        "executive_summary": "",
    }
