"""tests/test_oracle_gates.py — Gate B del audit codex: los oráculos no se negocian.

Regresiones de los hallazgos P0.3 / P0.4 / P0.7 / P0.8 / P0.9:
  1. Un build con returncode != 0 pero sin líneas ': error:' JAMÁS es green.
  2. Un patch aplicado que no mejora el build real se REVIERTE y no cuenta como fix.
  3. verify: un binario que imprime PASS pero muere con exit != 0 es FAIL.
  4. Loop sin éxito → la FSM salta a REPORTING y termina DONE_PARTIAL (no DONE).
  5. Certificado == evento report == counters del store (un solo snapshot).
"""
from __future__ import annotations

from pathlib import Path

from core.config import Config
from core.llm.router import decide_tier
from core.manifest import BuildSpec, Manifest, RunSpec, VerifySpec
from core.oracle.mock import MockOracle
from core.phases.loop import ApplyOutcome, run_build_loop
from core.phases.pipeline import run_full_pipeline
from core.phases.verify import verify
from core.schemas import BuildResult, ErrorGroup, RunResult, RunState
from core.state import SqliteRunStore
from core.trace import TraceWriter, read_events


def _cfg(**overrides) -> Config:
    defaults = dict(oracle_mode="mock", local_llm_base_url="", local_llm_model="",
                    remote_llm_base_url="", remote_llm_model="", fireworks_api_key="",
                    hf_token="", github_token="", gpu_arch="gfx942", max_iterations=25,
                    max_attempts_per_group=3, max_errors_parsed=30, confidence_threshold=0.6,
                    price_h100_hr=0.0, price_mi300x_hr=0.0)
    defaults.update(overrides)
    return Config(**defaults)


def _trace(tmp_path: Path) -> TraceWriter:
    return TraceWriter(str(tmp_path / "trace.jsonl"), "run_gates")


# --------------------------------------------------------------------------
# P0.3 — returncode != 0 sin ': error:' jamás es green
# --------------------------------------------------------------------------

def test_nonzero_exit_without_error_lines_is_never_green(tmp_path):
    """Un `make` que hace exit 2 sin imprimir ': error:' (No rule to make
    target, crash del linker) debe terminar success=False con el grupo
    sintético E13 en needs_human — nunca DONE/PASS."""
    class _BrokenMake:
        def build(self):
            return BuildResult(
                ok=False, count=0, returncode=2,
                raw_output="make: *** No rule to make target 'main'. Stop.\n",
            )

    res = run_build_loop(
        _BrokenMake(), _cfg(max_attempts_per_group=2), _trace(tmp_path),
        classify_fn=lambda g: "E99",
        decide_tier_fn=decide_tier,
        propose_fix_fn=lambda g, t, a: "",     # nadie puede proponer nada
        apply_fn=lambda p, m: ApplyOutcome(applied_ws=False),
    )
    assert res.success is False
    assert res.final_errors >= 1
    assert any("buildsys" in sig for sig in res.needs_human), res.needs_human


def test_green_requires_ok_not_just_zero_error_count(tmp_path):
    """count==0 con ok=False NO es green (returncode manda)."""
    class _LyingBuild:
        def build(self):
            return BuildResult(ok=False, count=0, returncode=1, raw_output="boom\n")

    res = run_build_loop(
        _LyingBuild(), _cfg(max_iterations=3), _trace(tmp_path),
        classify_fn=lambda g: "E99", decide_tier_fn=decide_tier,
        propose_fix_fn=lambda g, t, a: "", apply_fn=lambda p, m: ApplyOutcome(applied_ws=False),
    )
    assert res.success is False


# --------------------------------------------------------------------------
# P0.4 — patch que no mejora se revierte; el delta es del compilador
# --------------------------------------------------------------------------

def test_non_improving_patch_is_reverted_and_not_counted(tmp_path):
    """apply toca el workspace pero el build siguiente NO mejora → el loop
    invoca revert(), el fix no se cuenta y el intento se consume."""
    class _Stuck:
        def build(self):
            return BuildResult(
                ok=False, count=1, returncode=1,
                raw_output="a.cu:1:1: error: use of undeclared identifier 'cudaMalloc'\n",
            )

    reverts: list[int] = []

    def _apply(p, m):
        return ApplyOutcome(applied_ws=True, commit="feedface",
                            revert=lambda: reverts.append(1))

    res = run_build_loop(
        _Stuck(), _cfg(max_attempts_per_group=2), _trace(tmp_path),
        classify_fn=lambda g: "E02", decide_tier_fn=decide_tier,
        propose_fix_fn=lambda g, t, a: "patch", apply_fn=_apply,
    )
    assert res.success is False
    assert len(reverts) >= 1, "el parche no-mejorante debe revertirse"
    assert res.counters.fixes_deterministic == 0
    assert res.counters.fixes_local == 0
    assert res.counters.fixes_remote == 0
    # y todos los eventos fix del trace deben decir applied=false
    evs = read_events(str(tmp_path / "trace.jsonl"))
    fixes = [e for e in evs if e["ev"] == "fix"]
    assert fixes and all(e["applied"] is False for e in fixes)


