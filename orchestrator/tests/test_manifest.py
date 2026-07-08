"""tests/test_manifest.py — pure L2 tests for ``core.manifest``.

The manifest is the contract that makes the product general (blueprint
§7.1). These tests pin its schema, its fail-closed validation, and the
SCAN-side heuristic that produces a draft.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.manifest import (
    BuildSpec,
    Manifest,
    RunSpec,
    VerifySpec,
    draft_manifest,
    load_manifest,
)
from core.schemas import ScanResult


FIXTURES = Path(__file__).parent / "fixtures" / "manifests"


def _fixture(name: str) -> str:
    return str(FIXTURES / name)


# ---------------------------------------------------------------------------
# load_manifest — happy path on the canonical sample
# ---------------------------------------------------------------------------

def test_load_manifest_sample_self_check() -> None:
    m = load_manifest(_fixture("sample.yaml"))

    assert isinstance(m, Manifest)
    assert m.build == BuildSpec(cmd="make -f Makefile", dir="src/reduction-cuda")
    assert m.run == RunSpec(cmd="./main 1000000 100", timeout_s=120)
    assert m.verify == VerifySpec(
        mode="self_check",
        pass_regex="PASS",
        golden_file=None,
        numeric_rtol=1e-5,
        numeric_atol=1e-8,
    )
    assert m.timing_regex == "Average kernel execution time.*?([\\d.]+)"
    # Defaults baked in by the loader, not the operator
    assert m.verify.numeric_rtol == 1e-5
    assert m.verify.numeric_atol == 1e-8
    # raw source preserved for debugging / round-trip
    assert m.source and "build:" in m.source


# ---------------------------------------------------------------------------
# load_manifest — fail-closed validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body, needle",
    [
        # invalid mode
        (
            "build: { cmd: 'make', dir: '.' }\n"
            "run: { cmd: './main', timeout_s: 10 }\n"
            "verify: { mode: oracle, pass_regex: 'PASS' }\n",
            "verify.mode",
        ),
        # self_check without pass_regex
        (
            "build: { cmd: 'make', dir: '.' }\n"
            "run: { cmd: './main', timeout_s: 10 }\n"
            "verify: { mode: self_check }\n",
            "pass_regex",
        ),
        # golden_output without golden_file
        (
            "build: { cmd: 'make', dir: '.' }\n"
            "run: { cmd: './main', timeout_s: 10 }\n"
            "verify: { mode: golden_output }\n",
            "golden_file",
        ),
        # missing build.cmd
        (
            "build: { dir: '.' }\n"
            "run: { cmd: './main', timeout_s: 10 }\n"
            "verify: { mode: none }\n",
            "build.cmd",
        ),
        # empty build.cmd
        (
            "build: { cmd: '   ', dir: '.' }\n"
            "run: { cmd: './main', timeout_s: 10 }\n"
            "verify: { mode: none }\n",
            "build.cmd",
        ),
        # missing run.cmd
        (
            "build: { cmd: 'make', dir: '.' }\n"
            "run: { timeout_s: 10 }\n"
            "verify: { mode: none }\n",
            "run.cmd",
        ),
        # top-level not a mapping
        (
            "- just a list\n",
            "top-level",
        ),
    ],
)
def test_load_manifest_rejects_bad_input(tmp_path: Path, body: str, needle: str) -> None:
    p = tmp_path / "hipnosis.yaml"
    p.write_text(body)
    with pytest.raises(ValueError, match=needle):
        load_manifest(str(p))


def test_load_manifest_missing_file() -> None:
    with pytest.raises(ValueError, match="not found"):
        load_manifest(str(FIXTURES / "does-not-exist.yaml"))


def test_load_manifest_invalid_yaml(tmp_path: Path) -> None:
    p = tmp_path / "hipnosis.yaml"
    p.write_text("build: { cmd: 'make' : : oops")
    with pytest.raises(ValueError, match="invalid YAML"):
        load_manifest(str(p))


def test_load_manifest_timing_regex_requires_capture_group(tmp_path: Path) -> None:
    p = tmp_path / "hipnosis.yaml"
    p.write_text(
        "build: { cmd: 'make', dir: '.' }\n"
        "run: { cmd: './main', timeout_s: 10 }\n"
        "verify: { mode: self_check, pass_regex: 'PASS' }\n"
        "timing_regex: 'no capture here'\n"
    )
    with pytest.raises(ValueError, match="capture group"):
        load_manifest(str(p))


# ---------------------------------------------------------------------------
# load_manifest — happy path on the two non-self_check modes
# ---------------------------------------------------------------------------

def test_load_manifest_golden_output_mode(tmp_path: Path) -> None:
    p = tmp_path / "hipnosis.yaml"
    p.write_text(
        "build: { cmd: 'make', dir: '.' }\n"
        "run: { cmd: './main', timeout_s: 10 }\n"
        "verify: { mode: golden_output, golden_file: 'expected.txt', numeric_rtol: 0.0001 }\n"
    )
    m = load_manifest(str(p))
    assert m.verify.mode == "golden_output"
    assert m.verify.golden_file == "expected.txt"
    assert m.verify.numeric_rtol == 0.0001


def test_load_manifest_no_oracle_mode(tmp_path: Path) -> None:
    p = tmp_path / "hipnosis.yaml"
    p.write_text(
        "build: { cmd: 'make', dir: '.' }\n"
        "run: { cmd: './main', timeout_s: 10 }\n"
        "verify: { mode: none }\n"
    )
    m = load_manifest(str(p))
    assert m.verify.mode == "none"
    assert m.verify.pass_regex is None
    assert m.verify.golden_file is None


# ---------------------------------------------------------------------------
# draft_manifest — SCAN-side heuristic
# ---------------------------------------------------------------------------

def _scan(files: list[str], libs: list[str] | None = None) -> ScanResult:
    return ScanResult(
        files_cuda=files,
        loc_kernels=42,
        api_calls={"cudaMalloc": 1},
        libs=libs or [],
        build_system="make",
        wave64_findings=[],
        difficulty="easy",
    )


def test_draft_manifest_minimal_scan_returns_healthy_defaults() -> None:
    m = draft_manifest(_scan(files=["main.cu", "aux.cuh"]), repo_dir="/tmp/repo")

    assert isinstance(m, Manifest)
    # self_check with PASS is the HeCBench convention; we use it as the
    # default because most of the demo corpus matches that pattern.
    assert m.verify.mode == "self_check"
    assert m.verify.pass_regex == "PASS"
    # run defaults: 120 s timeout, ./main invocation
    assert m.run.timeout_s == 120
    assert m.run.cmd == "./main"
    # build defaults
    assert m.build.cmd == "make -f Makefile"
    assert m.build.dir == "."
    # timing is optional in the draft
    assert m.timing_regex is None
    # no source — the drafter is not a parser
    assert m.source is None


def test_draft_manifest_picks_main_binary_when_present() -> None:
    files = ["main.cu", "main", "kernel.cu"]
    m = draft_manifest(_scan(files=files), repo_dir="/tmp/repo")
    # The drafter recognises a binary named ``main`` and uses it for run
    assert m.run.cmd == "./main"
    # And the build heuristic still defaults to a Makefile target
    assert m.build.cmd == "make -f Makefile"


def test_draft_manifest_does_not_execute_anything(tmp_path: Path) -> None:
    """Sanity: drafting must be pure — no subprocess, no filesystem writes."""
    m = draft_manifest(_scan(files=["main.cu"]), repo_dir=str(tmp_path))
    assert isinstance(m, Manifest)
    # No side effects in the temp dir
    assert os.listdir(tmp_path) == []
