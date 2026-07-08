"""tests/test_oracle_mock.py — L3 pure tests for ``core.oracle.mock``.

Uses the bundled fixtures in ``tests/fixtures/mock_build/``; no network,
no subprocess, no GPU. Validates the INV-6 contract: the mock and the
eventual real oracle must look identical to the loop, so the behaviour
we assert here is what ``core.phases.loop`` will rely on at runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.oracle.base import Oracle
from core.oracle.mock import MockOracle
from core.schemas import BuildResult, RunResult


FIXTURES = Path(__file__).parent / "fixtures" / "mock_build"


def test_mock_oracle_is_an_oracle() -> None:
    assert isinstance(MockOracle(str(FIXTURES)), Oracle)


def test_build_advances_through_fixtures_and_converges() -> None:
    oracle = MockOracle(str(FIXTURES))

    counts = [oracle.build().count for _ in range(4)]

    assert counts[0] > counts[1] > counts[2] == 0
    assert counts[3] == 0


def test_first_build_is_not_ok() -> None:
    b = MockOracle(str(FIXTURES)).build()

    assert isinstance(b, BuildResult)
    assert b.ok is False
    assert b.count > 0
    assert b.returncode == 1
    assert b.raw_output
    assert ": error:" in b.raw_output or ": fatal error:" in b.raw_output


def test_last_build_is_clean_and_idempotent() -> None:
    oracle = MockOracle(str(FIXTURES))

    while oracle.build().ok is False:
        pass

    final = oracle.build()
    assert final.ok is True
    assert final.count == 0
    assert final.returncode == 0
    assert final.raw_output

    again = oracle.build()
    assert again.ok is True
    assert again.count == 0
    assert again.returncode == 0


def test_run_returns_pass_from_run_txt() -> None:
    r = MockOracle(str(FIXTURES)).run()

    assert isinstance(r, RunResult)
    assert r.ran is True
    assert r.exit_code == 0
    assert "PASS" in r.stdout
    assert r.timing is None


def test_run_ignores_args_but_stays_deterministic() -> None:
    oracle = MockOracle(str(FIXTURES))

    a = oracle.run()
    b = oracle.run(run_cmd="echo whatever", timeout_s=999)

    assert a.stdout == b.stdout
    assert a.exit_code == b.exit_code == 0
    assert a.ran is b.ran is True


def test_missing_run_fixture_defaults_to_pass(tmp_path: Path) -> None:
    (tmp_path / "build_01.txt").write_text("Build succeeded.\n")

    r = MockOracle(str(tmp_path)).run()

    assert r.ran is True
    assert r.exit_code == 0
    assert r.stdout == "PASS\n"


def test_no_build_fixtures_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        MockOracle(str(tmp_path))


def test_error_counting_is_crude_line_match(tmp_path: Path) -> None:
    (tmp_path / "build_01.txt").write_text(
        "warning: something fishy\n"
        "src/foo.cpp:1:1: error: bad\n"
        "src/foo.cpp:2:1: fatal error: worse\n"
        "note: in expansion of macro\n"
        "1 error generated.\n"
    )

    b = MockOracle(str(tmp_path)).build()

    assert b.count == 2
    assert b.ok is False
    assert b.returncode == 1


def test_clean_fixture_is_ok(tmp_path: Path) -> None:
    (tmp_path / "build_01.txt").write_text("Build succeeded.\n")

    b = MockOracle(str(tmp_path)).build()

    assert b.ok is True
    assert b.count == 0
    assert b.returncode == 0
