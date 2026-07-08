"""tests/test_loop.py — L4 tests for ``core.phases.loop`` (build-fix control loop).

Covers §6.4 invariants:
  1. Camino verde: MockOracle (bsw 8→5→2→0) + success=True, counters poblados.
  2. MAX_ITERATIONS: cota dura de cfg.max_iterations respetada.
  3. Estancamiento: fuerza tier=remote a no_progress>=3, exit a no_progress>=5.
  4. Revert-si-empeora: delta>0 agota attempts -> needs_human.

Uses ``core.oracle.mock.MockOracle`` (hermético) + stubs de las funciones
inyectadas. Las funciones reales se cablean en T14b.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Config
from core.llm.router import decide_tier
from core.oracle.mock import MockOracle
from core.phases.loop import (
    ApplyFn,
    ClassifyFn,
    LoopResult,
    ProposeFixFn,
    run_build_loop,
)
from core.schemas import Counters, ErrorGroup
from core.trace import TraceWriter, read_events


FIXTURES_BSW = Path(__file__).resolve().parent.parent.parent / "fixtures" / "bsw"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> Config:
    """Construye un ``Config`` mínimo (no depende de env vars)."""
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
    )
    defaults.update(overrides)
    return Config(**defaults)


def _make_trace(tmp_path: Path, run_id: str = "run_test") -> TraceWriter:
    return TraceWriter(str(tmp_path / "trace.jsonl"), run_id)


# ---------------------------------------------------------------------------
# Stubs for injected functions
# ---------------------------------------------------------------------------

def _classify_e01(_group: ErrorGroup) -> str:
    """Stub: siempre clasifica como E01 (leftover_cuda_include)."""
    return "E01"


def _propose_dummy(_group: ErrorGroup, _tier: str, _attempts: int) -> str:
    """Stub: devuelve un patch no-vacío (simula fix exitoso)."""
    return "dummy patch content"


def _apply_good(_patch: str, _commit_msg: str) -> int:
    """Stub: simula fix que mejora (delta negativo)."""
    return -1


def _apply_bad(_patch: str, _commit_msg: str) -> int:
    """Stub: simula fix que empeora (delta positivo)."""
    return 1


# ---------------------------------------------------------------------------
# Test 1 — Camino verde: 8→5→2→0
# ---------------------------------------------------------------------------

def test_green_path_converges(tmp_path: Path) -> None:
    """MockOracle drena fixtures/bsw 8→5→2→0; el loop converge a success=True."""
    oracle = MockOracle(str(FIXTURES_BSW))
    cfg = _make_config()
    trace = _make_trace(tmp_path)

    result = run_build_loop(
        oracle=oracle,
        cfg=cfg,
        trace=trace,
        classify_fn=_classify_e01,
        decide_tier_fn=decide_tier,
        propose_fix_fn=_propose_dummy,
        apply_fn=_apply_good,
    )

    assert isinstance(result, LoopResult)
    assert result.success is True
    assert result.final_errors == 0
    assert result.iterations >= 1, "debe haber al menos una iteración de fix"
    assert result.iterations <= cfg.max_iterations, (
        f"iterations {result.iterations} must not exceed max {cfg.max_iterations}"
    )

    c: Counters = result.counters
    assert c.errors_initial == 8, f"expected 8 initial errors, got {c.errors_initial}"
    assert c.errors_current == 0
    # Al menos fixes_deterministic > 0 (E01 es deterministic)
    assert c.fixes_deterministic > 0, (
        f"expected deterministic fixes, got {c.fixes_deterministic}"
    )
    assert c.iterations == result.iterations

    # INV-4: los eventos deben estar en el trace
    events = read_events(trace.path)
    build_events = [e for e in events if e["ev"] == "build"]
    fix_events = [e for e in events if e["ev"] == "fix"]
    assert len(build_events) >= 1
    assert len(fix_events) >= 1


# ---------------------------------------------------------------------------
# Test 2 — MAX_ITERATIONS: cota dura
# ---------------------------------------------------------------------------

def test_max_iterations_hard_cap(tmp_path: Path) -> None:
    """Con max_iterations=2 y un mock que nunca llega a 0, el loop
    respeta la cota dura y devuelve success=False en exactamente 2
    iteraciones."""
    # Un solo fixture con errores => el mock nunca converge a 0.
    single = tmp_path / "single"
    single.mkdir()
    (single / "build_01.txt").write_text(
        "src/foo.cu:1:1: error: something\n"
    )

    oracle = MockOracle(str(single))
    cfg = _make_config(max_iterations=2)
    trace = _make_trace(tmp_path)

    result = run_build_loop(
        oracle=oracle,
        cfg=cfg,
        trace=trace,
        classify_fn=_classify_e01,
        decide_tier_fn=decide_tier,
        propose_fix_fn=_propose_dummy,
        apply_fn=_apply_good,
    )

    assert result.success is False
    assert result.iterations == cfg.max_iterations, (
        f"hard cap: expected {cfg.max_iterations}, got {result.iterations}"
    )
    assert result.final_errors > 0
    # Mock nunca emite 0 → el loop debió iterar exactamente max_iterations veces
    # y salir por agotamiento.
    assert result.iterations == 2


# ---------------------------------------------------------------------------
# Test 3 — Estancamiento: tier=remote a no_progress>=3, exit a >=5
# ---------------------------------------------------------------------------

def test_stagnation_forces_remote_then_exits(tmp_path: Path) -> None:
    """Un mock que siempre devuelve el mismo count>0.

    * Tras 3 iteraciones sin bajar → tier='remote' en la propuesta.
    * Tras 5 → success=False (DONE_PARTIAL implícito).
    """
    single = tmp_path / "stuck"
    single.mkdir()
    (single / "build_01.txt").write_text(
        "src/foo.cu:1:1: error: something\n"
        "src/bar.cu:2:2: error: something else\n"
    )

    oracle = MockOracle(str(single))
    cfg = _make_config(max_iterations=25)  # suficiente para llegar a 5
    trace = _make_trace(tmp_path)

    captured_tiers: list[str] = []

    def _propose_capture(g: ErrorGroup, tier: str, a: int) -> str:
        captured_tiers.append(tier)
        return "patch"

    result = run_build_loop(
        oracle=oracle,
        cfg=cfg,
        trace=trace,
        classify_fn=_classify_e01,
        decide_tier_fn=decide_tier,
        propose_fix_fn=_propose_capture,
        apply_fn=_apply_good,
    )

    assert result.success is False
    # Debió salir por no_progress >= 5 (no por max_iterations)
    assert result.iterations < cfg.max_iterations, (
        "debe salir por estancamiento, no por max_iterations"
    )
    assert result.final_errors > 0

    # Las primeras 3 iteraciones (0,1,2) con no_progress < 3:
    # decide_tier_fn para E01 = deterministic → tier="deterministic"
    # A partir de iter 3 (no_progress >= 3) → tier="remote" forzado
    tiers_after3 = captured_tiers[3:] if len(captured_tiers) > 3 else []
    if tiers_after3:
        assert all(t == "remote" for t in tiers_after3), (
            f"tiers after no_progress>=3 must all be 'remote', got {tiers_after3}"
        )


# ---------------------------------------------------------------------------
# Test 4 — Revert-si-empeora: delta>0 agota attempts
# ---------------------------------------------------------------------------

def test_revert_on_worsening_exhausts_group(tmp_path: Path) -> None:
    """apply_fn devuelve delta>0 (empeoró) en cada intento.

    Tras max_attempts_per_group intentos fallidos, el grupo deja de
    elegirse → success=False con needs_human poblado con esa signature.
    """
    single = tmp_path / "bad"
    single.mkdir()
    (single / "build_01.txt").write_text(
        "src/foo.cu:1:1: error: something\n"
    )

    oracle = MockOracle(str(single))
    cfg = _make_config(max_attempts_per_group=3)
    trace = _make_trace(tmp_path)

    result = run_build_loop(
        oracle=oracle,
        cfg=cfg,
        trace=trace,
        classify_fn=_classify_e01,
        decide_tier_fn=decide_tier,
        propose_fix_fn=_propose_dummy,
        apply_fn=_apply_bad,        # siempre empeora
    )

    assert result.success is False
    assert result.final_errors > 0
    # El grupo se agotó → debe aparecer en needs_human
    assert len(result.needs_human) >= 1, (
        f"unresolved group must be reported, got {result.needs_human}"
    )
    # Los fixes del tier 'deterministic' NO deben haberse contado porque
    # el delta siempre fue > 0 (empeoró).
    assert result.counters.fixes_deterministic == 0, (
        "no successful fix should be counted when delta > 0"
    )

    # La signature del grupo debe ser un sha1 de 40 caracteres.
    for sig in result.needs_human:
        assert len(sig) == 40, f"signature must be 40-char sha1, got {len(sig)}: {sig}"
        assert all(c in "0123456789abcdef" for c in sig)


# ---------------------------------------------------------------------------
# Regresión — hallazgos del re-audit codex de T14a
# ---------------------------------------------------------------------------

def test_detect_oscillating_ignores_initial_appearance():
    """Re-audit #3: la PRIMERA aparición de una signature no es una reaparición.
    history=[∅,{S},∅,{S}] tiene UNA sola reaparición real → NO oscila."""
    from core.phases.loop import _detect_oscillating
    hist = [set(), {"S"}, set(), {"S"}]
    assert _detect_oscillating(hist, {"S"}) == set()          # 1 reaparición, no alcanza
    # Con DOS reapariciones reales (T,F,T,F,T) sí oscila:
    hist2 = [{"S"}, set(), {"S"}, set(), {"S"}]
    assert "S" in _detect_oscillating(hist2, {"S"})


def test_stagnation_exit_threshold_from_config(tmp_path):
    """Re-audit #2: el umbral de salida por estancamiento sale de config (no hardcode 5)."""
    # Oracle que devuelve SIEMPRE los mismos 2 errores (nunca mejora).
    class _StuckOracle:
        def build(self):
            from core.schemas import BuildResult
            raw = ("a.cu:1:1: error: use of undeclared identifier 'cudaMalloc'\n"
                   "b.cu:2:1: error: use of undeclared identifier 'cudaFree'\n")
            return BuildResult(ok=False, count=2, raw_output=raw, returncode=1)
    cfg = _make_config(max_iterations=25, stagnation_exit=2, stagnation_force_remote=1)
    trace = _make_trace(tmp_path)
    res = run_build_loop(_StuckOracle(), cfg, trace,
                         _classify_e01, decide_tier,
                         lambda g, t, a: "FILE: a.cu\n<<<<<<< SEARCH\nx\n=======\ny\n>>>>>>> REPLACE",
                         lambda p, m: 0)   # apply nunca mejora (delta 0)
    # Con stagnation_exit=2 debe cortar MUCHO antes de max_iterations=25.
    assert res.success is False
    assert res.iterations < 25


def test_empty_patch_does_not_inflate_counters(tmp_path):
    """Re-audit #1 (INV-7/F-17): un patch vacío NO cuenta como fix; consume intento."""
    class _StuckOracle:
        def build(self):
            from core.schemas import BuildResult
            raw = "a.cu:1:1: error: use of undeclared identifier 'cudaMalloc'\n"
            return BuildResult(ok=False, count=1, raw_output=raw, returncode=1)
    cfg = _make_config(max_iterations=5, max_attempts_per_group=2)
    trace = _make_trace(tmp_path)
    res = run_build_loop(_StuckOracle(), cfg, trace,
                         _classify_e01, decide_tier,
                         lambda g, t, a: "",       # propose_fix no produce patch
                         lambda p, m: 0)
    # Ningún fix real → todos los counters de fixes en 0 (no inflados).
    assert res.counters.fixes_deterministic == 0
    assert res.counters.fixes_local == 0
    assert res.counters.fixes_remote == 0
