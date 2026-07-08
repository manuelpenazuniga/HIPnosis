"""tests/test_verify.py — FASE 4 VERIFY (run + paridad + timing, §7).

Capa L4 (phase). Estos tests pinnean el contrato público de
``core.phases.verify`` (T15c):

  * ``self_check`` con stdout 'PASS' + ``pass_regex='PASS'`` → ``PASS``.
  * ``self_check`` con stdout 'FAIL' → ``FAIL``.
  * ``mode='none'`` → ``NO_ORACLE`` (F-08 — final legítimo, no error).
  * ``golden_output``: stdout/golden con mismos floats → ``PASS``; distintos
    → ``FAIL``.
  * ``timing_regex`` extrae el número correcto del stdout.

El módulo es L4 puro: importa solo ``core.{config,manifest,parity,
oracle.base,schemas,trace}`` y stdlib — NUNCA ``core.{llm,patcher,state}``.

Las pruebas usan un ``MockOracle`` ad-hoc (subclase de ``Oracle``) que
devuelve el stdout que el test quiere — el ``MockOracle`` real de
``core.oracle.mock`` lee un fixture de disco y no permite override por
test, lo cual está bien para el loop pero no para esta fase que tiene
3 ramas (self_check / golden_output / none) y cada una con su propio
shape de stdout.

No testeamos el handler end-to-end contra el driver FSM — eso depende
de T14b/T15a y de la inyección de ``ctx.manifest`` y ``ctx.oracle``;
los tests unitarios de ``verify()`` son lo que el contrato pide.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

from core.config import Config
from core.manifest import (
    BuildSpec,
    Manifest,
    RunSpec,
    VerifySpec,
)
from core.oracle.base import Oracle
from core.phases import verify as verify_mod
from core.phases.verify import (
    VERDICT_FAIL,
    VERDICT_NO_ORACLE,
    VERDICT_PASS,
    VerifyOutcome,
    verify,
)
from core.schemas import BuildResult, RunResult, VerifyResult
from core.trace import TraceWriter


# ---------------------------------------------------------------------------
# MockOracle ad-hoc — override de stdout por test
# ---------------------------------------------------------------------------

@dataclass
class _FakeRunResult:
    """Lo que devuelve ``MockOracle.run`` en estos tests."""

    stdout: str
    ran: bool = True
    exit_code: int = 0
    timing: Optional[dict] = None


class _MockOracle(Oracle):
    """Oracle mínimo para los tests de verify: build() no se usa nunca
    (el loop de compilación vive en otra fase), y ``run()`` devuelve
    un stdout configurable.

    El ``MockOracle`` real (``core.oracle.mock``) lee un fixture de
    disco; eso es perfecto para el build loop, pero acá necesitamos
    un stdout distinto por test (PASS / FAIL / floats / no-floats) y
    crearlos en tmp_path es ruido. Esta subclase es la simplificación
    honesta: el contrato de ``Oracle`` (subclaseable, ``build`` y
    ``run``) es lo único que la fase verifica.
    """

    def __init__(self, stdout: str, exit_code: int = 0, ran: bool = True) -> None:
        self._stdout = stdout
        self._exit_code = exit_code
        self._ran = ran

    def build(self) -> BuildResult:
        raise NotImplementedError("verify() tests no ejercitan build()")

    def run(self, run_cmd=None, timeout_s: int = 120) -> RunResult:  # noqa: D401, ARG002
        return RunResult(
            ran=self._ran,
            exit_code=self._exit_code,
            stdout=self._stdout,
            timing=None,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> Config:
    """Config mínimo a mano — sin ``get_config()`` para no leer el env."""
    return Config(
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


def _make_manifest(
    *,
    mode: str = "self_check",
    pass_regex: str | None = "PASS",
    golden_file: str | None = None,
    rtol: float = 1e-5,
    atol: float = 1e-8,
    timing_regex: str | None = None,
) -> Manifest:
    """Manifiesto mínimo para cada test. ``output_file`` se ignora
    intencionalmente — el spec canónico todavía no lo tiene; el código
    lo lee defensivamente con ``getattr``."""
    return Manifest(
        build=BuildSpec(cmd="make -f Makefile", dir="."),
        run=RunSpec(cmd="./main", timeout_s=60),
        verify=VerifySpec(
            mode=mode,
            pass_regex=pass_regex,
            golden_file=golden_file,
            numeric_rtol=rtol,
            numeric_atol=atol,
        ),
        timing_regex=timing_regex,
        source=None,
    )


# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

def test_verdict_constants_match_blueprint() -> None:
    """Los tres verdicts son contrato público. Snapshot para que un
    rename accidental rompa el test en vez del dashboard silenciosamente."""
    assert VERDICT_PASS == "PASS"
    assert VERDICT_FAIL == "FAIL"
    assert VERDICT_NO_ORACLE == "NO_ORACLE"


# ---------------------------------------------------------------------------
# self_check
# ---------------------------------------------------------------------------

def test_self_check_pass_regex_finds_pass_returns_pass() -> None:
    """Casos del blueprint §7.1: ``self_check`` con ``pass_regex='PASS'``
    y stdout que contiene 'PASS' en una línea → verdict=PASS."""
    stdout = "Running self-check...\n[ok] result verification\nPASS\n"
    manifest = _make_manifest(mode="self_check", pass_regex="PASS")
    oracle = _MockOracle(stdout)

    outcome = verify(manifest, oracle, repo_dir=".", config=_make_config())

    assert isinstance(outcome, VerifyOutcome)
    assert outcome.verify_result.verdict == VERDICT_PASS
    assert outcome.verify_result.ran is True
    assert outcome.verify_result.exit_code == 0
    assert "encontrado" in outcome.verify_result.parity_details
    assert outcome.parity.ok is True
    assert outcome.mode == "self_check"


def test_self_check_stdout_fail_returns_fail() -> None:
    """``self_check`` con stdout 'FAIL' y regex 'PASS' → verdict=FAIL.
    Esto es la otra cara de la moneda del test anterior — el
    comparador de ``core.parity`` no debe aceptar FAIL como PASS."""
    stdout = "running...\nFAIL\n"
    manifest = _make_manifest(mode="self_check", pass_regex="PASS")
    oracle = _MockOracle(stdout)

    outcome = verify(manifest, oracle, repo_dir=".", config=_make_config())

    assert outcome.verify_result.verdict == VERDICT_FAIL
    assert outcome.verify_result.ran is True
    assert "no encontrado" in outcome.verify_result.parity_details
    assert outcome.parity.ok is False


# ---------------------------------------------------------------------------
# mode='none' — F-08, NO_ORACLE es final legítimo
# ---------------------------------------------------------------------------

def test_mode_none_returns_no_oracle_final_legitimate() -> None:
    """F-08: un repo sin oráculo declarado (mode=none) produce
    ``verdict=NO_ORACLE`` — es FINAL LEGÍTIMO, no un error. El handler
    NO debe fallar el run, y el reporte lo dice honestamente en grande."""
    manifest = _make_manifest(mode="none", pass_regex=None)
    oracle = _MockOracle("irrelevant stdout\n")  # oracle no se usa para mode=none

    outcome = verify(manifest, oracle, repo_dir=".", config=_make_config())

    assert outcome.verify_result.verdict == VERDICT_NO_ORACLE
    assert outcome.verify_result.ran is True  # el run SÍ se ejecutó
    assert outcome.verify_result.exit_code == 0
    assert outcome.mode == "none"
    # El detail explica por qué (audit-friendly)
    assert "none" in outcome.verify_result.parity_details.lower()


# ---------------------------------------------------------------------------
# golden_output
# ---------------------------------------------------------------------------

def test_golden_output_matching_floats_returns_pass(tmp_path: Path) -> None:
    """``golden_output`` con stdout y golden que extraen los MISMOS
    floats (mismos valores) → verdict=PASS. Verifica que la fase
    delega en ``parity.check_golden`` (F-09: rtol/atol, NO
    comparación exacta de texto)."""
    golden_text = "result: 12.5\n"
    stdout = "result: 12.5\n"
    golden_path = tmp_path / "expected.txt"
    golden_path.write_text(golden_text)

    manifest = _make_manifest(
        mode="golden_output",
        golden_file="expected.txt",
        pass_regex=None,
    )
    oracle = _MockOracle(stdout)

    outcome = verify(manifest, oracle, repo_dir=str(tmp_path), config=_make_config())

    assert outcome.verify_result.verdict == VERDICT_PASS
    assert outcome.parity.ok is True
    assert outcome.parity.n_compared == 1
    assert "1 valores" in outcome.verify_result.parity_details
    assert outcome.mode == "golden_output"


def test_golden_output_different_floats_returns_fail(tmp_path: Path) -> None:
    """``golden_output`` con floats distintos → verdict=FAIL. El
    detail cita el índice de la divergencia y los valores (útil para
    el dashboard y para el humano que diagnostica)."""
    golden_text = "result: 5.0\n"
    stdout = "result: 99.0\n"
    golden_path = tmp_path / "expected.txt"
    golden_path.write_text(golden_text)

    manifest = _make_manifest(
        mode="golden_output",
        golden_file="expected.txt",
        pass_regex=None,
    )
    oracle = _MockOracle(stdout)

    outcome = verify(manifest, oracle, repo_dir=str(tmp_path), config=_make_config())

    assert outcome.verify_result.verdict == VERDICT_FAIL
    assert outcome.parity.ok is False
    assert outcome.parity.n_compared == 1
    # El detail tiene que ser útil para diagnosis
    assert "indice 0" in outcome.verify_result.parity_details
    assert "99" in outcome.verify_result.parity_details
    assert "5" in outcome.verify_result.parity_details


# ---------------------------------------------------------------------------
# timing_regex
# ---------------------------------------------------------------------------

def test_timing_regex_extracts_number_from_stdout() -> None:
    """``timing_regex`` con grupo de captura → extrae el float del
    stdout y lo guarda en ``VerifyResult.timing``. Verifica el shape
    exacto del dict (lo que el certificado espera)."""
    stdout = (
        "Running self-check...\n"
        "Average kernel execution time 12.500 ms\n"
        "PASS\n"
    )
    manifest = _make_manifest(
        mode="self_check",
        pass_regex="PASS",
        timing_regex=r"Average kernel execution time.*?([\d.]+)",
    )
    oracle = _MockOracle(stdout)

    outcome = verify(manifest, oracle, repo_dir=".", config=_make_config())

    assert outcome.verify_result.verdict == VERDICT_PASS
    assert outcome.verify_result.timing is not None
    timing = outcome.verify_result.timing
    assert timing["value"] == pytest.approx(12.5)
    assert timing["raw"] == "12.500"
    assert timing["unit"] == "s"
    # wall_clock siempre presente (fallback / complemento)
    assert "wall_clock_s" in timing
    assert timing["wall_clock_s"] >= 0.0


def test_no_timing_regex_yields_wall_clock_only() -> None:
    """Sin ``timing_regex``, el VerifyResult.timing sigue presente pero
    poblado con el wall_clock (es la red de seguridad — el certificado
    siempre tiene algo que mostrar)."""
    stdout = "running...\nPASS\n"
    manifest = _make_manifest(mode="self_check", pass_regex="PASS", timing_regex=None)
    oracle = _MockOracle(stdout)

    outcome = verify(manifest, oracle, repo_dir=".", config=_make_config())

    assert outcome.verify_result.verdict == VERDICT_PASS
    assert outcome.verify_result.timing is not None
    timing = outcome.verify_result.timing
    assert timing["value"] >= 0.0
    assert timing["source"] == "wall_clock"


# ---------------------------------------------------------------------------
# Trace emission (INV-4)
# ---------------------------------------------------------------------------

def test_verify_emits_trace_event(tmp_path: Path) -> None:
    """INV-4: el evento ``verify`` se emite al trace con verdict /
    detail / mode / wall_clock. El dashboard live-polling lo lee
    directamente."""
    stdout = "running...\nPASS\n"
    manifest = _make_manifest(mode="self_check", pass_regex="PASS")
    oracle = _MockOracle(stdout)

    trace_path = tmp_path / "trace.jsonl"
    tw = TraceWriter(str(trace_path), run_id="run_t15c_test")

    outcome = verify(manifest, oracle, repo_dir=str(tmp_path), config=_make_config(), trace=tw)

    raw = trace_path.read_text().strip().splitlines()
    assert len(raw) == 1
    import json
    event = json.loads(raw[0])
    assert event["ev"] == "verify"
    assert event["run"] == "run_t15c_test"
    assert event["verdict"] == VERDICT_PASS
    assert event["mode"] == "self_check"
    assert event["ran"] is True
    assert event["exit_code"] == 0
    assert "wall_clock_s" in event
    assert event["wall_clock_s"] >= 0.0
    # Sanity: el detail no está vacío
    assert event["detail"]
    # Y coincide con el del VerifyResult
    assert event["detail"] == outcome.verify_result.parity_details


def test_verify_works_without_trace(tmp_path: Path) -> None:
    """``trace=None`` es la firma usada por replay / dry-run. El flujo
    no debe depender de tener un trace vivo."""
    stdout = "running...\nPASS\n"
    manifest = _make_manifest(mode="self_check", pass_regex="PASS")
    oracle = _MockOracle(stdout)

    outcome = verify(manifest, oracle, repo_dir=str(tmp_path), config=_make_config(), trace=None)

    assert outcome.verify_result.verdict == VERDICT_PASS
    # El trace no se creó
    assert not (tmp_path / "trace.jsonl").exists()


# ---------------------------------------------------------------------------
# L4 purity: verify.py no importa llm / state / patcher
# ---------------------------------------------------------------------------

def test_verify_module_l4_purity_imports() -> None:
    """``verify`` es L4 (phase): importa L2 (manifest, parity,
    oracle.base) y L1 (schemas, config, trace). NUNCA state / llm /
    patcher — la dirección de la dependencia va solo para abajo."""
    source = inspect.getsource(verify_mod)
    tree = ast.parse(source)

    allowed_core = {
        "core.config", "core.manifest", "core.parity",
        "core.oracle.base", "core.schemas", "core.trace",
    }
    allowed_core_names = {
        "Config", "Manifest", "Oracle", "ParityResult",
        "RunResult", "TraceWriter", "VerifyResult",
        "check_golden", "check_self_check",
    }
    forbidden_roots = {
        "core.state", "core.api", "core.llm",
        "core.llm.client", "core.llm.router", "core.patcher",
    }
    stdlib_roots = {
        "annotations", "ast", "collections", "contextlib", "copy",
        "dataclasses", "datetime", "enum", "functools", "io",
        "itertools", "json", "os", "pathlib", "re", "subprocess",
        "sys", "time", "typing", "__future__",
    }

    forbidden_hits: list[str] = []
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in forbidden_roots:
                    forbidden_hits.append(f"import {alias.name}")
                elif root not in stdlib_roots and alias.name not in allowed_core:
                    bad.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "__future__":
                continue
            if any(module == f or module.startswith(f + ".")
                   for f in forbidden_roots):
                forbidden_hits.append(f"from {module} import ...")
                continue
            if module in allowed_core or module.startswith("core."):
                for alias in node.names:
                    if (alias.name not in allowed_core_names
                            and not alias.name.startswith("_")):
                        bad.append(f"from {module} import {alias.name}")
            elif module.split(".")[0] not in stdlib_roots:
                bad.append(f"from {module} import ...")

    assert forbidden_hits == [], (
        "verify.py es L4: NO puede importar state/api/llm/patcher, "
        f"encontrado: {forbidden_hits}"
    )
    assert bad == [], (
        "verify.py solo puede importar core.{config,manifest,parity,"
        "oracle.base,schemas,trace} y stdlib; encontrado: " + str(bad)
    )
