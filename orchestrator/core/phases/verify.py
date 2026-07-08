"""core/phases/verify.py — FASE 4 VERIFY (run + paridad + timing, §7).

Capa L4 (phase). Es el producto: corre el binario, evalúa la paridad
numérica contra el oráculo declarado en ``hipnosis.yaml`` y emite el
``verdict`` que el certificado reporta (PASS / FAIL / NO_ORACLE).

Tres modos de verificación (blueprint §7.1):

  * ``self_check``     — el benchmark se auto-verifica y el manifiesto dice
                        qué regex buscar en stdout (``pass_regex``). El
                        comparador (F-09) filtra falsos positivos con
                        ``\\bFAIL\\b``.
  * ``golden_output``  — extraer floats posicionalmente del stdout (o de
                        un archivo de output si el manifiesto lo declara
                        con ``output_file``) y compararlos con
                        ``rtol/atol`` contra el golden.
  * ``none``           — ``verdict=NO_ORACLE`` final legítimo (F-08); el
                        reporte lo dice honestamente en grande.

El timing se extrae del stdout vía ``timing_regex`` (con grupo de
captura) cuando el manifiesto lo provee. La wall clock SIEMPRE se mide
(``time.monotonic()``) — es el dato más barato y siempre presente.

Layering: L4 (phase). Importa ``core.manifest`` (L2), ``core.parity``
(L2), ``core.oracle.base`` (L3), ``core.schemas`` (L1), ``core.config``
(L1), ``core.trace`` (L1) y stdlib. NUNCA importa ``core.llm``,
``core.patcher`` ni ``core.state`` — el control lo decide la FSM, el
contenido lo decide el manifest y la paridad la decide ``core.parity``.

F-09: NUNCA comparación exacta de floats — eso vive en ``core.parity``
(F-17: los números del certificado SOLO salen de ese módulo, no de un
LLM). Aquí no se hace ninguna comparación numérica: se delega a
``parity.check_self_check`` / ``parity.check_golden`` y se copia el
``detail`` al ``VerifyResult``.

INV-5: ``NO_ORACLE`` es final legítimo; no es un error. El handler NO
debe fallar el run por tener un manifiesto sin oráculo.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Optional

from core.config import Config
from core.manifest import Manifest
from core.oracle.base import Oracle
from core.parity import (
    ParityResult,
    check_golden,
    check_self_check,
)
from core.schemas import VerifyResult
from core.trace import TraceWriter


# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: Veredictos que ``verify()`` puede emitir. Los tres son FINALES — el
#: orquestador no los reinterpreta. ``NO_ORACLE`` no es un error (F-08).
VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_NO_ORACLE = "NO_ORACLE"


# ---------------------------------------------------------------------------
# Resultado extendido (con campos derivados que el reporte consume)
# ---------------------------------------------------------------------------

@dataclass
class VerifyOutcome:
    """Lo que ``verify()`` devuelve al orquestador.

    Es un SOBRE alrededor de :class:`VerifyResult` que además expone el
    :class:`ParityResult` completo (no solo su ``detail``), el
    ``wall_clock_s`` medido acá, y el ``verdict`` ya computado. La
    :class:`VerifyResult` se construye al final y se devuelve en
    ``verify_result`` para alimentar el contrato del reporte.

    Atributos:
        verify_result: la ``VerifyResult`` (schema L1) que REPORTING consume.
        parity:        el ``ParityResult`` crudo — el detail ya está copiado
                      adentro, pero conservarlo permite que tests/diagnóstico
                      inspeccionen ``n_compared`` y ``ok`` sin re-parsear.
        wall_clock_s:  tiempo total medido en este proceso, en segundos
                      (siempre presente, complemento del ``timing_regex``).
        mode:          modo efectivo del manifiesto (``self_check`` /
                      ``golden_output`` / ``none``) — útil para el trace.
    """

    verify_result: VerifyResult
    parity: ParityResult
    wall_clock_s: float
    mode: str


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _read_text_file(path: str) -> str:
    """Lee un archivo de texto en UTF-8 (best-effort). Lanza si no existe.

    El benchmark puede o no haber producido el archivo de output —
    ``verify()`` lo decide antes de llamar a ``check_golden``; este
    helper es la versión "ya sé que existe, leélo".
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract_timing(stdout: str, timing_regex: str) -> Optional[dict]:
    """Extrae el timing del stdout con la regex del manifiesto.

    La regex DEBE contener un grupo de captura (lo enforcé
    ``core.manifest``: ``timing_regex`` se rechaza en load si no tiene
    ``(``). El primer match → ``group(1)`` se intenta convertir a
    ``float``. Si la conversión falla, devolvemos ``None`` (no un dict
    con string raro) — el certificado igualmente recibirá el
    ``wall_clock_s`` y el operador puede mirar el stdout crudo.

    Si no hay match, ``None``: el benchmark no imprimió el formato
    esperado, el certificado lo dirá como "sin timing reportado".
    """
    pat = re.compile(timing_regex)
    m = pat.search(stdout)
    if m is None:
        return None
    raw = m.group(1)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return {
        "value": value,
        "raw": raw,
        "unit": "s",
    }


