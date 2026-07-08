"""tests/test_trace.py — L1 tests for ``core.trace``.

Every test is hermetic: it uses ``tmp_path`` for the trace file and never
touches the real workspace. The writer/reader are tested independently of
any pipeline state, so these tests are stable even when the rest of the
orchestrator is mid-development.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from core.trace import TraceWriter, read_events


_RUN_ID = "run_test_abcd1234"


def _path(tmp_path: Path, name: str = "trace.jsonl") -> str:
    return str(tmp_path / name)


def test_emit_writes_one_jsonl_line_per_call(tmp_path: Path) -> None:
    path = _path(tmp_path)
    w = TraceWriter(path, _RUN_ID)

    w.emit("phase", phase="BUILD_LOOP")
    w.emit("build", iteration=3, errors=17, delta=-9)
    w.emit("fix", sig="sig-xyz", tier="local", applied=True, delta=-3,
           commit="a1b2c3", tokens=412)

    raw = Path(path).read_text(encoding="utf-8").splitlines()
    assert len(raw) == 3, f"expected 3 lines, got {len(raw)}: {raw!r}"

    for i, line in enumerate(raw):
        obj = json.loads(line)
        assert isinstance(obj, dict)
        assert "ts" in obj and isinstance(obj["ts"], str), f"line {i} missing ts"
        assert obj["run"] == _RUN_ID, f"line {i} missing/invalid run"
        assert "ev" in obj and isinstance(obj["ev"], str), f"line {i} missing ev"


def test_read_events_returns_all_with_index_keys(tmp_path: Path) -> None:
    path = _path(tmp_path)
    w = TraceWriter(path, _RUN_ID)
    w.emit("phase", phase="BUILD_LOOP")
    w.emit("build", iteration=3, errors=17, delta=-9)
    w.emit("fix", sig="sig-xyz", tier="local", applied=True, delta=-3,
           commit="a1b2c3", tokens=412)

    events = read_events(path)
    assert len(events) == 3
    assert [e["_i"] for e in events] == [0, 1, 2]
    assert events[0]["ev"] == "phase" and events[0]["phase"] == "BUILD_LOOP"
    assert events[1]["ev"] == "build" and events[1]["iteration"] == 3
    assert events[2]["ev"] == "fix" and events[2]["tokens"] == 412


def test_read_events_after_filters_by_index(tmp_path: Path) -> None:
    path = _path(tmp_path)
    w = TraceWriter(path, _RUN_ID)
    w.emit("phase", phase="BUILD_LOOP")
    w.emit("build", iteration=3, errors=17, delta=-9)
    w.emit("fix", sig="sig-xyz", tier="local", applied=True, delta=-3,
           commit="a1b2c3", tokens=412)

    # after=0 → indices 1, 2 (the last two events).
    tail = read_events(path, after=0)
    assert [e["_i"] for e in tail] == [1, 2]
    assert tail[0]["ev"] == "build"
    assert tail[1]["ev"] == "fix"

    # after=2 → nothing left.
    assert read_events(path, after=2) == []


def test_read_events_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert read_events("/no/existe/trace.jsonl") == []


def test_ts_field_is_iso8601_parseable(tmp_path: Path) -> None:
    path = _path(tmp_path)
    w = TraceWriter(path, _RUN_ID)
    w.emit("phase", phase="SCANNING")

    events = read_events(path)
    assert len(events) == 1
    ts = events[0]["ts"]
    # ``datetime.fromisoformat`` accepts the ``+00:00`` suffix that
    # ``datetime.now(timezone.utc).isoformat()`` produces on 3.11+.
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None, "ts must carry timezone info"


def test_emit_persists_before_returning_invariant_inv4(tmp_path: Path) -> None:
    """INV-4: after ``emit`` returns, the line must already be on disk."""
    path = _path(tmp_path)
    w = TraceWriter(path, _RUN_ID)
    w.emit("phase", phase="QUEUED")

    # No flush() / fsync() from us: a re-read straight from disk must see it.
    on_disk = Path(path).read_text(encoding="utf-8")
    assert on_disk.endswith("\n"), "append-only writer must terminate each line"
    obj = json.loads(on_disk)
    assert obj["ev"] == "phase" and obj["phase"] == "QUEUED"


def test_emit_uses_explicit_ts_when_provided(tmp_path: Path) -> None:
    path = _path(tmp_path)
    w = TraceWriter(path, _RUN_ID)
    fixed = "2026-07-08T12:00:00+00:00"
    w.emit("phase", phase="SCANNING", ts=fixed)

    events = read_events(path)
    assert events[0]["ts"] == fixed


def test_emit_is_append_only_does_not_truncate(tmp_path: Path) -> None:
    path = _path(tmp_path)
    w1 = TraceWriter(path, _RUN_ID)
    w1.emit("phase", phase="CLONING")
    first = Path(path).read_text(encoding="utf-8")

    # A second writer instance hitting the same path MUST extend, not replace.
    w2 = TraceWriter(path, _RUN_ID)
    w2.emit("phase", phase="SCANNING")
    second = Path(path).read_text(encoding="utf-8")

    assert second.startswith(first), "second emit must preserve the first line"
    assert second.count("\n") == 2


def test_emit_flushes_across_subprocess_boundary(tmp_path: Path) -> None:
    """If a child process were to crash right after ``emit`` returns, the
    event must already be visible to a parent reading the file. We model
    that by re-opening the file from a fresh file descriptor after
    ``emit`` returns."""
    path = _path(tmp_path)
    w = TraceWriter(path, _RUN_ID)
    w.emit("phase", phase="BUILD_LOOP")

    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline()
    assert json.loads(first_line)["phase"] == "BUILD_LOOP"


def test_read_events_skips_blank_lines(tmp_path: Path) -> None:
    path = _path(tmp_path)
    # Pre-seed the file with two valid events and a blank line in the middle.
    Path(path).write_text(
        "\n".join([
            json.dumps({"ts": "2026-01-01T00:00:00+00:00", "run": _RUN_ID, "ev": "phase", "phase": "A"}),
            "",
            json.dumps({"ts": "2026-01-01T00:00:01+00:00", "run": _RUN_ID, "ev": "phase", "phase": "B"}),
            "   \n",
            json.dumps({"ts": "2026-01-01T00:00:02+00:00", "run": _RUN_ID, "ev": "phase", "phase": "C"}),
            "",
        ])
        + "\n",
        encoding="utf-8",
    )

    events = read_events(path)
    assert [e["_i"] for e in events] == [0, 1, 2]
    assert [e["phase"] for e in events] == ["A", "B", "C"]


def test_read_events_malformed_line_raises(tmp_path: Path) -> None:
    """A corrupt line is a real failure, not something we silently skip."""
    path = _path(tmp_path)
    Path(path).write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "run": _RUN_ID, "ev": "phase", "phase": "A"})
        + "\n{not valid json}\n",
        encoding="utf-8",
    )
    with pytest.raises(json.JSONDecodeError):
        read_events(path)