def test_improving_patch_carries_measured_delta(tmp_path):
    """El delta del evento fix sale del compilador (after - before)."""
    class _Improves:
        def __init__(self):
            self.calls = 0
        def build(self):
            self.calls += 1
            if self.calls == 1:
                return BuildResult(ok=False, count=3, returncode=1,
                                   raw_output="a.cu:1:1: error: use of undeclared identifier 'cudaMalloc'\n" * 3)
            return BuildResult(ok=True, count=0, returncode=0, raw_output="ok\n")

    res = run_build_loop(
        _Improves(), _cfg(), _trace(tmp_path),
        classify_fn=lambda g: "E02", decide_tier_fn=decide_tier,
        propose_fix_fn=lambda g, t, a: "patch",
        apply_fn=lambda p, m: ApplyOutcome(applied_ws=True, commit="cafe1234"),
    )
    assert res.success is True
    evs = read_events(str(tmp_path / "trace.jsonl"))
    fix = next(e for e in evs if e["ev"] == "fix")
    assert fix["applied"] is True
    assert fix["delta"] == -3, f"delta medido por el compilador, got {fix['delta']}"
    assert fix["commit"] == "cafe1234"


# --------------------------------------------------------------------------
# P0.7 — verify exige proceso limpio antes de mirar el texto
# --------------------------------------------------------------------------

class _OracleRun:
    def __init__(self, ran=True, exit_code=0, stdout="PASS\n"):
        self._r = RunResult(ran=ran, exit_code=exit_code, stdout=stdout, timing=None)
    def build(self):
        raise AssertionError("verify no debe compilar")
    def run(self, run_cmd=None, timeout_s=120):
        return self._r


def _manifest_selfcheck() -> Manifest:
    return Manifest(build=BuildSpec(cmd="make"), run=RunSpec(cmd="./main"),
                    verify=VerifySpec(mode="self_check", pass_regex="PASS"))


def test_verify_fails_when_process_prints_pass_but_exits_nonzero(tmp_path):
    out = verify(_manifest_selfcheck(), _OracleRun(exit_code=1, stdout="PASS\n"),
                 str(tmp_path), _cfg(), trace=None)
    assert out.verify_result.verdict == "FAIL"
    assert "exit_code=1" in out.verify_result.parity_details


def test_verify_passes_when_process_clean_and_text_pass(tmp_path):
    out = verify(_manifest_selfcheck(), _OracleRun(exit_code=0, stdout="PASS\n"),
                 str(tmp_path), _cfg(), trace=None)
    assert out.verify_result.verdict == "PASS"


# --------------------------------------------------------------------------
# P0.8 + P0.9 — DONE_PARTIAL cableado y consistencia cert==report==store
# --------------------------------------------------------------------------

def _stage(tmp_path: Path, key: str) -> str:
    from core.runner import _stage_mock_workspace
    repo = tmp_path / "repo"
    _stage_mock_workspace(str(repo), key=key)
    return str(repo)


def test_failed_loop_routes_to_done_partial_and_skips_verify(tmp_path):
    """Fixture con un error E05 (llm) y workspace SIN demo-patch → nadie
    propone fix → loop success=False → REPORTING → DONE_PARTIAL. RUNNING y
    PARITY no deben ejecutarse (verificar un build roto no tiene sentido)."""
    fixdir = tmp_path / "fix"
    fixdir.mkdir()
    (fixdir / "build_01.txt").write_text(
        "kernel.cu:13:20: error: use of undeclared identifier '__ballot_sync'\n"
    )
    repo = _stage(tmp_path, "softmax")   # softmax NO trae demo-patch E05

    store = SqliteRunStore(str(tmp_path / "r.db"))
    run = store.create("https://ex/stuck.git")
    trace = TraceWriter(str(tmp_path / "trace.jsonl"), run.id)

    final = run_full_pipeline(run.id, store, _cfg(), trace,
                              MockOracle(str(fixdir)), _manifest_selfcheck(), repo)

    assert final.state == RunState.DONE_PARTIAL
    evs = read_events(str(tmp_path / "trace.jsonl"))
    phases = [e["phase"] for e in evs if e["ev"] == "phase"]
    assert phases[-1] == RunState.DONE_PARTIAL
    assert RunState.RUNNING not in phases, "no se verifica un build fallido"
    assert RunState.PARITY not in phases
    assert RunState.REPORTING in phases, "el reporte honesto es parte del contrato"
    # el certificado existe y declara el trabajo pendiente
    cert = Path(repo) / "HIPNOSIS_CERTIFICATE.md"
    assert cert.exists()


def test_certificate_report_event_and_store_agree(tmp_path):
    """P0.8: counters del store == evento report == números del certificado."""
    from pathlib import Path as _P
    repo = _stage(tmp_path, "bsw")
    fixtures_bsw = _P(__file__).resolve().parent.parent.parent / "fixtures" / "bsw"

    store = SqliteRunStore(str(tmp_path / "r.db"))
    run = store.create("https://ex/bsw.git")
    trace = TraceWriter(str(tmp_path / "trace.jsonl"), run.id)

    final = run_full_pipeline(run.id, store, _cfg(), trace,
                              MockOracle(str(fixtures_bsw)), _manifest_selfcheck(), repo)

    assert final.state == RunState.DONE
    c = store.get(run.id).counters
    assert c.errors_initial == 8 and c.errors_current == 0
    assert c.fixes_deterministic + c.fixes_local + c.fixes_remote >= 1

    evs = read_events(str(tmp_path / "trace.jsonl"))
    report_ev = next(e for e in evs if e["ev"] == "report")
    for field in ("errors_initial", "errors_current", "fixes_deterministic",
                  "fixes_local", "fixes_remote", "iterations"):
        assert report_ev[field] == getattr(c, field), (
            f"report.{field}={report_ev[field]} != store {getattr(c, field)}"
        )

    cert_text = (Path(repo) / "HIPNOSIS_CERTIFICATE.md").read_text()
    assert f"{c.errors_initial} → {c.errors_current}" in cert_text, (
        "el certificado debe mostrar los MISMOS números que el store/trace"
    )
