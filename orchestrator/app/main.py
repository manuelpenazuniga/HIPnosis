"""app/main.py — FastAPI application factory (L6 transport).

Responsibilities
----------------
1. Build the ``FastAPI`` app and include the API router from
   ``app.api``.
2. Wire up the run store (currently an in-memory ``RunStore``; the
   future ``core.state`` will be a drop-in replacement behind the same
   protocol).
3. Optionally mount the dashboard static directory at ``"/"`` if it
   exists on disk. The dashboard is another task's deliverable, so
   *missing* it must NOT break the API — we just skip the mount.

Starlette matches routes in registration order, so the API router is
included BEFORE the optional static mount. With that ordering, ``/runs``
and ``/healthz`` are always reachable, and the static mount acts purely
as a fallback for paths the API does not own (e.g. ``GET /`` returns
``dashboard/index.html`` when present).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.replay import bootstrap_replay
from app.store import InMemoryRunStore


_DASHBOARD_CANDIDATES = (
    Path(__file__).resolve().parent.parent.parent / "dashboard",
    Path(__file__).resolve().parent.parent / "dashboard",
)


def _resolve_dashboard_dir() -> Path | None:
    """Return the first existing dashboard dir under the candidates, else ``None``."""
    for candidate in _DASHBOARD_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return None


def create_app() -> FastAPI:
    """Build a fresh ``FastAPI`` app.

    A factory (not a module-level singleton) keeps the test suite
    hermetic: each ``TestClient`` can construct an isolated app with its
    own store and its own (possibly monkey-patched) resolver.
    """
    app = FastAPI(title="HIPnosis orchestrator", version="0.1.0")

    app.state.store = InMemoryRunStore()

    # AD-4: en ORACLE_MODE=replay, sembrar el run grabado + su reloj de replay.
    # En cualquier otro modo devuelve None y no hace nada.
    app.state.replay = bootstrap_replay(app.state.store)

    # Register API routes BEFORE the static mount so they win the
    # routing match (Starlette picks the first prefix-match in
    # registration order). The mount at "/" is then a true fallback.
    app.include_router(router)

    dashboard_dir = _resolve_dashboard_dir()
    if dashboard_dir is not None:
        app.mount(
            "/",
            StaticFiles(directory=str(dashboard_dir), html=True),
            name="dashboard",
        )

    return app


app = create_app()
