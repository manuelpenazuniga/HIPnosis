"""core/phases/build_loop.py — wiring real de BUILD_LOOP + integracion de pipeline.

Capa L4. UNICO modulo donde se juntan taxonomy+llm+patcher (T14a los dejo
inyectables a proposito). Cablea las funciones REALES al run_build_loop y
lo enchufa al driver de fases (T8) para correr el pipeline COMPLETO en mock.

Dos caminos de aplicacion (por eso classify da la estrategia):
  * deterministic (E01/E02): sustitucion GLOBAL via regex, NO por patcher.
  * LLM (E05/E04/etc.): SEARCH/REPLACE via core.patcher (unicidad dura).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Optional

from core.config import Config
from core.errparse import group as err_group
from core.errparse import parse as err_parse
from core.gitrepo import GitRepo
from core.llm.prompts import render_fixer
from core.llm.router import client_for_tier, decide_tier as _decide_tier
from core.oracle.base import Oracle
from core.patcher import PatchStatus, apply_patch
from core.phases.loop import (
    ApplyFn,
    ClassifyFn,
    LoopResult,
    ProposeFixFn,
    run_build_loop,
)
from core.schemas import Counters, ErrorGroup, Run, RunState
from core.state import PipelineContext, SqliteRunStore, run_pipeline
from core.taxonomy import classify as _classify
from core.taxonomy import deterministic_fix, load_rules
from core.trace import TraceWriter


# ---------------------------------------------------------------------------
# Deterministic fix helpers
# ---------------------------------------------------------------------------

_SED_RE = re.compile(r"^s(.)(.+)\1(.*)\1$")


def _parse_deterministic_template(fix_template: str) -> tuple[str, str]:
    """Parse ``s|pattern|replacement|`` into (pattern_str, replacement_str)."""
    m = _SED_RE.match(fix_template)
    if not m:
        raise ValueError(
            f"Cannot parse deterministic fix template: {fix_template!r}"
        )
    return m.group(2), m.group(3)


def _apply_deterministic_fix(
    fix_template: str,
    group: ErrorGroup,
    workspace_root: str,
) -> int:
    """Apply a deterministic fix globally on all affected files.

    Parses the sed-like ``fix_template`` (from ``deterministic_fix``),
    collects unique source files from the error group, applies a global
    ``re.sub`` on each, and returns how many files were modified.
    """
    pattern_str, replacement_str = _parse_deterministic_template(fix_template)
    pattern = re.compile(pattern_str)

    files: set[str] = set()
    for e in group.errors:
        if e.file and e.file != "<link>":
            files.add(e.file)

    touched = 0
    for fname in sorted(files):
        fpath = Path(workspace_root) / fname
        if not fpath.is_file():
            continue
        content = fpath.read_text(encoding="utf-8")
        new_content = pattern.sub(replacement_str, content)
        if new_content != content:
            fpath.write_text(new_content, encoding="utf-8", newline="\n")
            touched += 1

    return touched


# ---------------------------------------------------------------------------
# make_loop_functions — el wiring real de las 4 funciones inyectables
# ---------------------------------------------------------------------------


def make_loop_functions(
    ctx: PipelineContext,
    oracle: Oracle,
    rules: list,
) -> tuple[ClassifyFn, Callable, ProposeFixFn, ApplyFn]:
    """Build the four injected functions for ``run_build_loop``.

    Closure shares mutable ``_strategy`` so that ``propose_fix_fn`` and
    ``apply_fn`` know whether the current group follows the deterministic
    or LLM path without changing the loop's contract (INV-1).
    """
    _strategy: str = "llm"
    _group: ErrorGroup | None = None
    _klass: str = "E99"

    def classify_fn(g: ErrorGroup) -> str:
        nonlocal _group, _klass
        _group = g
        _klass = _classify(g, rules)
        return _klass

    def decide_tier_fn(
        strategy: str,
        attempts: int,
        tier_sugerido: str | None,
    ) -> str:
        nonlocal _strategy
        _strategy = strategy
        return _decide_tier(strategy, attempts, tier_sugerido)

    def propose_fix_fn(
        g: ErrorGroup,
        tier: str,
        attempts: int,
    ) -> str:
        if _strategy == "deterministic":
            klass = _klass or _classify(g, rules)
            fix = deterministic_fix(klass, g)
            return fix or ""

        if tier == "deterministic":
            return ""

        try:
            client = client_for_tier(tier, ctx.config)
        except ValueError:
            return ""

        error_msgs = [e.message for e in g.errors[:5]]
        first = g.errors[0]
        file_path = first.file or ""
        code_window = ""
        a, b, total = 1, 1, 1
        try:
            fpath = Path(ctx.repo_dir) / file_path
            if fpath.is_file():
                lines = fpath.read_text(encoding="utf-8").splitlines()
                total = len(lines)
                a = max(1, first.line - 5)
                b = min(total, first.line + 5)
                code_window = "\n".join(
                    f"{i + 1}: {ln}"
                    for i, ln in enumerate(lines[a - 1 : b], start=a - 1)
                )
        except OSError:
            pass

        history = ""
        if attempts > 0:
            history = f"(Intento {attempts + 1} de {ctx.config.max_attempts_per_group})"

        class_notes = ""
        rule = next((r for r in rules if r.id == _klass), None)
        if rule is not None:
            class_notes = rule.notes

        try:
            system, user = render_fixer(
                error_msgs=error_msgs,
                path=file_path,
                code_window=code_window,
                a=a,
                b=b,
                total=total,
                class_notes=class_notes,
                history=history,
            )
            resp = client.complete(system, user)
            return resp.text
        except Exception:
            return ""

    def apply_fn(patch: str, msg: str) -> int:
        if _strategy == "deterministic":
            if not patch or not _group:
                return 1
            touched = _apply_deterministic_fix(
                patch, _group, ctx.repo_dir
            )
            try:
                repo = GitRepo(ctx.repo_dir)
                repo.commit_all(msg)
            except Exception:
                pass
            build_result = oracle.build()
            return -1 if touched > 0 else 0

        if not patch:
            return 1

        try:
            repo = GitRepo(ctx.repo_dir)
        except Exception:
            return 1

        result = apply_patch(patch, repo, msg, ctx.trace)
        if result.status != PatchStatus.APPLIED:
            return 1

        build_result = oracle.build()
        return -1

    return classify_fn, decide_tier_fn, propose_fix_fn, apply_fn


# ---------------------------------------------------------------------------
# build_loop_handler — el handler de fase para el driver de state (T8)
# ---------------------------------------------------------------------------


def build_loop_handler(ctx: PipelineContext) -> None:
    """Phase handler for BUILD_LOOP in the FSM driver.

    Reads the oracle from ``ctx._oracle`` (injected by the caller, e.g.
    ``run_full_pipeline_mock``). If absent, emits a stub event and returns
    (real oracle not implemented yet — T15).

    Builds the loop functions via ``make_loop_functions``, runs the build
    loop, and persists counters into the store so REPORTING can use them.
    """
    oracle: Oracle | None = getattr(ctx, "oracle", None)
    if oracle is None:
        ctx.trace.emit("phase.stub", phase=RunState.BUILD_LOOP)
        return

    rules = load_rules()
    classify_fn, decide_tier_fn, propose_fix_fn, apply_fn = make_loop_functions(
        ctx, oracle, rules
    )
    result: LoopResult = run_build_loop(
        oracle=oracle,
        cfg=ctx.config,
        trace=ctx.trace,
        classify_fn=classify_fn,
        decide_tier_fn=decide_tier_fn,
        propose_fix_fn=propose_fix_fn,
        apply_fn=apply_fn,
    )
    ctx.store.update_counters(ctx.run.id, result.counters)
    ctx.trace.emit(
        "build_loop.done",
        success=result.success,
        final_errors=result.final_errors,
        iterations=result.iterations,
        needs_human=result.needs_human,
    )


# ---------------------------------------------------------------------------
# run_full_pipeline_mock — integracion completa en mock (M2 acceptance)
# ---------------------------------------------------------------------------


def run_full_pipeline_mock(
    run_id: str,
    store: SqliteRunStore,
    config: Config,
    trace: TraceWriter,
    fixtures_dir: str,
    repo_dir: str,
) -> Run:
    """Run the complete pipeline QUEUED...DONE in mock mode.

    Creates a ``MockOracle`` on ``fixtures_dir``, injects it into the
    pipeline context via a wrapper handler for ``BUILD_LOOP``, and calls
    ``core.state.run_pipeline`` with the override. Returns the final
    ``Run`` (state DONE or FAILED).
    """
    from core.oracle.mock import MockOracle  # noqa: PLC0415
    from core.state import default_handlers  # noqa: PLC0415

    mock_oracle = MockOracle(fixtures_dir)

    def handler_with_oracle(inner_ctx: PipelineContext) -> None:
        inner_ctx.oracle = mock_oracle
        build_loop_handler(inner_ctx)

    return run_pipeline(
        run_id=run_id,
        store=store,
        config=config,
        trace=trace,
        handlers=default_handlers(
            config,
            overrides={RunState.BUILD_LOOP: handler_with_oracle},
        ),
        repo_dir=repo_dir,
    )
