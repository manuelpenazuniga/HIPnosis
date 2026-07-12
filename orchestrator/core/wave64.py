"""core/wave64.py — linter estático wave64 (catálogo cerrado W01-W07).

L2 puro: importa SOLO ``core.schemas`` y ``re`` (más stdlib). Es el ARMA
DIFERENCIAL del producto: detecta suposiciones de warp=32 que rompen en
AMD wave64. Catálogo CERRADO y determinista; las explicaciones son
TEXTO FIJO del catálogo (F-17 — el LLM nunca las genera).

Contrato público:
    lint(source, filename="<mem>") -> list[Wave64Finding]
    lint_file(path)                 -> list[Wave64Finding]
"""

from __future__ import annotations

import re

from core.schemas import Wave64Finding


# ---------------------------------------------------------------------------
# Catálogo cerrado (blueprint §5.2). NO agregar patrones acá sin reabrir §5.2.
# Explicaciones copiadas EXACTO del blueprint — F-17.
# ---------------------------------------------------------------------------

EXPL_W01 = "32-bit mask — on wave64 the mask/result are 64-bit"
EXPL_W02 = "Ballot result truncated to 32 bits on wave64"
EXPL_W03 = "Should be __popcll over a 64-bit mask"
EXPL_W04 = "Hardcoded width 32 — AMD wavefront is 64"
EXPL_W05 = "Lane arithmetic assumes a 32-wide warp (&31, >>5)"
EXPL_W06 = "Cooperative-groups partition of NVIDIA warp size"
EXPL_W07 = "warpSize must be queried at runtime in HIP, not fixed at 32"


_PATTERN_W01 = re.compile(r"__ballot(_sync)?\s*\(\s*0xffffffff")
_PATTERN_W02 = re.compile(r"(unsigned|uint32_t|int)\s+\w+\s*=\s*__ballot")
_PATTERN_W03 = re.compile(r"__popc\s*\(\s*__ballot")
_PATTERN_W04 = re.compile(r"__shfl(_up|_down|_xor)?(_sync)?\s*\([^)]*\b32\b")
_PATTERN_W05 = re.compile(r"(%|&|/|>>)\s*(32|31|5)\b")
_PATTERN_W06 = re.compile(r"tiled_partition\s*<\s*32\s*>")
_PATTERN_W07 = re.compile(
    r"(#define\s+WARP_SIZE\s+32|constexpr\s+\w*\s*=\s*32.*warp)",
    re.IGNORECASE,
)

# W05: el patrón aritmético solo aplica si la línea ya menciona lane/thread.
_W05_LINE_GUARD = re.compile(r"threadIdx|laneId|lane_id")


# ---------------------------------------------------------------------------
# Stripper de comentarios y strings.
# ---------------------------------------------------------------------------

def _strip_comments_and_strings(source: str) -> str:
    """Reemplaza comentarios y literales por espacios; preserva \\n.

    State machine mínima (NORMAL / LINE_COMMENT / BLOCK_COMMENT /
    STRING / CHAR). Mantiene la cantidad de líneas y columnas del
    original: lo único que se preserva fuera de comentarios/strings
    es el carácter ``\\n``. Esto garantiza que los números de línea
    del output coincidan con los del input.
    """
    out = list(source)
    n = len(source)
    i = 0
    state = "NORMAL"
    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if state == "NORMAL":
            if c == "/" and nxt == "/":
                out[i] = " "
                out[i + 1] = " "
                i += 2
                state = "LINE_COMMENT"
            elif c == "/" and nxt == "*":
                out[i] = " "
                out[i + 1] = " "
                i += 2
                state = "BLOCK_COMMENT"
            elif c == '"':
                out[i] = " "
                i += 1
                state = "STRING"
            elif c == "'":
                out[i] = " "
                i += 1
                state = "CHAR"
            else:
                i += 1
        elif state == "LINE_COMMENT":
            if c == "\n":
                i += 1
                state = "NORMAL"
            else:
                out[i] = " "
                i += 1
        elif state == "BLOCK_COMMENT":
            if c == "*" and nxt == "/":
                out[i] = " "
                out[i + 1] = " "
                i += 2
                state = "NORMAL"
            elif c == "\n":
                i += 1
            else:
                out[i] = " "
                i += 1
        elif state == "STRING":
            if c == "\\" and i + 1 < n:
                out[i] = " "
                out[i + 1] = " "
                i += 2
            elif c == '"':
                out[i] = " "
                i += 1
                state = "NORMAL"
            elif c == "\n":
                i += 1
                state = "NORMAL"
            else:
                out[i] = " "
                i += 1
        elif state == "CHAR":
            if c == "\\" and i + 1 < n:
                out[i] = " "
                out[i + 1] = " "
                i += 2
            elif c == "'":
                out[i] = " "
                i += 1
                state = "NORMAL"
            elif c == "\n":
                i += 1
                state = "NORMAL"
            else:
                out[i] = " "
                i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def _snippet(orig_lines: list[str], idx: int) -> str:
    lo = max(0, idx - 2)
    hi = min(len(orig_lines), idx + 3)
    return "\n".join(orig_lines[lo:hi])