def _resolve_actual_text(
    repo_dir: str,
    manifest: Manifest,
    stdout: str,
) -> tuple[str, str]:
    """Decide de dónde sale el texto a comparar contra el golden.

    Devuelve ``(actual_text, source_label)``. La regla:

      * Si ``manifest.verify`` trae ``output_file`` (atributo opcional,
        leí­do defensivamente con ``getattr`` — el schema canónico
        todavía no lo tiene, pero el contrato §7.1 lo menciona y el
        repo demo ``bsw`` lo usa), se lee ESE archivo del ``repo_dir``.
      * Si no, se usa ``stdout`` del ``RunResult``.

    Devolvemos un ``source_label`` para que el trace / el log del
    orquestador digan explícitamente "leí 'archivo X' (no stdout)" —
    hace que la diagnosis de un FAIL sea inmediata.
    """
    output_file = getattr(manifest.verify, "output_file", None)
    if output_file:
        path = os.path.join(repo_dir, output_file)
        return _read_text_file(path), f"file:{output_file}"
    return stdout, "stdout"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def verify(
    manifest: Manifest,
    oracle: Oracle,
    repo_dir: str,
    config: Config,  # noqa: ARG001 — presente para simetría con el resto de las fases y para futuro tuning (p.ej. timeout override por env)
    trace: Optional[TraceWriter] = None,
) -> VerifyOutcome:
    """FASE 4 — corre el binario y evalúa el modo del manifiesto.

    Pasos (blueprint §7):

      1. ``result = oracle.run(manifest.run.cmd, manifest.run.timeout_s)``.
      2. Despacha según ``manifest.verify.mode``:
         - ``self_check``    → ``parity.check_self_check(result.stdout,
                                manifest.verify.pass_regex)``.
         - ``golden_output`` → lee el golden de
           ``manifest.verify.golden_file`` (relativo a ``repo_dir``) y
           decide el "actual" (stdout o ``output_file``); compara con
           ``parity.check_golden`` usando ``numeric_rtol/atol`` del
           manifiesto.
         - ``none``          → ``verdict=NO_ORACLE`` sin tocar parity.
      3. Timing: si ``manifest.timing_regex`` está set, extrae el valor
         de ``result.stdout``; el ``wall_clock_s`` SIEMPRE se mide.
      4. Emite ``{"ev":"verify", ...}`` al trace con verdict / detail /
         mode / n_compared / timing — INV-4, ANTES de devolver.
      5. Devuelve un :class:`VerifyOutcome` (no solo el
         :class:`VerifyResult` crudo) para que el handler y el reporte
         tengan a mano el :class:`ParityResult` completo y el wall clock.

    Trazabilidad (INV-4): un solo evento ``verify`` con todos los
    campos que el dashboard y el certificado necesitan. Si el
    ``oracle.run`` lanza (subprocess murió, timeout, archivo no
    existe), la excepción se propaga — el handler la captura y la FSM
    transiciona a FAILED (INV-5).
    """
    del config  # API simétrica; se reserva para tuning futuro

    mode = manifest.verify.mode

    # 1. Correr el benchmark.
    t0 = time.monotonic()
    result = oracle.run(manifest.run.cmd, manifest.run.timeout_s)
    wall_clock = time.monotonic() - t0

    # 2. Decidir verdict.
    parity: ParityResult
    verdict: str

    if mode == "self_check":
        assert manifest.verify.pass_regex is not None  # enforcé en core.manifest
        parity = check_self_check(result.stdout, manifest.verify.pass_regex)
        verdict = VERDICT_PASS if parity.ok else VERDICT_FAIL

    elif mode == "golden_output":
        assert manifest.verify.golden_file is not None  # enforcé en core.manifest
        golden_path = os.path.join(repo_dir, manifest.verify.golden_file)
        golden_text = _read_text_file(golden_path)
        actual_text, source_label = _resolve_actual_text(repo_dir, manifest, result.stdout)
        parity = check_golden(
            actual_text,
            golden_text,
            rtol=manifest.verify.numeric_rtol,
            atol=manifest.verify.numeric_atol,
        )
        verdict = VERDICT_PASS if parity.ok else VERDICT_FAIL

    else:  # "none" — F-08: NO_ORACLE es final legítimo, no un error
        parity = ParityResult(ok=False, detail="verify.mode=none (sin oráculo declarado)")
        verdict = VERDICT_NO_ORACLE

    # 3. Timing.
    timing: Optional[dict] = None
    if manifest.timing_regex is not None:
        timing = _extract_timing(result.stdout, manifest.timing_regex)
    # El wall_clock siempre va, complementando (o suplantando) al regex.
    if timing is None:
        timing = {"value": wall_clock, "raw": f"{wall_clock:.3f}", "unit": "s", "source": "wall_clock"}
    else:
        timing["wall_clock_s"] = wall_clock

    # 4. Construir el VerifyResult (schema L1) y emitir el trace.
    verify_result = VerifyResult(
        ran=result.ran,
        exit_code=result.exit_code,
        verdict=verdict,
        parity_details=parity.detail,
        timing=timing,
    )

    if trace is not None:
        emit_payload: dict = {
            "verdict": verdict,
            "detail": parity.detail,
            "mode": mode,
            "ran": result.ran,
            "exit_code": result.exit_code,
            "wall_clock_s": wall_clock,
        }
        if parity.n_compared:
            emit_payload["n_compared"] = parity.n_compared
        if timing is not None and "value" in timing:
            emit_payload["timing_value"] = timing["value"]
        if mode == "golden_output" and manifest.verify.golden_file is not None:
            emit_payload["golden_file"] = manifest.verify.golden_file
            output_file = getattr(manifest.verify, "output_file", None)
            if output_file:
                emit_payload["output_file"] = output_file
        trace.emit("verify", **emit_payload)

    return VerifyOutcome(
        verify_result=verify_result,
        parity=parity,
        wall_clock_s=wall_clock,
        mode=mode,
    )


