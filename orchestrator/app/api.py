"""app/api.py — FastAPI router for the run lifecycle (L6 transport).

Endpoints
---------
* ``POST /runs``                       enqueue a new run (state = ``QUEUED``).
* ``GET  /runs``                       list runs.
* ``GET  /runs/{run_id}``              fetch one run (``404`` if unknown).
* ``GET  /runs/{run_id}/events?after`` paginate the trace JSONL.
* ``GET  /healthz``                    liveness probe.

AD-3: this router never drives pipeline phases. ``POST /runs`` only records
the run in the store as ``QUEUED`` — the FSM in ``core.state`` (a later
task) is what actually picks the run up and starts cloning / scanning /
porting. Replay mode works by simply *reading* a recorded trace via
``GET /events?after=N``; the loop is not involved.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.schemas import Run
from core.trace import read_events


router = APIRouter()


class _WorkspacesLike(Protocol):
    """Surface the router needs from whatever owns run workspaces."""

    def get(self, run_id: str) -> Run | None: ...
    def list(self) -> list[Run]: ...
    def create(self, repo_url: str) -> Run: ...


class CreateRunBody(BaseModel):
    """Request body for ``POST /runs``."""

    repo_url: str = Field(..., min_length=1)


def _get_store(request: Request) -> _WorkspacesLike:
    # En modo autorun el store es un SQLite de ARCHIVO con check_same_thread=True:
    # uvicorn corre cada handler en un thread distinto, así que abrimos una conexión
    # FRESCA por request (en el thread correcto). El archivo comparte estado entre
    # conexiones. En tests (db_path=None) usamos el store en memoria de app.state.
    db_path = getattr(request.app.state, "db_path", None)
    if db_path:
        from core.state import SqliteRunStore
        return SqliteRunStore(db_path)
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=500, detail="run store not configured")
    return store


def trace_path_for_run(run_id: str) -> str:
    """Return the on-disk path of the trace JSONL for ``run_id``.

    The default layout is ``<repo>/workspaces/<run_id>/trace.jsonl``
    (relative to the orchestrator package). The function is a module-level
    seam so tests can ``monkeypatch`` it to point at a temp directory,
    and so the real ``core.state`` can later swap the layout without
    touching the router.

    A path that does not exist on disk is a valid result — the events
    endpoint treats it as "no events yet" and returns ``[]``.
    """
    from pathlib import Path

    workspaces = Path(__file__).resolve().parent.parent / "workspaces"
    return str(workspaces / run_id / "trace.jsonl")


@router.post("/runs", response_model=Run, status_code=200)
def create_run(body: CreateRunBody, request: Request) -> Run:
    """Enqueue a run y (en producción) dispará el pipeline en un thread de fondo.

    AD-3: la api NO ejecuta fases inline; registra el run como ``QUEUED`` y delega
    la conducción al driver de state (via ``core.runner.execute_run``) en un thread
    aparte, para que POST devuelva de inmediato y el dashboard vea la corrida en vivo
    por polling. Si ``app.state.autorun`` es False (tests) solo se encola.
    """
    store = _get_store(request)
    run = store.create(body.repo_url)

    app = request.app
    config = getattr(app.state, "config", None)
    autorun = getattr(app.state, "autorun", False)
    db_path = getattr(app.state, "db_path", None)
    # replay no ejecuta pipeline (AD-4); tampoco sin autorun/db_path.
    if autorun and db_path and config is not None and config.oracle_mode != "replay":
        import threading

        from core.runner import execute_run
        from core.state import SqliteRunStore

        def _bg(run_id: str) -> None:
            # El thread de fondo abre SU PROPIA conexión SQLite (check_same_thread=True).
            worker_store = SqliteRunStore(db_path)
            try:
                execute_run(run_id, worker_store, config)
            except Exception:  # noqa: BLE001 — INV-5: nunca tumbar el server por un run
                pass

        threading.Thread(target=_bg, args=(run.id,), daemon=True).start()

    return run


@router.get("/runs", response_model=list[Run])
def list_runs(request: Request) -> list[Run]:
    store = _get_store(request)
    return store.list()


@router.get("/runs/{run_id}", response_model=Run)
def get_run(run_id: str, request: Request) -> Run:
    store = _get_store(request)
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    return run


@router.get("/runs/{run_id}/events")
def get_run_events(
    run_id: str,
    request: Request,
    after: int = Query(-1, ge=-1),
) -> list[dict]:
    """Return trace events for ``run_id`` strictly past line index ``after``.

    The dashboard polls this with ``?after=<last_seen_index>``; ``after=-1``
    (default) returns the whole trace from the start. The trace file is
    read by ``core.trace.read_events`` — this router does NOT reimplement
    the JSONL parsing (it is the contract of L1 ``core.trace``).

    A missing run (404) is reported distinctly from a run whose trace
    has not been written yet: in the latter case we return ``[]`` with
    ``200`` so the dashboard can poll a freshly-created run without
    404-loops before the first ``emit``.
    """
    store = _get_store(request)
    if store.get(run_id) is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")

    # AD-4 modo replay: si hay una sesión de replay para ESTE run, servimos el
    # trace grabado con timing acelerado (§9). El reloj revela los eventos de a
    # poco; una carga fresca del dashboard (after == -1) reinicia la reproducción.
    replay = getattr(request.app.state, "replay", None)
    if replay is not None and replay.run_id == run_id:
        visible = replay.clock.visible_count()
        events = read_events(replay.trace_path, after=after)
        return [e for e in events if e["_i"] < visible]

    return read_events(trace_path_for_run(run_id), after=after)


@router.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}
