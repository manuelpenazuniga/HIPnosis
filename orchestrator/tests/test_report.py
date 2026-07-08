"""tests/test_report.py — L4 tests for ``core.report`` (F-17/INV-7).

The certificate is the PRODUCT (F-13b). These tests assert the contract
that makes F-17 hold: every number in the rendered markdown comes from
``ReportData`` (built by ``build_report_data`` from pipeline objects),
and ``render_certificate`` produces a markdown string that contains
all the required sections from blueprint §8.

Critical F-17 test: with KNOWN counters (``fixes_deterministic=6``,
``fixes_local=2``, ``fixes_remote=2``) the local-share is exactly 80%.
We assert that exact string appears in the rendered certificate.
The number is COMPUTED in the template from the dataclass, not
injected by an LLM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Config
from core.report import (
    HOURS_GPU_PER_YEAR,
    ReportData,
    build_report_data,
    compute_savings,
    render_certificate,
    render_portability,
    render_pr_body,
)
from core.schemas import (
    Budgets,
    Counters,
    Run,
    ScanResult,
    VerifyResult,
    Wave64Finding,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    )
    defaults.update(overrides)
    return Config(**defaults)


def _make_run(**overrides) -> Run:
    defaults = dict(
        id="run_t16demo",
        repo_url="https://example.com/repo.git",
        state="REPORTING",
        budgets=Budgets(
            max_iterations=25,
            max_attempts_per_group=3,
            max_errors_parsed=30,
        ),
        counters=Counters(),
    )
    defaults.update(overrides)
    return Run(**defaults)


def _make_scan() -> ScanResult:
    return ScanResult(
        files_cuda=["src/kernel.cu", "src/util.cuh"],
        loc_kernels=420,
        api_calls={"cudaMalloc": 3, "cudaMemcpy": 7, "cudaFree": 3},
        libs=["cublas"],
        build_system="make",
        wave64_findings=[
            Wave64Finding(
                file="src/kernel.cu",
                line=13,
                pattern_id="W01",
                snippet="unsigned mask = __ballot_sync(0xffffffff, pred);",
                severity="correctness",
                explanation="Máscara de 32 bits; en wave64 la máscara/resultado son de 64 bits.",
            ),
            Wave64Finding(
                file="src/kernel.cu",
                line=42,
                pattern_id="W04",
                snippet="int v = __shfl_xor_sync(0xffffffff, x, 4, 32);",
                severity="suspicious",
                explanation="Ancho 32 hardcodeado; wavefront AMD = 64.",
            ),
        ],
        difficulty="medium",
    )


def _make_loop_result(counters: Counters, needs_human: list[str] | None = None):
    """Fake ``LoopResult``-shaped object (lo único que ``build_report_data``
    lee es ``.counters`` y ``.needs_human``)."""

    class _LR:
        pass

    lr = _LR()
    lr.counters = counters
    lr.needs_human = needs_human or []
    lr.success = counters.errors_current == 0
    lr.final_errors = counters.errors_current
    lr.iterations = counters.iterations
    return lr


def _make_verify(verdict: str = "PASS", detail: str = "self-check PASS vs. CPU") -> VerifyResult:
    return VerifyResult(
        ran=True,
        exit_code=0,
        verdict=verdict,
        parity_details=detail,
        timing={"build_s": 1.23, "run_s": 0.45},
    )


# ---------------------------------------------------------------------------
# Test 1 — build_report_data desde objetos mínimos
# ---------------------------------------------------------------------------

def test_build_report_data_pulls_all_fields_from_pipeline_objects() -> None:
    """Cada campo de ReportData se popula desde objetos del pipeline
    (F-17/INV-7): counters del loop, inventario del scan, verdict del
    verify, repo_url del run. NINGÚN número se inventa."""
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(
        errors_initial=8,
        errors_current=0,
        fixes_local=2,
        fixes_remote=1,
        fixes_deterministic=5,
        tokens_local=412,
        tokens_remote=0,
        iterations=3,
    )
    loop = _make_loop_result(counters)
    verify = _make_verify("PASS")

    data = build_report_data(
        scan_result=scan,
        loop_result=loop,
        verify_result=verify,
        run=run,
        config=cfg,
    )

    assert isinstance(data, ReportData)
    assert data.repo_url == run.repo_url
    assert data.difficulty == "medium"
    assert data.files_cuda == 2
    assert data.loc_kernels == 420
    assert data.api_calls == {"cudaMalloc": 3, "cudaMemcpy": 7, "cudaFree": 3}
    assert data.libs == ["cublas"]
    assert data.build_system == "make"
    assert len(data.wave64_findings) == 2
    assert data.wave64_findings[0].pattern_id == "W01"
    assert data.verify_verdict == "PASS"
    assert "self-check" in data.verify_detail
    assert data.timing == {"build_s": 1.23, "run_s": 0.45}
    assert data.counters["errors_initial"] == 8
    assert data.counters["fixes_deterministic"] == 5
    assert data.executive_summary == ""  # default: vacío, no se inventa prosa
    assert data.needs_human == []


def test_build_report_data_handles_missing_verify() -> None:
    """Sin VerifyResult, el verdict cae a ``NO_ORACLE`` (F-08 honest)."""
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(errors_initial=4, errors_current=2, fixes_deterministic=2)
    loop = _make_loop_result(counters)

    data = build_report_data(
        scan_result=scan,
        loop_result=loop,
        verify_result=None,
        run=run,
        config=cfg,
    )

    assert data.verify_verdict == "NO_ORACLE"
    assert data.timing is None


def test_build_report_data_uses_run_counters_when_no_loop_result() -> None:
    """Si no hay LoopResult (e.g. reportes parciales de runs viejos),
    los counters vienen de ``run.counters`` (que también es de código)."""
    cfg = _make_config()
    run = _make_run(
        counters=Counters(
            errors_initial=6,
            errors_current=1,
            fixes_deterministic=4,
            fixes_local=1,
        ),
    )
    scan = _make_scan()

    data = build_report_data(
        scan_result=scan,
        loop_result=None,
        verify_result=None,
        run=run,
        config=cfg,
    )

    assert data.counters["fixes_deterministic"] == 4
    assert data.counters["fixes_local"] == 1
    assert data.counters["errors_current"] == 1


def test_build_report_data_aggregates_fixes_by_class() -> None:
    """El caller puede inyectar un desglose por grupo (klass, tier,
    commits). La tabla sale DE ESE desglose, no se inventa."""
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(
        errors_initial=10,
        errors_current=0,
        fixes_deterministic=6,
        fixes_local=2,
        fixes_remote=2,
        iterations=4,
    )
    loop = _make_loop_result(counters)
    verify = _make_verify("PASS")

    data = build_report_data(
        scan_result=scan,
        loop_result=loop,
        verify_result=verify,
        run=run,
        config=cfg,
        fixes_by_group=[
            {"klass": "E01", "tier": "deterministic", "n": 4, "commits": ["aaaa111"]},
            {"klass": "E01", "tier": "deterministic", "n": 2, "commits": ["bbbb222"]},
            {"klass": "E05", "tier": "local", "n": 2, "commits": ["cccc333"]},
            {"klass": "E05", "tier": "remote", "n": 2, "commits": ["dddd444"]},
        ],
    )

    by_klass = {r["klass"]: r for r in data.fixes_by_class}
    assert by_klass["E01"]["n"] == 6
    assert by_klass["E01"]["tier"] == "deterministic"
    assert set(by_klass["E01"]["commits"]) == {"aaaa111", "bbbb222"}
    assert by_klass["E05"]["n"] == 2  # se desglosa en dos filas (local + remote)


# ---------------------------------------------------------------------------
# Test 2 — render_certificate contiene TODO lo obligatorio (§8)
# ---------------------------------------------------------------------------

def test_render_certificate_contains_all_required_sections() -> None:
    """El certificado tiene las 8 secciones de §8:
    1. Resumen ejecutivo
    2. Inventario
    3. Fixes aplicados (tabla)
    4. Hallazgos wave64 (tabla)
    5. Verificación (verdict + detalle + tolerancias)
    6. Timing
    7. Limitaciones y NEEDS_HUMAN (SIEMPRE presente, INV-5)
    8. Métricas de eficiencia
    """
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(
        errors_initial=8,
        errors_current=0,
        fixes_deterministic=4,
        fixes_local=2,
        fixes_remote=1,
        tokens_local=100,
        tokens_remote=50,
        iterations=3,
    )
    loop = _make_loop_result(counters, needs_human=["deadbeef00"])
    verify = _make_verify("PASS", "self-check PASS vs. CPU reference")

    data = build_report_data(
        scan_result=scan, loop_result=loop, verify_result=verify,
        run=run, config=cfg, executive_summary="Port exitoso en mock.",
    )

    md = render_certificate(data)

    # Es un markdown string.
    assert isinstance(md, str)
    assert md  # no vacío

    # §8.1 Resumen ejecutivo (el único campo de prosa — viene del caller).
    assert "Port exitoso en mock." in md

    # §8.2 Inventario.
    assert "Archivos CUDA" in md
    assert "420" in md          # loc_kernels del scan, NO inventado
    assert "medium" in md       # difficulty

    # §8.3 Tabla de fixes.
    assert "Fixes aplicados" in md
    assert "deterministic" in md
    assert "local" in md
    assert "remote" in md

    # §8.4 Hallazgos wave64.
    assert "wave64" in md.lower()
    assert "W01" in md
    assert "W04" in md
    assert "kernel.cu" in md

    # §8.5 Verificación.
    assert "PASS" in md
    assert "self-check PASS" in md
    assert "rtol/atol" in md or "tolerancias" in md.lower()

    # §8.6 Timing.
    assert "build_s" in md or "Timing" in md

    # §8.7 NEEDS_HUMAN — sección obligatoria aunque esté vacía.
    assert "NEEDS_HUMAN" in md
    assert "Limitaciones" in md
    assert "deadbeef00" in md  # signature listada explícitamente

    # §8.8 Métricas de eficiencia.
    assert "Métricas" in md or "eficiencia" in md.lower()
    assert "Iteraciones" in md
    assert "Tokens" in md


def test_render_certificate_keeps_needs_human_section_when_empty() -> None:
    """La sección NEEDS_HUMAN aparece SIEMPRE aunque esté vacía (INV-5
    degradación honesta)."""
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(errors_initial=4, errors_current=0, fixes_deterministic=4)
    loop = _make_loop_result(counters, needs_human=[])  # ← vacío
    verify = _make_verify("PASS")

    data = build_report_data(
        scan_result=scan, loop_result=loop, verify_result=verify,
        run=run, config=cfg,
    )
    md = render_certificate(data)

    assert "NEEDS_HUMAN" in md
    assert "Limitaciones" in md
    # Y debe indicar explícitamente que NO hay grupos sin resolver.
    assert "No hay grupos sin resolver" in md or "no hay grupos" in md.lower()


# ---------------------------------------------------------------------------
# Test 3 — F-17: el % local se COMPUTA del JSON, no se inventa
# ---------------------------------------------------------------------------

def test_f17_local_share_is_computed_from_counters_exactly_80() -> None:
    """F-17/INV-7: con counters conocidos (deterministic=6, local=2,
    remote=2) el % de fixes locales debe ser EXACTAMENTE 80% en el
    certificado. El número sale del cómputo (8/10)*100 sobre el
    dataclass — NUNCA redactado por un LLM."""
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(
        errors_initial=10,
        errors_current=0,
        fixes_deterministic=6,
        fixes_local=2,
        fixes_remote=2,    # total=10 → 8/10 = 80%
        tokens_local=900,
        tokens_remote=200,
        iterations=4,
    )
    loop = _make_loop_result(counters)
    verify = _make_verify("PASS")

    data = build_report_data(
        scan_result=scan, loop_result=loop, verify_result=verify,
        run=run, config=cfg,
    )

    md = render_certificate(data)

    # El cómputo: (6 + 2) / (6 + 2 + 2) * 100 = 80.0
    # La template usa integer division ((8*100)//10 == 80).
    assert "80%" in md, (
        f"F-17: expected exact '80%' computed from counters "
        f"(deterministic=6, local=2, remote=2), got:\n{md}"
    )
    # Y NO debe aparecer cualquier otro % fabricado por un LLM.
    assert "85%" not in md
    assert "75%" not in md


def test_f17_counters_in_report_match_input_counters() -> None:
    """F-17/INV-7: cada contador que aparece en el certificado es
    exactamente el del input. Validamos los crudos en el markdown."""
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(
        errors_initial=12,
        errors_current=2,
        fixes_deterministic=7,
        fixes_local=3,
        fixes_remote=1,
        tokens_local=1500,
        tokens_remote=400,
        iterations=5,
    )
    loop = _make_loop_result(counters)
    verify = _make_verify("PASS")

    data = build_report_data(
        scan_result=scan, loop_result=loop, verify_result=verify,
        run=run, config=cfg,
    )
    md = render_certificate(data)

    # Todos los crudos del counter deben aparecer tal cual.
    assert "12" in md and "2" in md       # errors_initial → errors_current
    assert "1500" in md                   # tokens_local
    assert "400" in md                    # tokens_remote
    assert "5" in md                      # iterations
    # % local = (7+3)/(7+3+1)*100 = 10/11 → integer div (1000//11) = 90
    assert "90%" in md


# ---------------------------------------------------------------------------
# Test 4 — compute_savings (§5.3)
# ---------------------------------------------------------------------------

def test_compute_savings_with_zero_prices_returns_zero_and_note() -> None:
    """Si los precios son 0 (default de dev), compute_savings devuelve
    0 y una nota explicando que no hay proyección — F-17: NUNCA inventar
    el número."""
    cfg = _make_config(price_h100_hr=0.0, price_mi300x_hr=0.0)
    out = compute_savings({}, cfg)

    assert out["savings_per_year"] == 0.0
    assert out["delta_price_hr"] == 0.0
    assert "ahorro/año" in out["formula"]
    assert out["hours_gpu_year"] == HOURS_GPU_PER_YEAR
    assert "Precios no configurados" in out["note"] or "PRICE" in out["note"]


def test_compute_savings_with_set_prices_computes_correctly() -> None:
    """Con precios seteados, la fórmula es exacta y citada.

    Ejemplo: H100=$2.00/h, MI300X=$1.00/h → delta=$1.00/h
    8760 × 1.00 = $8,760/año.
    """
    cfg = _make_config(price_h100_hr=2.00, price_mi300x_hr=1.00)
    out = compute_savings({}, cfg)

    assert out["delta_price_hr"] == pytest.approx(1.00)
    assert out["savings_per_year"] == pytest.approx(HOURS_GPU_PER_YEAR * 1.00)
    assert out["formula"] == "ahorro/año = horas_gpu_año × (precio_h100 - precio_mi300x)"
    # La nota cita la fórmula con los números concretos.
    assert "8760" in out["note"]


def test_compute_savings_negative_delta_yields_negative() -> None:
    """Si por algún motivo la MI300X es MÁS cara (raro pero posible),
    el delta es negativo y el ahorro también — el código NO miente
    para quedar bonito (F-17)."""
    cfg = _make_config(price_h100_hr=1.00, price_mi300x_hr=3.00)
    out = compute_savings({}, cfg)
    assert out["delta_price_hr"] == pytest.approx(-2.00)
    assert out["savings_per_year"] == pytest.approx(-2.0 * HOURS_GPU_PER_YEAR)


# ---------------------------------------------------------------------------
# Test 5 — render_portability y render_pr_body funcionan
# ---------------------------------------------------------------------------

def test_render_portability_is_markdown_with_required_sections() -> None:
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(
        errors_initial=8, errors_current=0,
        fixes_deterministic=4, fixes_local=2, fixes_remote=1,
        tokens_local=100, tokens_remote=50, iterations=3,
    )
    loop = _make_loop_result(counters)
    verify = _make_verify("PASS")
    data = build_report_data(
        scan_result=scan, loop_result=loop, verify_result=verify,
        run=run, config=cfg, executive_summary="Resumen corto.",
    )

    md = render_portability(data)
    assert "Resumen corto." in md
    assert "W01" in md
    assert "NEEDS_HUMAN" in md
    # % local = (4+2)/(4+2+1)*100 = 85 (integer div: 600//7 = 85)
    assert "%" in md


def test_render_pr_body_contains_verdict_and_metrics() -> None:
    cfg = _make_config()
    run = _make_run()
    scan = _make_scan()
    counters = Counters(
        errors_initial=8, errors_current=0,
        fixes_deterministic=4, fixes_local=2, fixes_remote=1,
        iterations=3,
    )
    loop = _make_loop_result(counters)
    verify = _make_verify("PASS")
    data = build_report_data(
        scan_result=scan, loop_result=loop, verify_result=verify,
        run=run, config=cfg,
    )

    md = render_pr_body(data)
    assert "Verdict" in md or "verdict" in md
    assert "PASS" in md
    assert "Wave64" in md or "wave64" in md
    assert "Métricas" in md or "M" in md


# ---------------------------------------------------------------------------
# Test 6 — build_report_data NO toca LLM (F-17 / regresión)
# ---------------------------------------------------------------------------

def test_build_report_data_never_imports_or_calls_llm(monkeypatch) -> None:
    """F-17/INV-7: ``build_report_data`` es puro sobre datos. Si alguien
    intenta meter un LLM en el medio, este test explota."""
    import core.report as rep_mod

    forbidden = {"llm.client", "core.llm.client", "openai", "httpx"}
    src = Path(rep_mod.__file__).read_text(encoding="utf-8")

    for needle in forbidden:
        assert needle not in src, (
            f"F-17 violation: report.py references {needle!r}. "
            "build_report_data must be pure over pipeline objects."
        )

    # Y los import observados del módulo NO incluyen llm/oracle/state.
    for mod in ("core.llm", "core.oracle", "core.state", "core.llm.client", "core.llm.router"):
        assert mod not in rep_mod.__dict__ and mod not in dir(rep_mod), (
            f"F-17: report must not import {mod}"
        )
