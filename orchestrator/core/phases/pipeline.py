"""core/phases/pipeline.py — integración end-to-end (L4): cablea TODOS los handlers reales.

Este módulo es el ÚNICO lugar que junta build_loop + verify + ship sobre el driver de state
(T8). Los tres handlers fueron construidos por separado y usan nombres de campo de ``ctx``
distintos; acá se PUENTEAN sin editar los módulos mergeados:
  - se inyecta ``ctx.oracle`` / ``ctx._oracle`` (para build_loop y verify),
  - se inyecta ``ctx.manifest`` (para verify),
  - tras verify se copia ``ctx.verify`` → ``ctx.verify_result`` (nombre que lee ship).

Corre el pipeline COMPLETO QUEUED→…→DONE en modo mock (oracle de fixtures), generando el
certificado. En modo real, el mismo cableado usa el RealOracle (M0). Respeta AD-3 (el driver de
state es la única autoridad de control) e INV-5 (finales honestos).
"""

from __future__ import annotations

from core.config import Config
from core.manifest import Manifest
from core.oracle.base import Oracle
from core.phases.build_loop import build_loop_handler
from core.phases.ship import ship_handler
from core.phases.verify import verify_handler
from core.schemas import Run, RunState
from core.state import SqliteRunStore, default_handlers, run_pipeline
from core.trace import TraceWriter


def run_full_pipeline(
    run_id: str,
    store: SqliteRunStore,
    config: Config,
    trace: TraceWriter,
    oracle: Oracle,
    manifest: Manifest,
    repo_dir: str,
) -> Run:
    """Corre el pipeline completo con los handlers REALES cableados.

    ``oracle`` decide mock/real (mismo contrato, INV-6). ``manifest`` le dice a VERIFY cómo
    correr/verificar. ``repo_dir`` es el workspace ya clonado (con las fuentes CUDA→HIP).
    """

    def _loop(ctx) -> None:
        # build_loop lee ctx._oracle (y algunos caminos ctx.oracle): seteamos ambos.
        ctx.oracle = oracle
        ctx._oracle = oracle
        # El manifiesto también se inyecta acá (no solo en verify): el patcher
        # necesita saber qué archivos son oráculo (golden/output) para vetarlos.
        ctx.manifest = manifest
        build_loop_handler(ctx)

    def _verify(ctx) -> None:
        ctx.oracle = oracle
        ctx.manifest = manifest
        verify_handler(ctx)
        # Puente de nombres: verify_handler deja el resultado en ctx.verify;
        # ship_handler lo lee como ctx.verify_result.
        ctx.verify_result = getattr(ctx, "verify", None)

    def _report(ctx) -> None:
        # P0.8 (audit codex): ctx.run era el snapshot cargado ANTES de correr
        # las fases → el certificado salía con counters en cero mientras el
        # store y el trace tenían los reales. REPORTING refresca el run y
        # construye certificado + evento report desde el MISMO estado.
        fresh_run = store.get(run_id)
        if fresh_run is not None:
            ctx.run = fresh_run
        ship_handler(ctx)
        # Evento 'report': el resumen numérico que consume el dashboard.
        # Hasta ahora solo existía en el fixture demo — el pipeline real no lo
        # emitía. Números desde counters del store + costo calculado acá (F-17).
        fresh = store.get(run_id)
        if fresh is not None:
            c = fresh.counters
            trace.emit(
                "report",
                errors_initial=c.errors_initial,
                errors_current=c.errors_current,
                fixes_deterministic=c.fixes_deterministic,
                fixes_local=c.fixes_local,
                fixes_remote=c.fixes_remote,
                tokens_local=c.tokens_local,
                tokens_remote=c.tokens_remote,
                iterations=c.iterations,
                cost_remote_usd=round(
                    c.tokens_remote / 1_000_000 * config.remote_price_per_mtok, 4
                ),
            )

    overrides = {
        RunState.BUILD_LOOP: _loop,
        RunState.RUNNING: _verify,   # verify_handler hace run + paridad (§7)
        RunState.PARITY: lambda ctx: None,   # la paridad ya ocurrió en RUNNING; no re-ejecutar
        RunState.REPORTING: _report,
    }
    handlers = default_handlers(config, overrides=overrides)
    return run_pipeline(run_id, store, config, trace, handlers=handlers, repo_dir=repo_dir)
