"""app/store.py — minimal in-memory ``RunStore`` (L6 transport layer).

AD-3 mandates that ``app/api`` never drives pipeline phases; the FSM in
``core.state`` is the unique driver. This module is the temporary stand-in
for that state, providing just enough surface for the HTTP layer to:

* register a new run when a client ``POST /runs`` arrives (``create``);
* look a run up by id for ``GET /runs/{id}`` (``get``);
* enumerate runs for ``GET /runs`` (``list``).

The contract here is intentionally tiny: any future ``core.state`` (SQLite-
backed, resumable, multi-worker) MUST honour the same ``RunStore`` protocol
so the router can be wired to it without touching the API surface.
"""

from __future__ import annotations

from typing import Protocol

from core.config import budgets
from core.schemas import Counters, Run


_RUN_ID_PREFIX = "run_"


def _new_run_id() -> str:
    """Return a fresh run id of the form ``run_<8 hex>``.

    We use ``uuid4().hex[:8]`` per the brief: 8 hex chars gives 32 bits of
    entropy, enough to make accidental collisions inside a single deployment
    vanishingly unlikely. Real uniqueness across deployments / replays is
    the responsibility of ``core.state`` later — this function is just
    the placeholder used while that module does not yet exist.
    """
    import uuid

    return _RUN_ID_PREFIX + uuid.uuid4().hex[:8]


class RunStore(Protocol):
    """Protocol every run repository must satisfy (memory, SQLite, ...)."""

    def create(self, repo_url: str) -> Run:
        ...

    def get(self, run_id: str) -> Run | None:
        ...

    def list(self) -> list[Run]:
        ...

    def put(self, run: Run) -> Run:
        """Insert/replace a fully-formed run (used to seed a recorded replay run)."""
        ...


class InMemoryRunStore:
    """Trivial dict-backed implementation used until ``core.state`` lands.

    Thread-safety: NOT thread-safe. The orchestrator runs single-process per
    the blueprint (§1 topology), so a plain ``dict`` is enough. When the
    real state machine arrives it will replace this object via the
    ``RunStore`` protocol, with no change to the API.
    """

    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def create(self, repo_url: str) -> Run:
        run = Run(
            id=_new_run_id(),
            repo_url=repo_url,
            state="QUEUED",
            budgets=budgets(),
            counters=Counters(),
        )
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(self) -> list[Run]:
        return list(self._runs.values())

    def put(self, run: Run) -> Run:
        """Insert/replace a fully-formed run (used to seed a recorded replay run)."""
        self._runs[run.id] = run
        return run
