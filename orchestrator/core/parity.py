"""core/parity.py — comparador numerico rtol/atol (F-09).

F-09: JAMAS comparacion exacta de floats. SIEMPRE rtol/atol.
El orden de reduccion / FMA cambia los ultimos bits legitimamente.

F-17: los numeros de reportes/certificados solo salen de este codigo,
nunca de un LLM.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import core.schemas  # noqa: F401  — referencia L2 documentada


@dataclass
class ParityResult:
    ok: bool
    detail: str
    n_compared: int = 0


# audit MEDIUM: lookbehind para no capturar números pegados a identificadores/paths
# (p.ej. el '3' de 'v3.0' o 'file2.txt'). Los rangos tipo '1-2' siguen siendo ambiguos
# (el '-2' se lee como negativo) — limitación documentada; el golden de repos demo es estructurado.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

_NAN_INF_RE = re.compile(r"[-+]?\b(?:nan|inf(?:inity)?)\b", re.IGNORECASE)


def extract_floats(text: str) -> list[float]:
    """Extrae TODOS los numeros (int, float, notacion cientifica, nan, inf)
    del texto, en orden de aparicion."""
    positions: list[tuple[int, str]] = []

    for m in _NUMBER_RE.finditer(text):
        positions.append((m.start(), m.group()))

    for m in _NAN_INF_RE.finditer(text):
        positions.append((m.start(), m.group()))

    positions.sort(key=lambda x: x[0])

    result: list[float] = []
    for _, val in positions:
        lower = val.lower()
        if lower in ("nan", "-nan"):
            result.append(math.nan)
        elif lower in ("inf", "infinity", "+inf", "+infinity"):
            result.append(math.inf)
        elif lower in ("-inf", "-infinity"):
            result.append(-math.inf)
        else:
            result.append(float(val))

    return result


def compare_floats(
    actual: list[float],
    expected: list[float],
    rtol: float = 1e-5,
    atol: float = 1e-8,
) -> ParityResult:
    """Compara posicionalmente con la formula de numpy.isclose SIN numpy:

        close = abs(a-e) <= atol + rtol*abs(e)

    nan==nan se considera IGUAL (valido en self-checks).
    inf==inf igual, inf!=-inf distinto.
    """
    if len(actual) != len(expected):
        return ParityResult(
            ok=False,
            detail=f"conteo distinto: {len(actual)} vs {len(expected)}",
        )

    for i, (a, e) in enumerate(zip(actual, expected)):
        if not _values_close(a, e, rtol, atol):
            if math.isnan(a) or math.isnan(e):
                diff_repr = "nan"
            elif math.isinf(a) or math.isinf(e):
                diff_repr = "inf"
            else:
                diff_repr = repr(abs(a - e))
            return ParityResult(
                ok=False,
                n_compared=len(actual),
                detail=(
                    f"difieren en indice {i}: actual={a}, esperado={e}, "
                    f"diff={diff_repr}, rtol={rtol}, atol={atol}"
                ),
            )

    return ParityResult(
        ok=True,
        n_compared=len(actual),
        detail=f"{len(actual)} valores comparados, rtol={rtol}, atol={atol}",
    )


def _values_close(a: float, e: float, rtol: float, atol: float) -> bool:
    if math.isnan(a) and math.isnan(e):
        return True
    if math.isinf(a) or math.isinf(e):
        return a == e
    return abs(a - e) <= atol + rtol * abs(e)


def check_self_check(stdout: str, pass_regex: str) -> ParityResult:
    """Modo self_check: el benchmark imprime su veredicto en una línea.

    F-17/audit CRITICAL: el pass_regex se busca POR LÍNEA, y se ignoran las líneas que
    son un veredicto de FALLO (contienen ``\bFAIL\b``). Así ``FAIL: PASS not reached`` NO
    se certifica como PASS (aunque contenga el substring 'PASS'), pero casos legítimos como
    ``Tests completed: PASS`` o ``result: OK (1234)`` sí. (``\bFAIL\b`` word-bounded no
    excluye 'failures'; el caso '0 failures' como PASS es una limitación documentada.)
    """
    pat = re.compile(pass_regex)
    fail_re = re.compile(r"\bFAIL\b", re.IGNORECASE)
    ok = any(
        pat.search(line) and not fail_re.search(line)
        for line in stdout.splitlines()
    )
    return ParityResult(
        ok=ok,
        detail=f"self_check: patron de linea '{pass_regex}' {'encontrado' if ok else 'no encontrado'}",
    )


def check_golden(
    stdout: str,
    golden_text: str,
    rtol: float = 1e-5,
    atol: float = 1e-8,
) -> ParityResult:
    """Modo golden_output: extrae floats de stdout y golden_text, comparalos."""
    actual = extract_floats(stdout)
    expected = extract_floats(golden_text)
    # F-17/audit HIGH: "nada que comparar" NO certifica paridad numérica. Si el golden
    # (o la salida) no tiene números, no se puede afirmar PASS por golden_output.
    if not actual and not expected:
        return ParityResult(
            ok=False,
            detail="golden_output: sin valores numericos para comparar (no se certifica)",
        )
    return compare_floats(actual, expected, rtol, atol)
