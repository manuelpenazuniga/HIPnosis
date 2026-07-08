"""tests/test_wave64.py — pure L2 tests for ``core.wave64``.

The linter is the product's differential weapon: it catches warp=32
assumptions that silently break on AMD wave64. The catalog is CLOSED
(blueprint §5.2) and the explanations are FIXED text (F-17) — these
tests pin both down.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import wave64
from core.schemas import Wave64Finding
from core.wave64 import (
    EXPL_W01,
    EXPL_W02,
    EXPL_W03,
    EXPL_W04,
    EXPL_W05,
    EXPL_W06,
    EXPL_W07,
    lint,
    lint_file,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "wave64"
SYNTHETIC = FIXTURE_DIR / "wave64_patterns.cu"
REAL = FIXTURE_DIR / "shuffle_main.cu"


# ---------------------------------------------------------------------------
# Catalog is closed
# ---------------------------------------------------------------------------

EXPECTED_IDS = {"W01", "W02", "W03", "W04", "W05", "W06", "W07"}
EXPECTED_EXPLANATIONS = {
    "W01": EXPL_W01,
    "W02": EXPL_W02,
    "W03": EXPL_W03,
    "W04": EXPL_W04,
    "W05": EXPL_W05,
    "W06": EXPL_W06,
    "W07": EXPL_W07,
}
EXPECTED_SEVERITY = {
    "W01": "correctness",
    "W02": "correctness",
    "W03": "correctness",
    "W04": "suspicious",
    "W05": "suspicious",
    "W06": "suspicious",
    "W07": "suspicious",
}


# ---------------------------------------------------------------------------
# Synthetic fixture: the catalog is fully exercised
# ---------------------------------------------------------------------------

def test_synthetic_fixture_detects_all_seven_patterns() -> None:
    src = SYNTHETIC.read_text(encoding="utf-8")
    findings = lint(src, filename=str(SYNTHETIC))

    ids = {f.pattern_id for f in findings}
    assert ids == EXPECTED_IDS, (
        f"expected all 7 patterns, got {sorted(ids)} (missing: "
        f"{sorted(EXPECTED_IDS - ids)})"
    )


def test_synthetic_fixture_explanations_are_fixed_catalog() -> None:
    src = SYNTHETIC.read_text(encoding="utf-8")
    findings = lint(src, filename=str(SYNTHETIC))

    for f in findings:
        assert f.explanation == EXPECTED_EXPLANATIONS[f.pattern_id], (
            f"explanation drift on {f.pattern_id}: {f.explanation!r}"
        )


def test_synthetic_fixture_severity_matches_catalog() -> None:
    src = SYNTHETIC.read_text(encoding="utf-8")
    findings = lint(src, filename=str(SYNTHETIC))

    for f in findings:
        assert f.severity == EXPECTED_SEVERITY[f.pattern_id], (
            f"severity drift on {f.pattern_id}: {f.severity!r}"
        )


def test_synthetic_fixture_findings_are_pydantic_models() -> None:
    """The contract is ``list[Wave64Finding]``; instances must validate."""
    findings = lint("int x = threadIdx.x & 31;", filename="<t>")
    assert findings, "guard: this line should produce at least one finding"
    for f in findings:
        assert isinstance(f, Wave64Finding)


def test_synthetic_fixture_line_numbers_are_1based() -> None:
    """Each pattern fires on a known, unique line in the synthetic fixture."""
    src = SYNTHETIC.read_text(encoding="utf-8")
    findings = lint(src, filename=str(SYNTHETIC))

    expected = {
        "W01": 16,
        "W02": 22,
        "W03": 28,
        "W04": 34,
        "W05": 40,
        "W06": 46,
    }
    by_id = {}
    for f in findings:
        # First occurrence per pattern_id wins; the fixture is designed so
        # each pattern has exactly one unique "owner" line.
        by_id.setdefault(f.pattern_id, []).append(f.line)

    for pid, lineno in expected.items():
        assert lineno in by_id[pid], (
            f"{pid} expected on line {lineno}, got lines {by_id[pid]}"
        )

    # W07 has two forms: define (51) and constexpr (52). Both must show up.
    assert sorted(by_id["W07"]) == [51, 52], by_id["W07"]


def test_synthetic_fixture_negative_cases_produce_no_findings() -> None:
    """The block comment, line comment and string literal at the bottom
    of the synthetic fixture must NOT contribute any finding."""
    src = SYNTHETIC.read_text(encoding="utf-8")
    findings = lint(src, filename=str(SYNTHETIC))

    # Negative block starts at line 56 in the fixture.
    neg_lines = [f for f in findings if f.line >= 56]
    assert neg_lines == [], (
        f"negative cases leaked findings: {[(f.line, f.pattern_id) for f in neg_lines]}"
    )


# ---------------------------------------------------------------------------
# Stripper: comments and strings must be neutralised
# ---------------------------------------------------------------------------

def test_commented_ballot_does_not_trigger_w01() -> None:
    src = (
        "int x = 0;\n"
        "// __ballot(0xffffffff) commented out\n"
        "int y = 1;\n"
    )
    findings = lint(src, filename="<t>")
    w01 = [f for f in findings if f.pattern_id == "W01"]
    assert w01 == [], (
        f"commented __ballot(0xffffffff) must not trigger W01, got {w01}"
    )


def test_block_commented_ballot_does_not_trigger_w01() -> None:
    src = (
        "/* __ballot(0xffffffff) inside a\n"
        "   block comment that spans\n"
        "   multiple lines */\n"
        "int y = 1;\n"
    )
    findings = lint(src, filename="<t>")
    w01 = [f for f in findings if f.pattern_id == "W01"]
    assert w01 == [], (
        f"block-commented __ballot(0xffffffff) must not trigger W01, got {w01}"
    )


def test_string_literal_ballot_does_not_trigger_w01() -> None:
    src = (
        'const char *msg = "__ballot(0xffffffff) and __popc(__ballot(0x1))";\n'
        "int y = 1;\n"
    )
    findings = lint(src, filename="<t>")
    w01 = [f for f in findings if f.pattern_id == "W01"]
    assert w01 == [], (
        f"string-literal __ballot(0xffffffff) must not trigger W01, got {w01}"
    )


def test_string_literal_w06_does_not_trigger_w06() -> None:
    src = (
        'const char *msg = "tiled_partition<32> is a CG concept";\n'
        "int y = 1;\n"
    )
    findings = lint(src, filename="<t>")
    w06 = [f for f in findings if f.pattern_id == "W06"]
    assert w06 == [], (
        f"string-literal tiled_partition<32> must not trigger W06, got {w06}"
    )


def test_stripper_preserves_line_numbers_after_block_comment() -> None:
    """A multi-line block comment must NOT shift the line number of a
    finding that appears after it. The stripper preserves newlines, so
    the 1-based line of the finding must match the original source."""
    src = (
        "/* line 1\n"           # line 1
        "   line 2\n"           # line 2
        "   line 3 */\n"        # line 3
        "int x = 0;\n"          # line 4
        "use_mask(__ballot(0xffffffff));\n"  # line 5: W01 here
    )
    findings = lint(src, filename="<t>")
    w01 = [f for f in findings if f.pattern_id == "W01"]
    assert len(w01) == 1, f"expected exactly one W01, got {w01}"
    assert w01[0].line == 5, (
        f"line number drifted across the block comment: got {w01[0].line}"
    )


# ---------------------------------------------------------------------------
# W05 guard: requires threadIdx|laneId|lane_id on the same line
# ---------------------------------------------------------------------------

def test_w05_requires_lane_guard_present() -> None:
    """Bare `& 31` without threadIdx/laneId must NOT trigger W05."""
    src = "int x = y & 31;\n"
    findings = lint(src, filename="<t>")
    w05 = [f for f in findings if f.pattern_id == "W05"]
    assert w05 == [], f"`y & 31` without threadIdx must not trigger W05, got {w05}"


def test_w05_fires_with_lane_guard() -> None:
    """`threadIdx.x & 31` MUST trigger W05 (lane arithmetic)."""
    src = "int x = threadIdx.x & 31;\n"
    findings = lint(src, filename="<t>")
    w05 = [f for f in findings if f.pattern_id == "W05"]
    assert len(w05) == 1, f"threadIdx.x & 31 must trigger W05, got {w05}"


def test_w05_does_not_fire_for_wave64_lane_step() -> None:
    """`threadIdx.x / 64` is the CORRECT wave64 step; W05 must stay silent."""
    src = "int x = threadIdx.x / 64;\n"
    findings = lint(src, filename="<t>")
    w05 = [f for f in findings if f.pattern_id == "W05"]
    assert w05 == [], f"threadIdx.x / 64 (wave64) must not trigger W05, got {w05}"


def test_w05_does_not_fire_on_commented_lane_arithmetic() -> None:
    """`threadIdx.x & 31` inside a line comment must NOT trigger W05."""
    src = "int x = 0; // threadIdx.x & 31\n"
    findings = lint(src, filename="<t>")
    w05 = [f for f in findings if f.pattern_id == "W05"]
    assert w05 == [], f"commented lane arithmetic must not trigger W05, got {w05}"


# ---------------------------------------------------------------------------
# W07 variants (case-insensitive)
# ---------------------------------------------------------------------------

def test_w07_define_form_case_insensitive() -> None:
    """`#define warp_size 32` (lowercase) must still trigger W07."""
    src = "#define warp_size 32\n"
    findings = lint(src, filename="<t>")
    w07 = [f for f in findings if f.pattern_id == "W07"]
    assert len(w07) == 1, f"lowercase #define warp_size 32 must trigger W07, got {w07}"


def test_w07_constexpr_form() -> None:
    """`constexpr X = 32; ... warp ...` must trigger W07."""
    src = "constexpr WARP = 32; int warp = WARP;\n"
    findings = lint(src, filename="<t>")
    w07 = [f for f in findings if f.pattern_id == "W07"]
    assert len(w07) == 1, f"constexpr WARP = 32; ... warp must trigger W07, got {w07}"


# ---------------------------------------------------------------------------
# Snippet: line ± 2 context window
# ---------------------------------------------------------------------------

def test_snippet_is_line_plus_minus_two_joined_by_newline() -> None:
    src = "\n" * 5 + "use_mask(__ballot(0xffffffff));\n" + "\n" * 5
    findings = lint(src, filename="<t>")
    assert len(findings) == 1
    snippet = findings[0].snippet
    # 5 lines of context: idx-2 .. idx+2 (0-based), joined by \n
    assert snippet.count("\n") == 4, (
        f"snippet should be 5 lines joined by \\n, got: {snippet!r}"
    )
    # The match line is the 3rd (index 2) in the snippet window.
    lines = snippet.split("\n")
    assert "use_mask(__ballot(0xffffffff));" in lines[2]


# ---------------------------------------------------------------------------
# L2 purity: only core.schemas + re (F-17 / layering)
# ---------------------------------------------------------------------------

def test_l2_purity_imports_only_core_schemas_and_stdlib() -> None:
    """L2 contract: wave64.py may import only ``core.schemas`` and stdlib."""
    import ast
    import inspect

    source = inspect.getsource(wave64)
    tree = ast.parse(source)

    allowed = {"core.schemas"}
    stdlib_roots = {
        "annotations", "ast", "collections", "contextlib", "copy", "dataclasses",
        "datetime", "enum", "functools", "io", "itertools", "json", "os",
        "pathlib", "re", "sys", "typing", "__future__",
    }

    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in stdlib_roots:
                    bad.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            # ``from __future__ import ...`` is fine; treat as stdlib.
            if node.module == "__future__":
                continue
            if module not in stdlib_roots and node.module not in allowed:
                bad.append(f"from {node.module} import ...")

    assert bad == [], (
        "core.wave64 is L2: only core.schemas and stdlib are allowed, "
        f"found: {bad}"
    )


# ---------------------------------------------------------------------------
# lint_file: real fixture smoke test
# ---------------------------------------------------------------------------

def test_lint_file_on_real_hecbench_fixture_runs_and_returns_list() -> None:
    """Smoke test on a real HeCBench .cu file. We don't pin a count
    (this is a regression-guard, not a snapshot): the contract is just
    ``lint_file(path) -> list[Wave64Finding]`` without raising."""
    assert REAL.exists(), f"real fixture missing: {REAL}"
    findings = lint_file(str(REAL))
    assert isinstance(findings, list)
    for f in findings:
        assert isinstance(f, Wave64Finding)
        assert f.pattern_id in EXPECTED_IDS


def test_lint_file_filename_is_set_on_findings() -> None:
    findings = lint_file(str(REAL))
    for f in findings:
        assert f.file == str(REAL), f"file metadata not propagated: {f.file!r}"


# ---------------------------------------------------------------------------
# Catalog: findings only ever carry W01..W07
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pid", sorted(EXPECTED_IDS))
def test_each_catalog_id_appears_at_least_once_on_synthetic(pid: str) -> None:
    """Per-pattern guard: the synthetic fixture must hit each W01..W07."""
    src = SYNTHETIC.read_text(encoding="utf-8")
    findings = lint(src, filename=str(SYNTHETIC))
    assert any(f.pattern_id == pid for f in findings), (
        f"synthetic fixture failed to exercise {pid}"
    )
