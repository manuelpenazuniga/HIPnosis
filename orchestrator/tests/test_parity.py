"""tests/test_parity.py — tests for core/parity.py (F-09).

El comparador ES el producto — probarlo a fondo.
"""

from __future__ import annotations

import math

import pytest

from core.parity import (
    ParityResult,
    check_golden,
    check_self_check,
    compare_floats,
    extract_floats,
)


class TestExtractFloats:
    def test_simple_numbers(self):
        assert extract_floats("Average time 12.5 ms, error 1.2e-5") == [
            12.5,
            1.2e-5,
        ]

    def test_negative_numbers(self):
        assert extract_floats("values: -3.14, -42, -1.2e-5") == [
            -3.14,
            -42.0,
            -1.2e-5,
        ]

    def test_scientific_notation(self):
        assert extract_floats("1e10, 2.5e-3, -1.2E+5") == [1e10, 2.5e-3, -1.2e5]

    def test_leading_dot(self):
        assert extract_floats(".5, .123") == [0.5, 0.123]

    def test_trailing_dot(self):
        assert extract_floats("1.") == [1.0]

    def test_integers(self):
        assert extract_floats("42 and 13") == [42.0, 13.0]

    def test_nan(self):
        result = extract_floats("value is nan")
        assert len(result) == 1
        assert math.isnan(result[0])

    def test_inf(self):
        result = extract_floats("value is inf")
        assert len(result) == 1
        assert result[0] == math.inf

    def test_negative_inf(self):
        result = extract_floats("value is -inf")
        assert len(result) == 1
        assert result[0] == -math.inf

    def test_infinity(self):
        result = extract_floats("value is infinity")
        assert len(result) == 1
        assert result[0] == math.inf

    def test_negative_infinity(self):
        result = extract_floats("value is -infinity")
        assert len(result) == 1
        assert result[0] == -math.inf

    def test_plus_inf(self):
        result = extract_floats("+inf")
        assert len(result) == 1
        assert result[0] == math.inf

    def test_mixed_output(self):
        text = "x=1.0, y=2.5e-1, ok=nan, overflow=inf"
        result = extract_floats(text)
        assert len(result) == 4
        assert result[0] == 1.0
        assert result[1] == 0.25
        assert math.isnan(result[2])
        assert result[3] == math.inf

    def test_empty(self):
        assert extract_floats("no numbers here") == []

    def test_many_numbers(self):
        text = " ".join(str(n) for n in range(10))
        assert extract_floats(text) == [float(n) for n in range(10)]

    def test_no_partial_word_match_nan(self):
        assert extract_floats("nanosecond") == []

    def test_no_partial_word_match_inf(self):
        assert extract_floats("infinite loop") == []


class TestCompareFloats:
    def test_identical(self):
        r = compare_floats([1.0, 2.0], [1.0, 2.0])
        assert r.ok
        assert r.n_compared == 2

    def test_close_within_tolerance(self):
        r = compare_floats([1.0, 2.0], [1.0000001, 2.0], rtol=1e-5)
        assert r.ok

    def test_not_close(self):
        r = compare_floats([1.0], [1.1], rtol=1e-5)
        assert not r.ok
        assert "indice 0" in r.detail
        assert "1.0" in r.detail
        assert "1.1" in r.detail

    def test_count_mismatch(self):
        r = compare_floats([1, 2], [1, 2, 3])
        assert not r.ok
        assert "conteo distinto" in r.detail
        assert "2 vs 3" in r.detail

    def test_f09_float_inexact(self):
        """F-09: 0.1+0.2 != 0.3 en comparacion exacta. rtol/atol DEBE dar OK."""
        r = compare_floats([0.1 + 0.2], [0.3])
        assert r.ok, (
            f"F-09 VIOLATED: comparacion exacta daria False. "
            f"detail: {r.detail}"
        )

    def test_nan_equal(self):
        """nan==nan se considera IGUAL (decision documentada)."""
        r = compare_floats([math.nan], [math.nan])
        assert r.ok

    def test_inf_equal(self):
        r = compare_floats([math.inf], [math.inf])
        assert r.ok

    def test_inf_neq_negative_inf(self):
        r = compare_floats([math.inf], [-math.inf])
        assert not r.ok

    def test_negative_inf_equal(self):
        r = compare_floats([-math.inf], [-math.inf])
        assert r.ok

    def test_detail_on_success(self):
        r = compare_floats([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert "3 valores comparados" in r.detail

    def test_detail_on_failure(self):
        r = compare_floats([1.0], [2.0], rtol=1e-5, atol=1e-8)
        assert not r.ok
        assert "indice 0" in r.detail

    def test_close_near_zero(self):
        r = compare_floats([0.0], [1e-10], atol=1e-8, rtol=1e-5)
        assert r.ok

    def test_not_close_near_zero(self):
        r = compare_floats([0.0], [1e-6], atol=1e-8, rtol=1e-5)
        assert not r.ok

    def test_empty_both(self):
        r = compare_floats([], [])
        assert r.ok
        assert r.n_compared == 0

    def test_empty_vs_nonempty(self):
        r = compare_floats([1.0], [])
        assert not r.ok
        assert "conteo distinto" in r.detail

    def test_custom_tolerances(self):
        r = compare_floats([1.0], [1.1], rtol=0.2, atol=0.0)
        assert r.ok

    def test_nan_vs_number(self):
        r = compare_floats([math.nan], [1.0])
        assert not r.ok

    def test_atol_gate_for_small_values(self):
        r = compare_floats([1e-10], [2e-10], rtol=1e-5, atol=1e-7)
        assert r.ok


class TestCheckSelfCheck:
    def test_pass_found(self):
        r = check_self_check("Tests completed: PASS", "PASS")
        assert r.ok
        assert "encontrado" in r.detail

    def test_fail_not_found(self):
        r = check_self_check("Tests completed: FAIL", "PASS")
        assert not r.ok
        assert "no encontrado" in r.detail

    def test_regex_pattern(self):
        r = check_self_check("result: OK (1234)", r"OK\s*\(\d+\)")
        assert r.ok

    def test_partial_match_fail(self):
        r = check_self_check("COMPASS pointing north", r"\bPASS\b")
        assert not r.ok


class TestCheckGolden:
    def test_identical(self):
        r = check_golden("result: 12.5", "result: 12.5")
        assert r.ok

    def test_close_values(self):
        r = check_golden("result: 12.5000000001", "result: 12.5")
        assert r.ok
        assert r.n_compared == 1

    def test_different_count(self):
        r = check_golden("12.5 and 13.0", "12.5")
        assert not r.ok
        assert "conteo distinto" in r.detail

    def test_same_floats_different_text(self):
        r = check_golden(
            "elapsed: 12.5000 ms",
            "time: 12.5",
        )
        assert r.ok
        assert r.n_compared == 1

    def test_different_values(self):
        r = check_golden("result: 5.0", "result: 3.0", rtol=1e-5)
        assert not r.ok
        assert "indice 0" in r.detail

    def test_mixed_nan_inf(self):
        r = check_golden("nan, inf, -inf", "nan, inf, -inf")
        assert r.ok
        assert r.n_compared == 3


def test_result_dataclass():
    r = ParityResult(ok=True, detail="todo bien", n_compared=42)
    assert r.ok
    assert r.detail == "todo bien"
    assert r.n_compared == 42
