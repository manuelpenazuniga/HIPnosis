"""core/state.py — L5 FSM + SQLite persistence + phase driver (AD-3).

This module is the **UNIQUE driver of pipeline phases**. The HTTP layer
(``app/``) calls into ``run_pipeline`` and the ``SqliteRunStore``; it
NEVER calls ``core.phases.*`` directly. Phases call back into the FSM only
through the ``PipelineContext`` they receive — they do not decide what
runs next (INV-1: the LLM is content, the orchestrator is control).

Layering: L5. Imports L4 (``core.phases.scan``, ``core.phases.port``),
L2 (``core.gitrepo``), L1 (``core.schemas``, ``core.config``,
``core.trace``) and stdlib (``os``, ``sqlite3``, ``uuid``, ``dataclasses``,
``typing``). **Never imports ``app``** — direction of dependencies is
strictly ``app → core.state → core.phases``.

The FSM (blueprint §3)::

    QUEUED → CLONING → SCANNING → PORTING → BUILD_LOOP → RUNNING →
              PARITY → REPORTING → DONE
    BUILD_LOOP sin progreso/presupuesto → REPORTING → DONE_PARTIAL
    Excepción no manejada → FAILED(reason)

* **INV-4**: every state transition emits ``{"ev":"phase","phase":<s>}``
  to the trace **before** the corresponding handler runs and before the
  state is persisted. A crash mid-handler still leaves a coherent phase
  event on disk.
* **INV-5**: ``DONE`` / ``DONE_PARTIAL`` / ``FAILED`` are legitimate finals.
  Handler exceptions are caught, the run is persisted as ``FAILED``, and
  the exception is **not** re-raised. The driver never leaves a run
  "colgado" mid-pipeline.
* **§3 (no fine-grained intra-phase resumption)**: the driver does not
  attempt to checkpoint inside a phase. Re-running ``run_pipeline`` from
  the start is acceptable; the workspace + trace together make that
  idempotent enough for T8.

What this module ships vs. what is stubbed
------------------------------------------
* ``SqliteRunStore`` — drop-in replacement for ``InMemoryRunStore``;
  same ``create / get / list / put`` surface, plus two FSM helpers
  (``update_state``, ``update_counters``).
* ``PipelineContext`` — the seam between the FSM and the phases.
* ``default_handlers(config, overrides=...)`` — the canonical map.
  Real handlers are wired for ``CLONING / SCANNING / PORTING`` (those
  exist); the later phases (``BUILD_LOOP / RUNNING / PARITY / REPORTING``)
  are STUBs that emit a ``phase.stub`` event and do nothing more.
  The ``overrides`` seam is the explicit injection point for the
  T14 (BUILD_LOOP), T15 (RUNNING/PARITY) and T16/T17 (REPORTING)
  implementations, and for test mocks.
* ``run_pipeline`` — the heart of the driver.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from core.config import Config, budgets
from core.gitrepo import GitRepo
from core.phases import port as port_phase
from core.phases import scan as scan_phase
from core.schemas import Budgets, Counters, Run, RunState, ScanResult
from core.trace import TraceWriter


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_RUN_ID_PREFIX = "run_"


#: Linear state sequence the driver walks on the happy path. Final
#: states (``DONE_PARTIAL``, ``FAILED``) are reached through side
#: channels: ``BUILD_LOOP`` may signal ``DONE_PARTIAL`` when T14 lands;
#: any unhandled handler exception ends the loop with ``FAILED``. The
#: driver stops as soon as the state is one of the recognised finals.
_LINEAR_SEQUENCE: tuple[str, ...] = (
    RunState.QUEUED,
    RunState.CLONING,
    RunState.SCANNING,
    RunState.PORTING,
    RunState.BUILD_LOOP,
    RunState.RUNNING,
    RunState.PARITY,
    RunState.REPORTING,
    RunState.DONE,
)


# ===========================================================================
# SqliteRunStore — drop-in replacement for InMemoryRunStore
# ===========================================================================

class SqliteRunStore:
    """SQLite-backed run repository; satisfies ``app.store.RunStore``.

    Same protocol surface as ``InMemoryRunStore`` (``create``, ``get``,
    ``list``, ``put``) so the HTTP layer can swap to it without touching
    the router. Adds two FSM-specific helpers used by ``run_pipeline``:

        update_state(run_id, state)
        update_counters(run_id, counters)

    Schema (single table)::

        runs(
            id            TEXT PRIMARY KEY,
            repo_url      TEXT NOT NULL,
            state         TEXT NOT NULL,
            budgets_json  TEXT NOT NULL,   -- Budgets.model_dump_json()
            counters_json TEXT NOT NULL    -- Counters.model_dump_json()
        )

    Thread-safety: NOT thread-safe — the orchestrator is single-process
    per blueprint §1. The default ``check_same_thread=True`` is the
    fail-loud policy; concurrent access from a worker thread will raise
    ``ProgrammingError`` instead of corrupting state.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                repo_url TEXT NOT NULL,
                state TEXT NOT NULL,
                budgets_json TEXT NOT NULL,
                counters_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # -------------------------------------------------------------------
    # RunStore protocol (create / get / list / put)
    # -------------------------------------------------------------------

    def create(self, repo_url: str) -> Run:
        """Create a new run in state ``QUEUED`` with fresh budgets/counters.

        ``id`` follows the blueprint convention: ``"run_" + uuid4().hex[:8]``
        (8 hex chars = 32 bits of entropy, plenty for a single deployment).
        Budgets come from ``config.budgets()`` (i.e. the env-driven default
        ``Config``); ``Counters()`` is the zero-valued model.
        """
        run_id = _RUN_ID_PREFIX + uuid.uuid4().hex[:8]
        run = Run(
            id=run_id,
            repo_url=repo_url,
            state=RunState.QUEUED,
            budgets=budgets(),
            counters=Counters(),
        )
        self._conn.execute(
            "INSERT INTO runs (id, repo_url, state, budgets_json, counters_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                run.id,
                run.repo_url,
                run.state,
                run.budgets.model_dump_json(),
                run.counters.model_dump_json(),
            ),
        )
        self._conn.commit()
        return run

    def get(self, run_id: str) -> Run | None:
        """Look up a run by id; ``None`` if unknown."""
        row = self._conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def list(self) -> list[Run]:
        """Return every persisted run, in insertion order."""
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY rowid"
        ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def put(self, run: Run) -> Run:
        """Upsert a fully-formed run. Used by replay seeders.

        Distinct from ``create`` (which generates a fresh id) and from
        ``update_state`` (which only touches the ``state`` column). The
        budgets and counters of the passed run overwrite whatever is on
        disk for that id.
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(id, repo_url, state, budgets_json, counters_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                run.id,
                run.repo_url,
                run.state,
                run.budgets.model_dump_json(),
                run.counters.model_dump_json(),
            ),
        )
        self._conn.commit()
        return run

    # -------------------------------------------------------------------
    # FSM helpers (not part of the RunStore protocol; used by run_pipeline)
    # -------------------------------------------------------------------

    def update_state(self, run_id: str, state: str) -> None:
        """Persist a new state for ``run_id``. ``KeyError`` if unknown."""
        cur = self._conn.execute(
            "UPDATE runs SET state = ? WHERE id = ?", (state, run_id)
        )
        if cur.rowcount == 0:
            raise KeyError(f"run {run_id!r} not found")
        self._conn.commit()

    def update_counters(self, run_id: str, counters: Counters) -> None:
        """Persist updated ``Counters`` for ``run_id``."""
        cur = self._conn.execute(
            "UPDATE runs SET counters_json = ? WHERE id = ?",
            (counters.model_dump_json(), run_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"run {run_id!r} not found")
        self._conn.commit()

    # -------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------

    def _row_to_run(self, row: sqlite3.Row) -> Run:
        return Run(
            id=row["id"],
            repo_url=row["repo_url"],
            state=row["state"],
            budgets=Budgets.model_validate_json(row["budgets_json"]),
            counters=Counters.model_validate_json(row["counters_json"]),
        )

    def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        self._conn.close()


# ===========================================================================
# PipelineContext + PhaseHandler
# ===========================================================================

#: Signature every phase handler must satisfy. The driver invokes the
#: handler with a fully-populated ``PipelineContext``; the handler
#: returns ``None`` — observable state changes travel back through the
#: context (``ctx.scan_result``, ``ctx.repo_dir``) and through the
#: trace / store.
PhaseHandler = Callable[["PipelineContext"], None]


@dataclass
class PipelineContext:
    """Shared state passed to every phase handler.

    The FSM driver constructs ONE context per run and passes the same
    object to every handler in sequence. Handlers populate fields
    progressively (e.g. ``SCANNING`` fills ``scan_result``); the driver
    does **not** inspect handler-populated fields — INV-1: it just
    walks the sequence and persists the state. Decisions about content
    happen in the LLM; the FSM is content-agnostic.
    """

    run: Run
    repo_dir: str
    config: Config
    store: SqliteRunStore
    trace: TraceWriter
    scan_result: ScanResult | None = None


# ---------------------------------------------------------------------------
# Default phase handlers
# ---------------------------------------------------------------------------

def _stub_handler(state: str) -> PhaseHandler:
    """A phase handler that emits a ``phase.stub`` event and does nothing.

    Replaced when the real phase lands:

      * ``BUILD_LOOP`` — T14 (the deterministic build/fix loop)
      * ``RUNNING``    — T15 (run the produced binary on the oracle)
      * ``PARITY``     — T15 (numerical-parity check vs. the reference)
      * ``REPORTING``  — T16/T17 (port certificate + ship)

    The ``phase.stub`` event is tagged with the state name so a future
    task can detect (in replay) that it is operating on top of a T8-era
    run, and so the dashboard can render these phases with a visual
    marker until the real implementation lands.
    """

    def handler(ctx: PipelineContext) -> None:
        ctx.trace.emit("phase.stub", phase=state)

    handler.__name__ = f"_stub_{state}"
    return handler


def _cloning_handler(ctx: PipelineContext) -> None:
    """CLONING: ``git clone`` the target repo (or accept a pre-set dir).

    Two modes:

    * **Mock / test** — ``ctx.repo_dir`` already points to an existing
      directory (a fixture repo). The handler emits ``cloning.skipped``
      and leaves the directory alone. Downstream phases can then run on
      it without any network access.
    * **Real** — ``ctx.repo_dir`` is empty / does not exist. The handler
      derives a workspace dir from the run id, calls
      ``GitRepo.clone(ctx.run.repo_url, target)``, and updates
      ``ctx.repo_dir`` so the downstream phases see the cloned tree.
    """
    if ctx.repo_dir and os.path.isdir(ctx.repo_dir):
        ctx.trace.emit(
            "cloning.skipped",
            repo_dir=ctx.repo_dir,
            reason="repo_dir already provided (mock/test mode)",
        )
        return

    target = _workspace_dir(ctx.run.id)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    GitRepo.clone(ctx.run.repo_url, target)
    ctx.repo_dir = target
    ctx.trace.emit("cloning.done", repo_dir=target, branch="hipnosis/rocm-port")


def _scanning_handler(ctx: PipelineContext) -> None:
    """SCANNING: deterministic inventory + wave64 + difficulty.

    Wraps ``core.phases.scan.scan`` and stashes the ``ScanResult`` on the
    context so PORTING (T13) and the report (T16) can reuse it without
    re-walking the workspace. Emits a ``scan.done`` event with the
    headline numbers for the dashboard; the full ``ScanResult`` lives
    in the run's structured data, not the trace.
    """
    result = scan_phase.scan(ctx.repo_dir)
    ctx.scan_result = result
    ctx.trace.emit(
        "scan.done",
        files_cuda=len(result.files_cuda),
        loc_kernels=result.loc_kernels,
        difficulty=result.difficulty,
        build_system=result.build_system,
        wave64_total=len(result.wave64_findings),
    )


def _porting_handler(ctx: PipelineContext) -> None:
    """PORTING: thin wrapper around ``core.phases.port.port``.

    Requires a real git repo (cloned by ``CLONING``) and a populated
    ``ctx.scan_result``. The T8 test suite does not exercise this
    handler end-to-end — the integration test stops at ``SCANNING`` —
    but the handler must be reachable and compilable because T13
    already shipped and the port phase needs a driver in the FSM.
    """
    if ctx.scan_result is None:
        raise RuntimeError(
            "PORTING handler called before SCANNING populated ctx.scan_result"
        )
    repo = GitRepo(ctx.repo_dir)
    port_phase.port(repo, ctx.repo_dir, ctx.scan_result, ctx.config, ctx.trace)


def default_handlers(
    config: Config,
    overrides: Optional[dict[str, PhaseHandler]] = None,
) -> dict[str, PhaseHandler]:
    """Return the canonical phase-handler map for the FSM.

    Maps each state in the linear sequence to its handler. The early
    phases are wired to their real implementations (``CLONING``,
    ``SCANNING``, ``PORTING``); the later phases are STUBs that emit a
    ``phase.stub`` event and do nothing more — they will be replaced
    by T14 (BUILD_LOOP), T15 (RUNNING/PARITY) and T16/T17 (REPORTING).

    The ``overrides`` parameter is the **explicit seam** for injecting
    the real implementations (or test mocks) without forking this
    function. The dict is shallowly merged: any key in ``overrides``
    replaces the corresponding default.
    """
    handlers: dict[str, PhaseHandler] = {
        RunState.CLONING: _cloning_handler,
        RunState.SCANNING: _scanning_handler,
        RunState.PORTING: _porting_handler,
        RunState.BUILD_LOOP: _stub_handler(RunState.BUILD_LOOP),
        RunState.RUNNING: _stub_handler(RunState.RUNNING),
        RunState.PARITY: _stub_handler(RunState.PARITY),
        RunState.REPORTING: _stub_handler(RunState.REPORTING),
    }
    if overrides:
        handlers.update(overrides)
    return handlers


# ---------------------------------------------------------------------------
# The driver
# ---------------------------------------------------------------------------

def _workspace_dir(run_id: str) -> str:
    """Per-run workspace path on disk.

    Layout (mirrors ``app.api.trace_path_for_run``): a ``workspaces/``
    directory next to the orchestrator package, one sub-dir per run
    with the cloned tree inside ``repo/``. The trace file (managed by
    the trace layer) lives at ``workspaces/<run_id>/trace.jsonl``.
    """
    return os.path.join("workspaces", run_id, "repo")


def _fail_run(
    run_id: str,
    store: SqliteRunStore,
    trace: TraceWriter,
    exc: BaseException,
) -> Run:
    """Transition a run to ``FAILED(reason)``. Persists + traces. Returns it.

    Two trace events for transparency:

      1. ``{"ev":"phase","phase":"FAILED"}`` — INV-4: the phase event is
         emitted **before** the new state is persisted.
      2. ``{"ev":"failed","reason":<str(exc)>, "exc_type":<classname>}`` —
         a debug event with the exception class and message, so a human
         reading the trace can see what blew up.

    Returns the freshly-loaded ``Run`` (state=FAILED, counters/budgets
    whatever the run had at the moment of failure).
    """
    trace.emit("phase", phase=RunState.FAILED)
    store.update_state(run_id, RunState.FAILED)
    trace.emit(
        "failed",
        reason=str(exc),
        exc_type=type(exc).__name__,
    )
    final = store.get(run_id)
    assert final is not None
    return final


def run_pipeline(
    run_id: str,
    store: SqliteRunStore,
    config: Config,
    trace: TraceWriter,
    handlers: Optional[dict[str, PhaseHandler]] = None,
    repo_dir: Optional[str] = None,
) -> Run:
    """Drive the FSM for a single run; return the final ``Run``.

    Algorithm (blueprint §3):

      1. Load the run from the store (``KeyError`` if unknown).
      2. Build a ``PipelineContext`` (the seam between FSM and phases).
      3. Walk the linear state sequence. For each transition:
         a. **INV-4**: emit ``{"ev":"phase","phase":<s>}`` to the trace
            **before** persisting or executing.
         b. ``store.update_state(run_id, s)``.
         c. Run ``handlers[s](ctx)`` if a handler is registered; states
            with no handler (``QUEUED``, ``DONE`` by default) are no-ops.
      4. If a handler raises, **catch** the exception, call
         ``_fail_run`` to set state=FAILED + trace the reason, and
         return the resulting ``Run``. The exception is **not**
         re-raised (INV-5: ``DONE`` / ``DONE_PARTIAL`` / ``FAILED`` are
         legitimate finals).
      5. On the happy path the loop ends at ``DONE`` and the final
         ``Run`` is returned.

    No fine-grained intra-phase resumption (§3): re-running
    ``run_pipeline`` from the beginning is acceptable; the workspace
    + trace together make that idempotent.
    """
    run = store.get(run_id)
    if run is None:
        raise KeyError(f"run {run_id!r} not found")

    handlers = handlers if handlers is not None else default_handlers(config)

    ctx = PipelineContext(
        run=run,
        repo_dir=repo_dir or "",
        config=config,
        store=store,
        trace=trace,
    )

    for state in _LINEAR_SEQUENCE:
        # INV-4: trace event first, then store, then handler. A crash
        # anywhere past this point still leaves the phase event on disk
        # and a consistent state in the store.
        trace.emit("phase", phase=state)
        store.update_state(run_id, state)

        handler = handlers.get(state)
        if handler is None:
            continue

        try:
            handler(ctx)
        except Exception as exc:  # noqa: BLE001 — INV-5: catch, do not re-raise
            return _fail_run(run_id, store, trace, exc)

    final = store.get(run_id)
    assert final is not None
    return final
