"""core/phases/loop.py — build-fix control loop (L4, §6.4).

Deterministic state machine. The three "content" operations (classify,
propose fix, apply) are INJECTED — the loop NEVER imports them directly
(INV-1: LLM decides content; the orchestrator decides control).

The loop consults `core.rules.yaml` as a data file (strategy/tier lookup),
NOT via `core.taxonomy` — the taxonomy classifier is one of the injected
content functions.

Layering: L4. Imports `core.schemas`, `core.config`, `core.errparse`,
`core.trace`, plus the oracle type contract. No reference to `core.llm`,
`core.patcher` or `core.taxonomy`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yaml

from core.config import Config
from core.errparse import group as err_group
from core.errparse import parse as err_parse
from core.schemas import Counters, ErrorGroup
from core.trace import TraceWriter


# --- Injection types ---

ClassifyFn = Callable[[ErrorGroup], str]
"""Grupo -> clase 'E05'. Inyectada (INV-1)."""

ProposeFixFn = Callable[[ErrorGroup, str, int], str]
"""(group, tier, attempts) -> patch text ('' si no puede proponer)."""

ApplyFn = Callable[[str, str], int]
"""(patch, commit_msg) -> build error delta. <=0 mejora, >0 empeora."""


@dataclass
class LoopResult:
    """Resultado del build-fix loop (§6.4)."""
    success: bool
    final_errors: int
    iterations: int
    needs_human: list[str]       # signatures no resueltas
    counters: Counters


# ---------------------------------------------------------------------------
# Rule metadata lookup — carga rules.yaml como DATA, sin pasar por taxonomy
# ---------------------------------------------------------------------------

def _load_rule_info() -> dict[str, tuple[str, str | None]]:
    """Load ``{class_id: (strategy, tier_sugerido)}`` from rules.yaml."""
    rules_path = Path(__file__).resolve().parent.parent / "rules.yaml"
    with open(rules_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return {
        entry["id"]: (entry["strategy"], entry.get("tier"))
        for entry in raw
    }


_RULE_INFO: dict[str, tuple[str, str | None]] = _load_rule_info()


# ---------------------------------------------------------------------------
# F-06: anti-oscillation detection
# ---------------------------------------------------------------------------

def _detect_oscillating(
    history: list[set[str]],
    current: set[str],
) -> set[str]:
    """Return signatures that have disappeared and reappeared >= 2 times.

    F-06 (blueprint §6.4): a signature that vanishes, comes back, vanishes
    again, and comes back again is almost certainly a false positive — the
    loop is undoing its own progress. These groups must be escalated to
    remote tier.

    ``history`` is a list of signature-sets, one per iteration, in order.
    ``current`` is the set for the CURRENT iteration (already appended).
    """
    if len(history) < 3:
        return set()

    all_sigs: set[str] = set()
    for s in history:
        all_sigs |= s

    oscillating: set[str] = set()
    for sig in all_sigs:
        presence = [sig in s for s in history]
        reappearances = sum(
            1 for i in range(1, len(presence))
            if not presence[i - 1] and presence[i]
        )
        if reappearances >= 2 and sig in current:
            oscillating.add(sig)
    return oscillating


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_build_loop(
    oracle,
    cfg: Config,
    trace: TraceWriter,
    classify_fn: ClassifyFn,
    decide_tier_fn: Callable[[str, int, str | None], str],
    propose_fix_fn: ProposeFixFn,
    apply_fn: ApplyFn,
) -> LoopResult:
    """Execute the build-fix loop (§6.4).

    INV-10: ``cfg.max_iterations`` and ``cfg.max_attempts_per_group`` are
    HARD caps (no infinite loop).
    INV-1: ``classify_fn`` / ``propose_fix_fn`` / ``apply_fn`` are injected
    (the loop NEVER decides content).
    INV-4: every ``build`` and ``fix`` event is emitted to the trace
    BEFORE the next step.
    F-06: oscillating signatures are detected and force-escalated to remote.
    """
    counters = Counters()
    iteration = 0
    signature_history: list[set[str]] = []
    no_progress = 0
    prev_errors: Optional[int] = None
    needs_human: list[str] = []
    persistent_groups: dict[str, ErrorGroup] = {}

    while iteration < cfg.max_iterations:
        # --- BUILD ---
        result = oracle.build()

        if counters.errors_initial == 0:
            counters.errors_initial = result.count

        delta_build = result.count - prev_errors if prev_errors is not None else 0
        trace.emit("build", iteration=iteration, errors=result.count,
                   delta=delta_build)

        # --- GREEN? ---
        if result.count == 0:
            counters.errors_current = 0
            counters.iterations = iteration
            return LoopResult(
                success=True,
                final_errors=0,
                iterations=iteration,
                needs_human=needs_human,
                counters=counters,
            )

        # --- PARSE + GROUP ---
        errors = err_parse(result.raw_output, cfg.max_errors_parsed)
        groups = err_group(errors)

        # Persist group state across iterations
        for g in groups:
            prev = persistent_groups.get(g.signature)
            if prev is not None:
                g.attempts = prev.attempts
                g.status = prev.status
            persistent_groups[g.signature] = g

        cur_sigs = {g.signature for g in groups}
        signature_history.append(cur_sigs)

        # F-06: detect oscillating signatures
        oscillating = _detect_oscillating(signature_history, cur_sigs)

        # --- PROGRESS ---
        if prev_errors is not None and result.count >= prev_errors:
            no_progress += 1
        else:
            no_progress = 0

        # INV-10: 5 consecutive non-improving builds → honest exit
        if no_progress >= 5:
            counters.errors_current = result.count
            counters.iterations = iteration
            for g in groups:
                needs_human.append(g.signature)
            return LoopResult(
                success=False,
                final_errors=result.count,
                iterations=iteration,
                needs_human=needs_human,
                counters=counters,
            )

        # --- SELECT TARGET ---
        open_groups = [
            g for g in groups
            if g.status == "open" and g.attempts < cfg.max_attempts_per_group
        ]
        if not open_groups:
            counters.errors_current = result.count
            counters.iterations = iteration
            for g in groups:
                if g.attempts >= cfg.max_attempts_per_group:
                    needs_human.append(g.signature)
            return LoopResult(
                success=False,
                final_errors=result.count,
                iterations=iteration,
                needs_human=needs_human,
                counters=counters,
            )

        g = max(open_groups, key=lambda x: len(x.errors))

        # --- CLASSIFY + DECIDE TIER ---
        klass = classify_fn(g)
        strategy, tier_sugerido = _RULE_INFO.get(
            klass, ("llm", "local_then_remote")
        )
        tier = decide_tier_fn(strategy, g.attempts, tier_sugerido)

        # F-06 force remote for oscillating signatures
        if g.signature in oscillating:
            tier = "remote"

        # §6.4: force remote after 3 consecutive non-improving builds
        if no_progress >= 3:
            tier = "remote"

        # --- FIX ---
        patch = propose_fix_fn(g, tier, g.attempts)
        delta = apply_fn(patch, f"fix({klass}): iter {iteration} [tier={tier}]")
        applied = delta <= 0 and patch != ""

        trace.emit(
            "fix",
            sig=g.signature,
            klass=klass,
            tier=tier,
            applied=applied,
            delta=delta,
            attempt=g.attempts,
            iteration=iteration,
        )

        # --- UPDATE STATE ---
        if delta > 0:
            g.attempts += 1
        else:
            if tier == "deterministic":
                counters.fixes_deterministic += 1
            elif tier == "local":
                counters.fixes_local += 1
            elif tier == "remote":
                counters.fixes_remote += 1

        prev_errors = result.count
        iteration += 1

    # INV-10: exhausted max_iterations (hard cap)
    counters.errors_current = prev_errors or 0
    counters.iterations = iteration
    return LoopResult(
        success=False,
        final_errors=counters.errors_current,
        iterations=iteration,
        needs_human=needs_human,
        counters=counters,
    )
