"""core/trace.py — primitive (L1): append-only JSONL writer/reader for the run trace.

The trace file is the single source of truth of "what happened in this run" that
the dashboard polls. Every pipeline phase (``SCAN``, ``PORT``, ``BUILD_LOOP``,
``RUN``, ``PARITY``, ``REPORT``) emits one event per observable step; the
dashboard renders them live as the run progresses.

Layering: L1 primitive. This module imports ONLY from ``core.schemas`` (for
type clarity) and the standard library (``json``, ``os``, ``datetime``). It
does NOT depend on ``config``, ``phases``, ``oracle``, ``llm`` or ``state``:
the trace is the lowest layer of the pipeline's memory and must keep working
even if everything above it is broken or mocked.

Design constraints (from the blueprint):

* **INV-4 (persist before acting).** ``TraceWriter.emit`` MUST flush the
  event to disk before returning, so that a crash in the caller never loses
  an event. No in-memory batching, no deferred writes.
* **Append-only.** The file is only ever opened in mode ``"a"``. No
  rewrites, no truncation. ``read_events`` never mutates the file.
* **Stable schema.** The keys ``ts`` / ``run`` / ``ev`` are added by the
  writer and MUST NOT be renamed. Additional fields are passed through
  verbatim via ``**fields``.
* **Indexing.** The dashboard's polling contract is
  ``GET /runs/{id}/events?after=<n>`` where ``n`` is the 0-based LINE INDEX
  of the last event the client has already seen. ``read_events`` therefore
  tags every returned dict with ``_i`` (its line index) and filters by
  ``line_index > after``.

Event format reference (blueprint §4.3)::

    {"ts": "...", "run": "run_ab12cd34", "ev": "phase", "phase": "BUILD_LOOP"}
    {"ts": "...", "run": "...",       "ev": "build", "iteration": 3, ...}
    {"ts": "...", "run": "...",       "ev": "fix",   "sig": "...", ...}
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


_DEFAULT_TS_KEY = "ts"
_RUN_KEY = "run"
_EV_KEY = "ev"


def _utc_now_iso() -> str:
    """Current UTC time as an ISO 8601 string (``+00:00`` suffix)."""
    return datetime.now(timezone.utc).isoformat()


class TraceWriter:
    """Append-only writer for a run's ``trace.jsonl``.

    The instance is bound 1:1 to a path on disk (the run's trace file) and
    to a ``run_id`` that is injected into every event. It is *not*
    thread-safe across the same instance; the pipeline serialises access
    per run (one writer per workspace per run).

    Construction does NOT touch the file. The file is created lazily on the
    first ``emit`` call, in append mode, so that merely instantiating a
    writer cannot fail because of permissions or pre-existing state.
    """

    def __init__(self, path: str, run_id: str) -> None:
        self._path = path
        self._run_id = run_id

    @property
    def path(self) -> str:
        """Absolute or workspace-relative path of the JSONL file this writer appends to."""
        return self._path

    @property
    def run_id(self) -> str:
        """Run identifier injected into every event this writer emits."""
        return self._run_id

    def emit(self, ev: str, **fields: object) -> None:
        """Append ONE event line to the trace and flush it to disk.

        The event line is::

            {"ts": <ISO8601 UTC>, "run": <run_id>, "ev": <ev>, **fields}

        ``ts`` is auto-generated here (UTC, ISO 8601) unless the caller
        already provided one in ``fields`` — this lets test code and
        replay code inject deterministic timestamps without bypassing the
        writer.

        INV-4: the line is written and flushed before this method returns.
        We open the file per call (mode ``"a"``), write ``json.dumps(...) +
        "\\n"``, then ``flush()`` and ``os.fsync()``. The per-call
        open/close is intentional: it removes any ambiguity about buffered
        state surviving a crash in the caller.
        """
        obj: dict[str, object] = dict(fields)
        obj.setdefault(_DEFAULT_TS_KEY, _utc_now_iso())
        obj[_RUN_KEY] = self._run_id
        obj[_EV_KEY] = ev

        line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())


def read_events(path: str, after: int = -1) -> list[dict]:
    """Read events from a trace JSONL file, optionally skipping the first ``after + 1`` lines.

    Semantics:

    * ``after = -1`` (default) returns ALL non-empty events.
    * ``after = N`` (N >= 0) returns only events whose 0-based line index
      is strictly greater than N. The dashboard uses this for polling
      ("send me everything past the last line I already have").
    * Each returned dict is tagged with ``_i`` = its 0-based line index in
      the file. This is what the dashboard uses to compute the next
      ``after`` for the following request.
    * Empty / whitespace-only lines are silently skipped (and do NOT
      advance the index — the index is the count of valid events, not
      raw lines). Malformed lines raise ``json.JSONDecodeError``; we do
      NOT silently swallow them, because a corrupt event is a real
      failure that the pipeline must surface.
    * If the file does not exist, returns ``[]`` (the dashboard must
      handle a not-yet-created trace, e.g. between run creation and the
      first ``emit``).
    """
    if not os.path.exists(path):
        return []

    out: list[dict] = []
    idx = 0
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            if idx > after:
                ev = json.loads(stripped)
                ev["_i"] = idx
                out.append(ev)
            idx += 1
    return out