def verify_handler(ctx) -> None:
    """Phase handler para la FSM (RUNNING + PARITY).

    El driver de ``core.state`` invoca este handler UNA vez por run
    (el estado ``PARITY`` es el último "antes de REPORTING"; ``RUNNING``
    se queda como stub porque el run ya lo hizo el oracle dentro de
    ``verify()`` — esta fase cubre las dos desde un solo handler para
    no duplicar trabajo). Lee:

      * ``ctx.config``       — ``Config`` del run.
      * ``ctx.repo_dir``     — workspace del repo.
      * ``ctx.oracle``       — oracle inyectado (e.g. ``MockOracle`` o el
                               ``RealOracle`` futuro).
      * ``ctx.manifest``     — :class:`Manifest` (lo carga el orquestador
                               antes de invocar esta fase, o lo inyecta
                               el override del caller en tests).
      * ``ctx.trace``        — :class:`TraceWriter` del run.

    Persiste el :class:`VerifyResult` en el contexto para que
    ``REPORTING`` lo consuma, y emite un evento ``verify`` al trace.
    """
    manifest: Manifest | None = getattr(ctx, "manifest", None)
    if manifest is None:
        # Sin manifiesto no hay nada que verificar. El handler NO falla
        # el run — emite un trace con NO_ORACLE y guarda un VerifyResult
        # neutro para que REPORTING no explote al consumir ``ctx.verify``.
        noop = VerifyResult(
            ran=False,
            exit_code=-1,
            verdict=VERDICT_NO_ORACLE,
            parity_details="verify_handler llamado sin ctx.manifest (sin oráculo)",
            timing=None,
        )
        ctx.verify = noop
        ctx.trace.emit("verify", verdict=VERDICT_NO_ORACLE, detail=noop.parity_details, mode="none")
        return

    oracle: Oracle | None = getattr(ctx, "oracle", None)
    if oracle is None:
        # El orquestador todavía no inyectó el oracle (camino análogo a
        # build_loop_handler). Stub honesto: NO_ORACLE + trace.
        noop = VerifyResult(
            ran=False,
            exit_code=-1,
            verdict=VERDICT_NO_ORACLE,
            parity_details="verify_handler llamado sin ctx.oracle (sin oráculo disponible)",
            timing=None,
        )
        ctx.verify = noop
        ctx.trace.emit("verify", verdict=VERDICT_NO_ORACLE, detail=noop.parity_details, mode="none")
        return

    outcome = verify(
        manifest=manifest,
        oracle=oracle,
        repo_dir=ctx.repo_dir,
        config=ctx.config,
        trace=ctx.trace,
    )
    ctx.verify = outcome.verify_result
    # El ParityResult completo queda accesible para REPORTING / tests.
    ctx.parity = outcome.parity
    ctx.verify_wall_clock_s = outcome.wall_clock_s


__all__ = [
    "VERDICT_FAIL",
    "VERDICT_NO_ORACLE",
    "VERDICT_PASS",
    "VerifyOutcome",
    "verify",
    "verify_handler",
]
