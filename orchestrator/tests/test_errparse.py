"""tests/test_errparse.py — pure L2 tests for ``core.errparse``.

Fixtures live in ``tests/fixtures/errparse/`` and are committed
verbatim samples of hipcc/clang output, used to drive the regex
that powers the build loop (blueprint §6.1).
"""

from __future__ import annotations

from pathlib import Path

from core.errparse import group, parse, signature
from core.schemas import BuildError, ErrorGroup


FIXTURES = Path(__file__).parent / "fixtures" / "errparse"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_detects_leftover_cuda_include() -> None:
    raw = _fixture("build_leftover_include.txt")
    errors = parse(raw)

    assert errors, "parser must find at least one error in the leftover-include fixture"
    e = errors[0]
    assert isinstance(e, BuildError)
    assert e.file.endswith("cuda_runtime.h")
    assert e.line == 1
    assert e.col == 10
    assert "cuda_runtime.h" in e.message
    assert "file not found" in e.message
    assert e.signature and len(e.signature) == 40  # sha1 hexdigest


def test_parse_detects_undeclared_identifier_cudaMemcpy() -> None:
    raw = _fixture("build_undeclared_api.txt")
    errors = parse(raw)

    matches = [e for e in errors if "use of undeclared identifier 'cudaMemcpy'" in e.message]
    assert matches, f"expected the cudaMemcpy error, got: {[e.message for e in errors]}"
    e = matches[0]
    assert e.file == "src/kernel.cu"
    assert e.line == 42
    assert e.col == 5
    assert e.signature


def test_signature_collapses_numeric_differences() -> None:
    """Two messages that differ only in a number MUST share a signature.

    This is the cornerstone of the dedupe: a different argument count
    or array size does not make the error a new root cause.
    """
    a = signature("src/foo.cu", "expected 42 arguments for call to 'bar'")
    b = signature("src/foo.cu", "expected 7 arguments for call to 'bar'")
    assert a == b, "numbers in the message must normalise to '#'"


def test_signature_collapses_hex_addresses() -> None:
    """Hex addresses ``0x[hex]`` must normalise to ``@``."""
    a = signature("src/foo.cu", "invalid device pointer 0xdeadbeef at kernel entry")
    b = signature("src/foo.cu", "invalid device pointer 0x1234abcd at kernel entry")
    assert a == b


def test_signature_distinguishes_quoted_identifiers() -> None:
    """NEGATIVE test: messages differing only inside single quotes
    MUST produce different signatures.

    Without this guarantee, the loop would collapse every
    unconverted-CUDA-API error into one giant group and the patcher
    would have no way to know which symbol it was actually trying
    to convert.
    """
    a = signature("src/foo.cu", "use of undeclared identifier 'cudaMemcpy'")
    b = signature("src/foo.cu", "use of undeclared identifier 'cudaFree'")
    assert a != b, "different identifiers in single quotes must yield different signatures"


def test_signature_uses_basename_not_full_path() -> None:
    """Same basename, different absolute roots → same signature."""
    a = signature("/build/foo.cu", "use of undeclared identifier 'cudaMemcpy'")
    b = signature("/workspace/run-42/foo.cu", "use of undeclared identifier 'cudaMemcpy'")
    assert a == b


def test_group_collapses_cascade_into_single_group() -> None:
    raw = _fixture("build_cascade.txt")
    errors = parse(raw)
    assert len(errors) == 5, f"cascade fixture must yield 5 errors, got {len(errors)}"

    groups = group(errors)
    assert len(groups) == 1, f"cascade must collapse to one group, got {len(groups)}"
    g = groups[0]
    assert isinstance(g, ErrorGroup)
    assert len(g.errors) == 5
    assert g.klass is None
    assert g.attempts == 0
    assert g.status == "open"
    # group signature is the msg-only root-cause key
    assert g.signature and len(g.signature) == 40
    # every member of the group has the same msg signature
    from core.errparse import _msg_signature  # intentional: verify internals
    expected_msg_sig = _msg_signature("use of undeclared identifier 'warpSize'")
    assert g.signature == expected_msg_sig


def test_parse_caps_at_max_errors() -> None:
    lines = [f"src/a.cu:{i + 1}:1: error: oops {i}" for i in range(50)]
    raw = "\n".join(lines) + "\n"

    capped = parse(raw, max_errors=30)
    assert len(capped) == 30, "parse must cap at max_errors"

    # Sanity: a smaller cap is honoured too, and we always keep the FIRST N.
    smaller = parse(raw, max_errors=5)
    assert len(smaller) == 5
    assert smaller[0].line == 1
    assert smaller[-1].line == 5


def test_parse_linker_undefined_reference() -> None:
    raw = (
        "/usr/bin/ld: src/main.o: in function `main':\n"
        "/usr/bin/ld: undefined reference to `foo'\n"
        "/usr/bin/ld: undefined reference to `bar'\n"
    )
    errors = parse(raw)

    link_errors = [e for e in errors if e.file == "<link>"]
    assert len(link_errors) == 2, f"expected 2 linker errors, got {len(link_errors)}"
    for le in link_errors:
        assert le.line == 0
        assert le.col == 0
        assert "undefined reference" in le.message
        assert le.signature


def test_parse_ignores_meta_lines() -> None:
    """``N errors generated.`` and the command-line echo must not be parsed."""
    raw = "hipcc -O2 -c src/foo.cu\nsrc/foo.cu:1:1: error: bad\n1 error generated.\n"
    errors = parse(raw)
    assert len(errors) == 1
    assert errors[0].message == "bad"


def test_error_without_column_is_parsed():
    """hipcc/clang a veces emiten error sin columna: 'foo.cu:42: fatal error: ...'
    (hallazgo HIGH audit Gemini). Debe parsearse con col=0, no descartarse."""
    from core.errparse import parse
    raw = "src/foo.cu:42: fatal error: 'cuda_runtime.h' file not found\n"
    errs = parse(raw)
    assert len(errs) == 1
    assert errs[0].file == "src/foo.cu"
    assert errs[0].line == 42
    assert errs[0].col == 0
    assert "cuda_runtime.h" in errs[0].message
