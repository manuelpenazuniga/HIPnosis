"""tests/test_build_loop.py — T14b wiring tests (mock, sin red, sin GPU).

Covers:
  1. make_loop_functions: classify, decide_tier deterministic.
  2. Camino deterministic: archivos reales en workspace temporal → sustitucion global.
  3. PIPELINE COMPLETO EN MOCK: run_full_pipeline_mock sobre fixtures/bsw → DONE.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from core.config import Config
from core.errparse import group as err_group
from core.errparse import parse as err_parse
from core.oracle.mock import MockOracle
from core.phases.build_loop import (
    build_loop_handler,
    make_loop_functions,
    run_full_pipeline_mock,
)
from core.schemas import BuildError, ErrorGroup, RunState
from core.state import PipelineContext, SqliteRunStore
from core.taxonomy import load_rules
from core.trace import TraceWriter, read_events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BSW_FIXTURES = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "bsw"
)

FIXTURES_BSW = str(BSW_FIXTURES)


def _make_config(**overrides) -> Config:
    defaults = dict(
        oracle_mode="mock",
        local_llm_base_url="http://vllm:8000/v1",
        local_llm_model="google/gemma-3-27b-it",
        remote_llm_base_url="https://api.fireworks.ai/inference/v1",
        remote_llm_model="",
        fireworks_api_key="",
        hf_token="",
        github_token="",
        gpu_arch="gfx942",
        max_iterations=25,
        max_attempts_per_group=3,
        max_errors_parsed=30,
        confidence_threshold=0.6,
        price_h100_hr=0.0,
        price_mi300x_hr=0.0,
        stagnation_force_remote=3,
        stagnation_exit=5,
    )
    defaults.update(overrides)
    return Config(**defaults)


def _make_trace(tmp_path: Path, run_id: str = "run_test") -> TraceWriter:
    return TraceWriter(str(tmp_path / "trace.jsonl"), run_id)


def _make_store() -> SqliteRunStore:
    return SqliteRunStore()


def _group_with_message(
    message: str, file: str = "main.cu", line: int = 1
) -> ErrorGroup:
    e = BuildError(
        file=file, line=line, col=1, message=message, signature="x" * 40
    )
    return ErrorGroup(signature="x" * 40, errors=[e])


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@hipnosis.local"],
        cwd=str(path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test Pipeline"],
        cwd=str(path), check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# Test 1 — make_loop_functions: classify + decide_tier determinista
# ---------------------------------------------------------------------------

def test_make_loop_functions_classify_e01() -> None:
    """classify_fn sobre un grupo cuda_runtime.h → E01; decide_tier_fn → deterministic."""
    rules = load_rules()
    group = _group_with_message(
        "kernel.cu:3:10: fatal error: 'cuda_runtime.h' file not found",
        file="kernel.cu",
    )

    oracle = MockOracle(FIXTURES_BSW)
    store = _make_store()
    config = _make_config()
    trace = _make_trace(Path("/tmp"), "run_classify_test")

    run = store.create("https://example.com/repo.git")
    ctx = PipelineContext(
        run=run,
        repo_dir="/tmp",
        config=config,
        store=store,
        trace=trace,
    )
    ctx.oracle = oracle

    classify_fn, decide_tier_fn, propose_fix_fn, apply_fn = make_loop_functions(
        ctx, oracle, rules
    )

    klass = classify_fn(group)
    assert klass == "E01", f"expected E01, got {klass}"

    tier = decide_tier_fn("deterministic", 0, None)
    assert tier == "deterministic", f"expected deterministic, got {tier}"

    fix = propose_fix_fn(group, "deterministic", 0)
    assert fix != "", "deterministic propose_fix_fn must return non-empty fix template"


# ---------------------------------------------------------------------------
# Test 2 — Camino deterministico: archivos reales en workspace temporal
# ---------------------------------------------------------------------------

def test_deterministic_path_applies_substitution(tmp_path: Path) -> None:
    """E01/E02: archivos reales con cuda_runtime.h y cudaMemcpy → sustitucion global."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _init_git_repo(repo_path)

    kernel_cu = repo_path / "kernel.cu"
    kernel_cu.write_text(
        '#include <cuda_runtime.h>\n'
        '\n'
        'extern "C" void kernel() {\n'
        '  float *d;\n'
        '  cudaMalloc(&d, 1024);\n'
        '  cudaMemcpy(d, d, 1024, cudaMemcpyHostToDevice);\n'
        '  cudaFree(d);\n'
        '}\n'
    )

    main_cu = repo_path / "main.cu"
    main_cu.write_text(
        '#include <cuda_runtime.h>\n'
        '#include <stdio.h>\n'
        '\n'
        'int main() { return 0; }\n'
    )

    subprocess.run(
        ["git", "add", "-A"], cwd=str(repo_path), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo_path), check=True, capture_output=True,
    )

    rules = load_rules()
    oracle = MockOracle(FIXTURES_BSW)
    store = _make_store()
    config = _make_config(max_iterations=1)
    trace = _make_trace(tmp_path, "run_det_test")
    run = store.create("https://example.com/repo.git")

    ctx = PipelineContext(
        run=run,
        repo_dir=str(repo_path),
        config=config,
        store=store,
        trace=trace,
    )
    ctx.oracle = oracle

    classify_fn, decide_tier_fn, propose_fix_fn, apply_fn = make_loop_functions(
        ctx, oracle, rules
    )

    group = _group_with_message(
        "kernel.cu:1:10: fatal error: 'cuda_runtime.h' file not found",
        file="kernel.cu",
    )
    klass = classify_fn(group)
    assert klass == "E01", f"expected E01, got {klass}"

    tier = decide_tier_fn("deterministic", 0, None)
    assert tier == "deterministic"

    fix = propose_fix_fn(group, "deterministic", 0)
    assert fix != "", "deterministic fix template must be non-empty"

    delta = apply_fn(fix, "fix(E01): deterministic test")
    assert delta < 0, f"deterministic apply_fn must return negative delta, got {delta}"

    kernel_content = kernel_cu.read_text()
    assert "cuda_runtime.h" not in kernel_content, (
        "cuda_runtime.h should have been replaced"
    )
    assert "hip/hip_runtime.h" in kernel_content or "hip_runtime.h" in kernel_content, (
        "hip_runtime.h should be present after substitution"
    )

    # main.cu was NOT in the group's errors, so it should NOT have been modified.
    main_content = main_cu.read_text()
    assert "cuda_runtime.h" in main_content, (
        "main.cu was not in the error group — must be left untouched"
    )


