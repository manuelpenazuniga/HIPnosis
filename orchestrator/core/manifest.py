"""core/manifest.py — primitive (L2): per-repo manifest loader + drafter.

Reads ``hipnosis.yaml`` (blueprint §7.1) and turns it into a typed
:class:`Manifest` that VERIFY consumes. The manifest is the contract that
makes the product general: it says HOW to build, HOW to run, and HOW to
verify a given repo without hard-coding the commands anywhere in core.

The manifest is DATA — this module parses, validates and produces a typed
object. It does NOT execute anything; ``phases.verify`` (a later task)
will read the spec and dispatch the run. That separation is enforced
both by the docstring and by the import surface (L2 primitive, no
``phases``/``oracle``/``llm``/``state`` dependencies).

Layering: L2 primitive. Imports only stdlib, ``pyyaml`` and
``core.schemas`` (for the :class:`ScanResult` consumed by
``draft_manifest``). Does NOT import ``phases``, ``oracle``, ``llm`` or
``state``.

Validation is fail-closed: a missing required field or an unknown
``verify.mode`` raises :class:`ValueError` with a clear message. The
build loop depends on this — a silently accepted malformed manifest
would later produce a confusing verify failure rather than a precise
config error at load time.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from core.schemas import ScanResult


# ---------------------------------------------------------------------------
# Typed schema
# ---------------------------------------------------------------------------

# Allowed ``verify.mode`` values. ``"none"`` is the honest "I have no
# oracle" verdict (F-07/F-08 outside the demo set) — never an error.
_VERIFY_MODES: frozenset[str] = frozenset({"self_check", "golden_output", "none"})


@dataclass
class BuildSpec:
    cmd: str
    dir: str = "."


@dataclass
class RunSpec:
    cmd: str
    timeout_s: int = 120


@dataclass
class VerifySpec:
    mode: str
    pass_regex: str | None = None
    golden_file: str | None = None
    numeric_rtol: float = 1e-5
    numeric_atol: float = 1e-8


@dataclass
class Manifest:
    build: BuildSpec
    run: RunSpec
    verify: VerifySpec
    timing_regex: str | None = None
    # raw, original text of the file — kept for round-tripping / debugging.
    source: str | None = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_str(payload: dict[str, Any], key: str, where: str) -> str:
    """Pull a non-empty string out of ``payload`` or raise ``ValueError``."""
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"hipnosis.yaml: {where}.{key} is required and must be a non-empty string"
        )
    return value


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"hipnosis.yaml: {key} must be a string when present (got {type(value).__name__})"
        )
    return value


def _optional_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"hipnosis.yaml: {key} must be an integer (got {type(value).__name__})"
        )
    return value


def _optional_float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"hipnosis.yaml: {key} must be a number (got {type(value).__name__})"
        )
    return float(value)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _parse_build(payload: Any) -> BuildSpec:
    if not isinstance(payload, dict):
        raise ValueError("hipnosis.yaml: 'build' must be a mapping")
    cmd = _require_str(payload, "cmd", "build")
    build_dir = payload.get("dir", ".")
    if not isinstance(build_dir, str) or not build_dir:
        raise ValueError("hipnosis.yaml: build.dir must be a non-empty string when present")
    return BuildSpec(cmd=cmd, dir=build_dir)


def _parse_run(payload: Any) -> RunSpec:
    if not isinstance(payload, dict):
        raise ValueError("hipnosis.yaml: 'run' must be a mapping")
    cmd = _require_str(payload, "cmd", "run")
    return RunSpec(cmd=cmd, timeout_s=_optional_int(payload, "timeout_s", 120))


def _parse_verify(payload: Any) -> VerifySpec:
    if not isinstance(payload, dict):
        raise ValueError("hipnosis.yaml: 'verify' must be a mapping")
    mode = payload.get("mode")
    if not isinstance(mode, str) or mode not in _VERIFY_MODES:
        allowed = ", ".join(sorted(_VERIFY_MODES))
        raise ValueError(
            f"hipnosis.yaml: verify.mode must be one of {{{allowed}}} (got {mode!r})"
        )
    pass_regex = _optional_str(payload, "pass_regex")
    golden_file = _optional_str(payload, "golden_file")
    if mode == "self_check" and not pass_regex:
        raise ValueError(
            "hipnosis.yaml: verify.pass_regex is required when verify.mode='self_check'"
        )
    if mode == "golden_output" and not golden_file:
        raise ValueError(
            "hipnosis.yaml: verify.golden_file is required when verify.mode='golden_output'"
        )
    return VerifySpec(
        mode=mode,
        pass_regex=pass_regex,
        golden_file=golden_file,
        numeric_rtol=_optional_float(payload, "numeric_rtol", 1e-5),
        numeric_atol=_optional_float(payload, "numeric_atol", 1e-8),
    )


def load_manifest(path: str) -> Manifest:
    """Load and validate ``hipnosis.yaml`` from ``path``.

    Fail-closed: any structural problem (missing ``build.cmd`` /
    ``run.cmd``, unknown ``verify.mode``, missing ``pass_regex`` for
    ``self_check`` or missing ``golden_file`` for ``golden_output``)
    raises :class:`ValueError` with a precise message that names the
    offending key.
    """
    if not os.path.isfile(path):
        raise ValueError(f"hipnosis.yaml not found at {path}")
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"hipnosis.yaml: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("hipnosis.yaml: top-level must be a mapping")

    if "build" not in data:
        raise ValueError("hipnosis.yaml: 'build' section is required")
    if "run" not in data:
        raise ValueError("hipnosis.yaml: 'run' section is required")
    if "verify" not in data:
        raise ValueError("hipnosis.yaml: 'verify' section is required")

    build = _parse_build(data["build"])
    run = _parse_run(data["run"])
    verify = _parse_verify(data["verify"])
    timing_regex = _optional_str(data, "timing_regex")
    if timing_regex is not None:
        # Sanity: ``timing_regex`` must contain a capture group, since
        # the verifier extracts the timing value from group(1). We do
        # not validate the rest of the regex (the user owns the
        # dialect) — just the structural contract.
        try:
            re.compile(timing_regex)
        except re.error as exc:
            raise ValueError(f"hipnosis.yaml: timing_regex is not a valid regex: {exc}") from exc
        if "(" not in timing_regex:
            raise ValueError(
                "hipnosis.yaml: timing_regex must contain a capture group (group 1) for the timing value"
            )

    return Manifest(
        build=build,
        run=run,
        verify=verify,
        timing_regex=timing_regex,
        source=raw,
    )


# ---------------------------------------------------------------------------
# Drafter (used by SCAN to seed a hand-edited manifest)
# ---------------------------------------------------------------------------

_DEFAULT_HEURISTIC_BUILD_CMDS = (
    "make -f Makefile",
    "make",
)
_DEFAULT_HEURISTIC_RUN_CMDS = (
    "./main",
    "make run",
)
_DEFAULT_PASS_REGEX = "PASS"
_DEFAULT_TIMEOUT_S = 120


def _detect_cmd(candidates: tuple[str, ...], files: list[str], makefile_text: str | None) -> str | None:
    """Return the first candidate that is plausible for this repo, or None.

    Mirrors the SCAN heuristic: a real ``Makefile`` target first, then a
    known binary. We only DO detection — the actual on-disk check
    belongs to verify.py (different task), so we keep this signature
    pure-ish by also accepting the already-scanned file list.
    """
    for cmd in candidates:
        head = cmd.split()[0]
        if head.startswith("./") and head[2:] in files:
            return cmd
    if makefile_text is not None:
        for target in ("run", "test", "bench"):
            if re.search(rf"^{re.escape(target)}\s*:", makefile_text, flags=re.MULTILINE):
                return f"make {target}"
    return None


def draft_manifest(scan_result: ScanResult, repo_dir: str) -> Manifest:
    """Return a best-effort :class:`Manifest` from a :class:`ScanResult`.

    Heuristic — NOT a substitute for a hand-curated manifest on demo
    repos (F-07, §7.1). Defaults:

    * ``build`` → ``make -f Makefile`` in ``"."`` (will be edited to
      the actual subdir by the operator).
    * ``run``   → ``./main`` with 120 s timeout.
    * ``verify`` → ``self_check`` with ``pass_regex="PASS"`` (the
      HeCBench convention; the most common self-check dialect in the
      corpus).
    * ``timing_regex`` → ``None`` (timing is optional; if absent the
      verify phase still reports wall clock).

    The function is pure: it does not touch the filesystem, only the
    :class:`ScanResult` plus an explicit ``repo_dir`` string the caller
    fills in. ``repo_dir`` is currently unused by the heuristic but is
    part of the contract so the signature does not need to change when
    we later add a real filesystem sniff (e.g. listing ``src/``).
    """
    _ = repo_dir  # accepted for API stability; not used by current heuristic

    files = list(scan_result.files_cuda or [])
    makefile_text: str | None = None
    for name in ("Makefile", "makefile", "GNUmakefile"):
        if name in files:
            makefile_text = name  # placeholder; verify.py will read the real text
            break

    build_cmd = _detect_cmd(_DEFAULT_HEURISTIC_BUILD_CMDS, files, makefile_text) or _DEFAULT_HEURISTIC_BUILD_CMDS[0]
    run_cmd = _detect_cmd(_DEFAULT_HEURISTIC_RUN_CMDS, files, makefile_text) or _DEFAULT_HEURISTIC_RUN_CMDS[0]

    return Manifest(
        build=BuildSpec(cmd=build_cmd, dir="."),
        run=RunSpec(cmd=run_cmd, timeout_s=_DEFAULT_TIMEOUT_S),
        verify=VerifySpec(mode="self_check", pass_regex=_DEFAULT_PASS_REGEX),
        timing_regex=None,
        source=None,
    )
