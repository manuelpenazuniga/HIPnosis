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


_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

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
    """Modo self_check: el benchmark imprime PASS/FAIL."""
    ok = re.search(pass_regex, stdout) is not None
    return ParityResult(
        ok=ok,
        detail=f"self_check: patron '{pass_regex}' {'encontrado' if ok else 'no encontrado'}",
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
    return compare_floats(actual, expected, rtol, atol)