# ---------------------------------------------------------------------------
# Test 3 — PIPELINE COMPLETO EN MOCK (criterio M2)
# ---------------------------------------------------------------------------

def test_full_pipeline_mock_reaches_done(tmp_path: Path) -> None:
    """Pipeline completo QUEUED→...→DONE sobre fixtures/bsw en mock.

    Verifica:
      - Run final en state DONE.
      - Trace con secuencia de fases completa.
      - Eventos 'build' en el trace con errores descendiendo.
      - Counters poblados (errors_initial, fixes_deterministic, iterations).
    """
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _init_git_repo(repo_path)

    kernel_cu = repo_path / "kernel.cu"
    kernel_cu.write_text(
        '#include <cuda_runtime.h>\n'
        '\n'
        'extern "C" void kernel() {\n'
        '  float *d;\n'
        '  cudaMalloc(&d, 1024);\n'
        '  cudaMemcpy(d, d, 1024, cudaMemcpyHostToDevice);\n'
        '  cudaFree(d);\n'
        '}\n'
    )

    main_cu = repo_path / "main.cu"
    main_cu.write_text(
        '#include <cuda_runtime.h>\n'
        '#include <stdio.h>\n'
        '\n'
        'int main() { return 0; }\n'
    )

    kernel_wrapper_cu = repo_path / "kernel_wrapper.cu"
    kernel_wrapper_cu.write_text(
        '#include <cuda_runtime.h>\n'
        '\n'
        'void launch() {}\n'
    )

    subprocess.run(
        ["git", "add", "-A"], cwd=str(repo_path), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo_path), check=True, capture_output=True,
    )

    store = SqliteRunStore(str(tmp_path / "runs.db"))
    config = _make_config()
    run = store.create("https://example.com/repo.git")
    trace = _make_trace(tmp_path, run.id)

    final = run_full_pipeline_mock(
        run_id=run.id,
        store=store,
        config=config,
        trace=trace,
        fixtures_dir=FIXTURES_BSW,
        repo_dir=str(repo_path),
    )

    assert final.state == RunState.DONE, (
        f"expected DONE, got {final.state}"
    )

    assert store.get(run.id).state == RunState.DONE

    events = read_events(trace.path)
    phase_events = [e for e in events if e["ev"] == "phase"]
    phases_seen = [e["phase"] for e in phase_events]
    assert "BUILD_LOOP" in phases_seen, (
        f"phases seen: {phases_seen}"
    )
    assert "DONE" in phases_seen, (
        f"phases seen: {phases_seen}"
    )

    build_events = [e for e in events if e["ev"] == "build"]
    assert len(build_events) >= 1, "must have at least one build event"

    error_counts = [e.get("errors", 0) for e in build_events]
    assert any(c > 0 for c in error_counts), (
        "must have build events with errors > 0"
    )
    assert error_counts[-1] == 0 or error_counts[0] > error_counts[-1], (
        f"errors should be descending or reaching 0; got {error_counts}"
    )

    fix_events = [e for e in events if e["ev"] == "fix"]
    assert len(fix_events) >= 1, "must have at least one fix event"

    counters = final.counters
    assert counters.errors_initial > 0, (
        f"errors_initial must be > 0, got {counters.errors_initial}"
    )
    assert counters.iterations >= 1, (
        f"iterations must be >= 1, got {counters.iterations}"
    )

    done_events = [e for e in events if e["ev"] == "build_loop.done"]
    assert len(done_events) == 1, "must have one build_loop.done event"
    assert done_events[0].get("success") is True, (
        f"build_loop.done must report success=True, got {done_events[0]}"
    )
