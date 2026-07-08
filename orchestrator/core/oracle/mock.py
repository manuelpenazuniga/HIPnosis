"""core/oracle/mock.py — deterministic fixture-replay oracle (L3).

Used in CI and on the developer's laptop: no GPU, no subprocess, no
network. ``MockOracle`` re-emits pre-recorded compiler output from
``build_*.txt`` files inside ``fixtures_dir``, advancing an internal
counter on every ``build()`` call. The LAST fixture in the directory
must be a clean build (0 error lines) so the loop can converge to
green; once that point is reached, further ``build()`` calls keep
returning the same clean result (idempotent at the end).

Error counting is intentionally crude (regex on ``: error:`` /
``: fatal error:``) on purpose: this layer does NOT consult the
taxonomy, and it MUST NOT import ``errparse`` (L2). That is the
contract the rest of the system relies on — INV-6: mock and real
are indistinguishable from the loop's point of view.

Layering: L3. Imports ``core.oracle.base``, ``core.schemas`` and
stdlib only. No reference to ``phases``, ``llm``, ``state`` or
``errparse``.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.oracle.base import Oracle
from core.schemas import BuildResult, RunResult


_ERROR_LINE = re.compile(r":\s*(?:fatal\s+)?error:")


def _count_error_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if _ERROR_LINE.search(line))


class MockOracle(Oracle):
    """Replay build fixtures sequentially; return a static run result.

    The constructor snapshots every ``build_*.txt`` and ``run.txt`` in
    ``fixtures_dir``. ``build()`` advances a per-instance cursor through
    the snapshot list; once the cursor walks past the last fixture, the
    LAST fixture is returned on every subsequent call so the loop's
    "is it green yet?" check stays stable (idempotent at the end).
    """

    def __init__(self, fixtures_dir: str) -> None:
        self._dir = Path(fixtures_dir)
        self._builds: list[str] = []
        self._cursor = 0
        self._run_stdout: str = "PASS\n"
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        build_files = sorted(self._dir.glob("build_*.txt"))
        if not build_files:
            raise FileNotFoundError(
                f"no build_*.txt fixtures in {self._dir}"
            )
        for path in build_files:
            self._builds.append(path.read_text(encoding="utf-8"))

        run_path = self._dir / "run.txt"
        if run_path.exists():
            self._run_stdout = run_path.read_text(encoding="utf-8")

    def build(self) -> BuildResult:
        if self._cursor < len(self._builds):
            raw = self._builds[self._cursor]
            self._cursor += 1
        else:
            raw = self._builds[-1]
        count = _count_error_lines(raw)
        ok = count == 0
        return BuildResult(
            ok=ok,
            count=count,
            raw_output=raw,
            returncode=0 if ok else 1,
        )

    def run(self, run_cmd: str | None = None, timeout_s: int = 120) -> RunResult:
        del run_cmd, timeout_s
        return RunResult(
            ran=True,
            exit_code=0,
            stdout=self._run_stdout,
            timing=None,
        )
