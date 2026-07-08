"""tests/test_state.py — L5 tests for the FSM + SQLite store + driver.

These tests are the structural watchpoint for AD-3: ``core.state`` is the
UNIQUE driver of pipeline phases. They cover:

* ``SqliteRunStore`` round-trip (create / get / list / put / update_state
  / update_counters) and the ``RunStore`` protocol surface.
* ``run_pipeline`` walking the linear sequence with stub handlers
  (one ``phase`` event per transition, in order).
* INV-4: a phase event is emitted BEFORE the corresponding handler runs.
* INV-5: a handler exception ends the run in ``FAILED`` and is not
  re-raised; the run is persisted with that state.
* Live integration: the real ``SCANNING`` handler on
  ``tests/fixtures/scan_repo`` populates ``ctx.scan_result``.
* AD-3: ``core.state`` does not import ``app`` (defence in depth on
  the layering rule).

All tests are hermetic: ``tmp_path`` for the SQLite file and the trace
JSONL, in-memory stores and stub handlers — no network, no GPU, no
``hipify-perl``, no subprocess.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Callable

import pytest

from core import state as state_module
from core.config import Config, get_config
from core.phases import scan as scan_phase
from core.schemas import Counters, Run, RunState, ScanResult
from core.state import (
    PipelineContext,
    SqliteRunStore,
    default_handlers,
    run_pipeline,
)
from core.trace import TraceWriter, read_events


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scan_repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> Config:
    """A fixed ``Config`` for deterministic tests (env-independent)."""
    return get_config()


def _trace(tmp_path: Path, run_id: str) -> tuple[TraceWriter, str]:
    """Return ``(writer, path)`` so the test can read the trace back."""
    path = str(tmp_path / "trace.jsonl")
    return TraceWriter(path, run_id), path


def _stub_recorder() -> tuple[dict[str, Callable[[PipelineContext], None]], list[str]]:
    """Build a stub-handler map that records the order in which it is called.

    Each stub does nothing but append its state name to a shared list.
    The returned ``handlers`` dict covers every state in the linear
    sequence so ``run_pipeline`` walks end-to-end without invoking any
    real phase logic.
    """
    from core.state import _LINEAR_SEQUENCE  # noqa: PLC0415

    called: list[str] = []

    def make_stub(state: str) -> Callable[[PipelineContext], None]:
        def stub(ctx: PipelineContext) -> None:
            called.append(state)
        stub.__name__ = f"stub_{state}"
        return stub

    handlers = {state: make_stub(state) for state in _LINEAR_SEQUENCE}
    return handlers, called


# ===========================================================================
# SqliteRunStore — round-trip
# ===========================================================================

def test_store_create_returns_queued_run_with_budgets_and_counters() -> None:
    store = SqliteRunStore()
    run = store.create("https://example.com/repo.git")

    assert run.id.startswith("run_")
    assert len(run.id) == len("run_") + 8
    assert run.repo_url == "https://example.com/repo.git"
    assert run.state == RunState.QUEUED
    # budgets come from config.budgets(); counters are zero-valued.
    assert run.budgets.max_iterations >= 1
    assert run.counters == Counters()


def test_store_get_round_trips_created_run(tmp_path: Path) -> None:
    store = SqliteRunStore(str(tmp_path / "runs.db"))
    created = store.create("https://x/y")

    fetched = store.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.repo_url == created.repo_url
    assert fetched.state == RunState.QUEUED
    assert fetched.budgets.model_dump() == created.budgets.model_dump()
    assert fetched.counters.model_dump() == created.counters.model_dump()


def test_store_get_returns_none_for_unknown_id() -> None:
    store = SqliteRunStore()
    assert store.get("run_doesnotexist") is None


def test_store_list_returns_every_created_run() -> None:
    store = SqliteRunStore()
    a = store.create("https://a/a")
    b = store.create("https://b/b")
    c = store.create("https://c/c")

    ids = {r.id for r in store.list()}
    assert {a.id, b.id, c.id}.issubset(ids)
    # New runs are all QUEUED right after creation.
    assert {r.state for r in store.list()} == {RunState.QUEUED}


def test_store_put_upserts_a_fully_formed_run() -> None:
    store = SqliteRunStore()
    seed = store.create("https://original/url")
    # A replay seeder would build a fully-formed Run and ``put`` it.
    replay_run = Run(
        id=seed.id,
        repo_url="https://replay/url",
        state=RunState.DONE,
        budgets=seed.budgets,
        counters=Counters(
            errors_initial=10,
            errors_current=0,
            fixes_local=4,
            fixes_remote=2,
            fixes_deterministic=4,
            tokens_local=900,
            tokens_remote=1200,
            iterations=6,
        ),
    )
    returned = store.put(replay_run)

    assert returned.id == seed.id
    fetched = store.get(seed.id)
    assert fetched is not None
    assert fetched.repo_url == "https://replay/url"
    assert fetched.state == RunState.DONE
    assert fetched.counters.errors_initial == 10
    assert fetched.counters.fixes_local == 4
    assert fetched.counters.iterations == 6


def test_store_update_state_persists_new_state() -> None:
    store = SqliteRunStore()
    run = store.create("https://x/y")

    store.update_state(run.id, RunState.CLONING)
    assert store.get(run.id).state == RunState.CLONING

    store.update_state(run.id, RunState.DONE)
    assert store.get(run.id).state == RunState.DONE


def test_store_update_state_raises_keyerror_for_unknown_run() -> None:
    store = SqliteRunStore()
    with pytest.raises(KeyError):
        store.update_state("run_ghost0000", RunState.DONE)


def test_store_update_counters_round_trip() -> None:
    store = SqliteRunStore()
    run = store.create("https://x/y")

    new_counters = Counters(
        errors_initial=42,
        errors_current=7,
        fixes_local=3,
        fixes_remote=1,
        fixes_deterministic=5,
        tokens_local=120,
        tokens_remote=340,
        iterations=4,
    )
    store.update_counters(run.id, new_counters)

    fetched = store.get(run.id)
    assert fetched is not None
    assert fetched.counters.model_dump() == new_counters.model_dump()


def test_store_update_counters_raises_keyerror_for_unknown_run() -> None:
    store = SqliteRunStore()
    counters = Counters()
    with pytest.raises(KeyError):
        store.update_counters("run_ghost0000", counters)


def test_store_survives_close(tmp_path: Path) -> None:
    """A persisted file-based store can be closed and re-opened."""
    db_path = str(tmp_path / "runs.db")
    store = SqliteRunStore(db_path)
    run = store.create("https://x/y")
    store.update_state(run.id, RunState.SCANNING)
    store.close()

    store2 = SqliteRunStore(db_path)
    fetched = store2.get(run.id)
    assert fetched is not None
    assert fetched.state == RunState.SCANNING


# ===========================================================================
# SqliteRunStore — satisfies the RunStore protocol
# ===========================================================================

def test_store_satisfies_runstore_protocol_surface() -> None:
    """The store exposes the four RunStore methods with the right signatures.

    ``app.store.RunStore`` is a ``typing.Protocol`` (not
    ``@runtime_checkable``), so we verify the surface structurally:
    each method must exist, be callable, and accept the documented
    positional/keyword shape.
    """
    store = SqliteRunStore()
    for name, expected_param in (
        ("create", "repo_url"),
        ("get", "run_id"),
        ("list", None),
        ("put", "run"),
    ):
        method = getattr(store, name, None)
        assert callable(method), f"store.{name} must be callable"
        sig = inspect.signature(method)
        if expected_param is None:
            # ``list`` takes no args.
            assert len(sig.parameters) == 0
        else:
            assert expected_param in sig.parameters, (
                f"store.{name} must accept {expected_param!r}; "
                f"got parameters {list(sig.parameters)}"
            )

    # A round-trip call to each must succeed without raising.
    created = store.create("https://x/y")
    assert store.get(created.id) == created
    assert created in store.list()
    store.put(created)  # idempotent upsert


# ===========================================================================
# run_pipeline — the FSM driver
# ===========================================================================

def test_run_pipeline_walks_full_sequence_with_stub_handlers(
    tmp_path: Path,
) -> None:
    """Stub handlers → one ``phase`` event per transition, in order.

    Asserts the full happy-path sequence
    ``QUEUED → CLONING → SCANNING → PORTING → BUILD_LOOP → RUNNING →
    PARITY → REPORTING → DONE``: nine phase events in the trace, and
    the stub handler map fires once per state.
    """
    store = SqliteRunStore()
    config = _make_config()
    run = store.create("https://example.com/repo.git")
    trace, trace_path = _trace(tmp_path, run.id)
    handlers, called = _stub_recorder()

    final = run_pipeline(run.id, store, config, trace, handlers=handlers)

    assert final.state == RunState.DONE
    # The store mirrors the final state.
    assert store.get(run.id).state == RunState.DONE

    # The handler map fired exactly once per state, in order.
    assert called == [
        "QUEUED",
        "CLONING",
        "SCANNING",
        "PORTING",
        "BUILD_LOOP",
        "RUNNING",
        "PARITY",
        "REPORTING",
        "DONE",
    ]

    # The trace has ONE ``phase`` event per transition, in the same order.
    events = read_events(trace_path)
    phase_events = [e for e in events if e["ev"] == "phase"]
    assert [e["phase"] for e in phase_events] == [
        "QUEUED",
        "CLONING",
        "SCANNING",
        "PORTING",
        "BUILD_LOOP",
        "RUNNING",
        "PARITY",
        "REPORTING",
        "DONE",
    ]


def test_run_pipeline_emits_phase_event_before_handler_inv4(
    tmp_path: Path,
) -> None:
    """INV-4: the phase event is on disk BEFORE the handler runs.

    Strategy: make a ``SCANNING`` handler that, at the moment it is
    invoked, re-reads the trace and asserts the SCANNING phase event is
    already the last entry. Then it raises. The test then verifies the
    FAILED path (see next test) — here we only care about INV-4.
    """
    store = SqliteRunStore()
    config = _make_config()
    run = store.create("https://x/y")
    trace, trace_path = _trace(tmp_path, run.id)

    seen_at_handler: list[dict] = []

    def scanning_handler(ctx: PipelineContext) -> None:
        # Read the trace as it stands RIGHT NOW (the driver has
        # already emitted the SCANNING phase event for us).
        seen_at_handler.extend(read_events(trace_path))

    handlers, _ = _stub_recorder()
    handlers[RunState.SCANNING] = scanning_handler

    run_pipeline(run.id, store, config, trace, handlers=handlers)

    assert seen_at_handler, "SCANNING handler was never invoked"
    last = seen_at_handler[-1]
    assert last["ev"] == "phase", (
        f"INV-4 violated: last trace event at handler entry was "
        f"{last.get('ev')!r}, expected 'phase'"
    )
    assert last["phase"] == RunState.SCANNING, (
        f"INV-4 violated: phase at handler entry was "
        f"{last.get('phase')!r}, expected 'SCANNING'"
    )


def test_run_pipeline_handler_exception_yields_failed_state_inv5(
    tmp_path: Path,
) -> None:
    """INV-5: a handler exception ends the run in ``FAILED`` and does
    NOT propagate. The run is persisted with that state, and the trace
    has both the FAILED phase event and a ``failed`` event with the
    exception class + message.
    """
    store = SqliteRunStore()
    config = _make_config()
    run = store.create("https://x/y")
    trace, trace_path = _trace(tmp_path, run.id)

    boom_msg = "synthetic handler failure for INV-5"

    def porting_bomb(ctx: PipelineContext) -> None:
        raise RuntimeError(boom_msg)

    handlers, _ = _stub_recorder()
    handlers[RunState.PORTING] = porting_bomb

    # The exception must NOT propagate: the call returns normally.
    final = run_pipeline(run.id, store, config, trace, handlers=handlers)

    assert final.state == RunState.FAILED
    # The store mirrors the final state.
    assert store.get(run.id).state == RunState.FAILED

    # The trace records the reason.
    events = read_events(trace_path)
    failed_events = [e for e in events if e["ev"] == "failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["reason"] == boom_msg
    assert failed_events[0]["exc_type"] == "RuntimeError"

    # The FAILED phase event comes BEFORE the failed-event in the trace
    # (INV-4: trace event before act, even for the FAILED transition).
    phases = [e for e in events if e["ev"] == "phase"]
    assert phases[-1]["phase"] == RunState.FAILED
    failed_idx = next(i for i, e in enumerate(events) if e["ev"] == "failed")
    failed_phase_idx = max(
        i for i, e in enumerate(events) if e["ev"] == "phase" and e["phase"] == "FAILED"
    )
    assert failed_phase_idx < failed_idx, (
        "FAILED phase event must precede the failed-event in the trace"
    )

    # Handlers for states AFTER the failing one (BUILD_LOOP, RUNNING,
    # PARITY, REPORTING, DONE) are NEVER invoked — the driver bails
    # out on the first exception.
    called = [
        e["phase"] for e in phases
        if e["phase"] in {
            RunState.BUILD_LOOP, RunState.RUNNING,
            RunState.PARITY, RunState.REPORTING, RunState.DONE,
        }
    ]
    assert called == [], (
        f"no post-FAIL handlers should fire, but got phase events: {called}"
    )


def test_run_pipeline_handler_exception_before_phase_event_in_trace_inv4(
    tmp_path: Path,
) -> None:
    """Stricter INV-4 check: even when the handler raises, its OWN
    phase event was already emitted before the exception. We compare
    the position of the failing state's phase event to the position of
    the ``failed`` event.
    """
    store = SqliteRunStore()
    config = _make_config()
    run = store.create("https://x/y")
    trace, trace_path = _trace(tmp_path, run.id)

    def cloning_bomb(ctx: PipelineContext) -> None:
        raise ValueError("clone blew up")

    handlers, _ = _stub_recorder()
    handlers[RunState.CLONING] = cloning_bomb

    final = run_pipeline(run.id, store, config, trace, handlers=handlers)
    assert final.state == RunState.FAILED

    events = read_events(trace_path)
    # The CLONING phase event MUST precede the failed event.
    cloning_idx = next(
        i for i, e in enumerate(events)
        if e["ev"] == "phase" and e["phase"] == RunState.CLONING
    )
    failed_idx = next(
        i for i, e in enumerate(events) if e["ev"] == "failed"
    )
    assert cloning_idx < failed_idx, (
        f"INV-4 violated: CLONING phase event at {cloning_idx} should "
        f"come BEFORE failed-event at {failed_idx}"
    )


def test_run_pipeline_unknown_run_raises_keyerror(tmp_path: Path) -> None:
    store = SqliteRunStore()
    config = _make_config()
    trace, _ = _trace(tmp_path, "run_nope")
    with pytest.raises(KeyError):
        run_pipeline("run_nope", store, config, trace)


# ===========================================================================
# default_handlers — the explicit override seam
# ===========================================================================

def test_default_handlers_covers_known_phases() -> None:
    """Every state that has a real implementation OR a stub is in the map.

    ``QUEUED`` and ``DONE`` are not in the map by design: they are the
    initial and final states, with no handler. The driver handles them
    as "no handler" (skip the call) while still emitting their phase
    event and persisting the state.
    """
    config = _make_config()
    handlers = default_handlers(config)

    # Real implementations wired for the phases that exist.
    for state in (RunState.CLONING, RunState.SCANNING, RunState.PORTING):
        assert state in handlers, f"default_handlers missing {state}"

    # STUBs for the phases still to be implemented (T14 / T15 / T16).
    for state in (
        RunState.BUILD_LOOP, RunState.RUNNING,
        RunState.PARITY, RunState.REPORTING,
    ):
        assert state in handlers, f"default_handlers missing stub for {state}"

    # ``QUEUED`` and ``DONE`` deliberately absent — no handler, no work.
    assert RunState.QUEUED not in handlers
    assert RunState.DONE not in handlers


def test_default_handlers_overrides_replace_defaults() -> None:
    """The ``overrides`` seam lets callers inject the real impls (T14+)
    or test mocks without forking the function."""
    config = _make_config()
    sentinel = object()

    def custom_build_loop(ctx: PipelineContext) -> None:
        ctx.trace.emit("custom", marker=sentinel)

    handlers = default_handlers(
        config, overrides={RunState.BUILD_LOOP: custom_build_loop}
    )
    assert handlers[RunState.BUILD_LOOP] is custom_build_loop

    # Other states are unaffected.
    assert handlers[RunState.CLONING] is not custom_build_loop


# ===========================================================================
# Integration — real SCANNING handler on the scan_repo fixture
# ===========================================================================

def test_run_pipeline_real_scanning_handler_pouplates_scan_result(
    tmp_path: Path,
) -> None:
    """Lightweight end-to-end: the real ``SCANNING`` handler runs against
    the existing ``tests/fixtures/scan_repo`` directory and populates
    ``ctx.scan_result``. PORTING is not exercised (it needs a real git
    repo); we override it with a no-op stub so the run walks
    ``SCANNING → PORTING (no-op) → ... → DONE``.
    """
    store = SqliteRunStore()
    config = _make_config()
    run = store.create("https://example.com/scan_repo.git")
    trace, trace_path = _trace(tmp_path, run.id)

    # Use default_handlers for the real SCANNING + a no-op for the
    # phases after it (we don't want to actually port/build the fixture
    # in this test — we just need to see SCANNING fill the context).
    captured: list[ScanResult] = []

    def capturing_scanning(ctx: PipelineContext) -> None:
        # Wrap the real SCANNING implementation so we can capture the
        # resulting ScanResult for the test to assert on.
        result = scan_phase.scan(ctx.repo_dir)
        ctx.scan_result = result
        captured.append(result)
        ctx.trace.emit(
            "scan.done",
            files_cuda=len(result.files_cuda),
            loc_kernels=result.loc_kernels,
            difficulty=result.difficulty,
            build_system=result.build_system,
            wave64_total=len(result.wave64_findings),
        )

    # The CLONING handler would try to git-clone in real mode. In
    # mock/test mode (a real ``repo_dir`` already on disk) it emits
    # ``cloning.skipped`` and does nothing — so we can use the real
    # CLONING handler. PORTING needs a real git repo + a scan_result,
    # so we override it with a no-op.
    handlers = default_handlers(
        config,
        overrides={
            RunState.SCANNING: capturing_scanning,
            RunState.PORTING: lambda ctx: None,
        },
    )

    final = run_pipeline(
        run.id, store, config, trace,
        handlers=handlers,
        repo_dir=str(FIXTURE_DIR),
    )

    assert final.state == RunState.DONE
    assert len(captured) == 1, "SCANNING handler should have been called exactly once"

    scan_result = captured[0]
    assert isinstance(scan_result, ScanResult)
    # The fixture ships with ``kernel.cu`` and ``aux.cuh``.
    assert "kernel.cu" in scan_result.files_cuda
    assert "aux.cuh" in scan_result.files_cuda
    # wave64 linting catches the ``__ballot_sync(0xffffffff,...)`` in
    # the fixture (W01 and/or W02).
    assert any(
        f.pattern_id in {"W01", "W02"} for f in scan_result.wave64_findings
    ), "fixture should trigger at least one wave64 finding"

    # The trace records the SCANNING transition + scan.done.
    events = read_events(trace_path)
    scan_done = [e for e in events if e["ev"] == "scan.done"]
    assert len(scan_done) == 1
    assert scan_done[0]["build_system"] == "make"


# ===========================================================================
# AD-3 defence in depth — state.py does not import app
# ===========================================================================

def test_state_module_does_not_import_app() -> None:
    """AD-3: ``core.state`` is the unique driver; the FSM does NOT
    depend on the HTTP layer. ``app → core.state``, never the reverse.
    """
    import app  # noqa: F401 — sentinel; the real check is on core.state

    forbidden = {"app"}
    bad: list[str] = []
    for module_name in list(sys.modules):
        if not module_name.startswith("core") and module_name != "core.state":
            continue
        mod = sys.modules.get(module_name)
        if mod is None:
            continue
        src_file = getattr(mod, "__file__", "") or ""
        if not src_file.endswith("state.py"):
            continue
        # Only the state.py file under core/ is the subject of this test.
        for name in dir(mod):
            if name.startswith("__"):
                continue
            obj = getattr(mod, name, None)
            owner = getattr(obj, "__module__", "") or ""
            assert not owner.startswith("app"), (
                f"core.state.{name} is bound to {owner!r} — "
                f"state.py must not import from app (AD-3)"
            )


def test_state_module_top_level_imports_have_no_app_dependency() -> None:
    """Static check: scan the source of ``core.state`` for any
    ``import app`` / ``from app`` statement. This is the early-warning
    test for AD-3 violations — the runtime check above depends on the
    module having been imported already.
    """
    import ast  # noqa: PLC0415

    source = inspect.getsource(state_module)
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app" or alias.name.startswith("app."):
                    bad.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "app" or module.startswith("app."):
                bad.append(f"from {module} import ...")
    assert bad == [], (
        "core/state.py must not import from app (AD-3): "
        f"found {bad}"
    )