def _emit(
    findings: list[Wave64Finding],
    *,
    pid: str,
    severity: str,
    explanation: str,
    lineno: int,
    orig_lines: list[str],
    idx: int,
    filename: str,
) -> None:
    findings.append(
        Wave64Finding(
            file=filename,
            line=lineno,
            pattern_id=pid,
            snippet=_snippet(orig_lines, idx),
            severity=severity,
            explanation=explanation,
        )
    )


def lint(source: str, filename: str = "<mem>") -> list[Wave64Finding]:
    """Aplica el catálogo W01..W07 sobre ``source`` ya despojado de
    comentarios y strings. Devuelve hallazgos en orden de aparición.

    El número de línea es 1-based y refleja la posición en el ``source``
    ORIGINAL (no en la versión despojada): como el stripper preserva
    los ``\\n``, los índices no se corren.
    """
    stripped = _strip_comments_and_strings(source)
    orig_lines = source.split("\n")
    stripped_lines = stripped.split("\n")
    findings: list[Wave64Finding] = []

    for idx, line in enumerate(stripped_lines):
        lineno = idx + 1

        for _ in _PATTERN_W01.finditer(line):
            _emit(findings, pid="W01", severity="correctness",
                  explanation=EXPL_W01, lineno=lineno,
                  orig_lines=orig_lines, idx=idx, filename=filename)

        for _ in _PATTERN_W02.finditer(line):
            _emit(findings, pid="W02", severity="correctness",
                  explanation=EXPL_W02, lineno=lineno,
                  orig_lines=orig_lines, idx=idx, filename=filename)

        for _ in _PATTERN_W03.finditer(line):
            _emit(findings, pid="W03", severity="correctness",
                  explanation=EXPL_W03, lineno=lineno,
                  orig_lines=orig_lines, idx=idx, filename=filename)

        for _ in _PATTERN_W04.finditer(line):
            _emit(findings, pid="W04", severity="suspicious",
                  explanation=EXPL_W04, lineno=lineno,
                  orig_lines=orig_lines, idx=idx, filename=filename)

        if _W05_LINE_GUARD.search(line):
            for _ in _PATTERN_W05.finditer(line):
                _emit(findings, pid="W05", severity="suspicious",
                      explanation=EXPL_W05, lineno=lineno,
                      orig_lines=orig_lines, idx=idx, filename=filename)

        for _ in _PATTERN_W06.finditer(line):
            _emit(findings, pid="W06", severity="suspicious",
                  explanation=EXPL_W06, lineno=lineno,
                  orig_lines=orig_lines, idx=idx, filename=filename)

        for _ in _PATTERN_W07.finditer(line):
            _emit(findings, pid="W07", severity="suspicious",
                  explanation=EXPL_W07, lineno=lineno,
                  orig_lines=orig_lines, idx=idx, filename=filename)

    return findings


def lint_file(path: str) -> list[Wave64Finding]:
    """Helper: lee el archivo de ``path`` y delega en :func:`lint`."""
    with open(path, encoding="utf-8") as f:
        return lint(f.read(), filename=path)
