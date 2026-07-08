"""core/oracle/base.py — abstract oracle interface (L3).

The oracle is the ONLY surface the build / verify loop consults to decide
if a compile succeeded and a run passed. ``Oracle`` is the contract that
``core.oracle.real`` (subprocess on the MI300X) and ``core.oracle.mock``
(replay of fixtures) must honour identically — INV-6 says no phase may
branch on the oracle mode.

Layering: L3. Imports only ``core.schemas``. No reference to ``phases``,
``llm``, ``state`` or ``errparse``: the oracle is a pure execution
surface, it counts compiler error markers crudely and never interprets
them through the taxonomy. ``BuildResult`` and ``RunResult`` live in
``schemas`` (AD-2) so this layer stays free of value types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.schemas import BuildResult, RunResult


class Oracle(ABC):
    """Abstract surface consulted by the build / verify loop.

    ``build()`` is invoked after every patch attempt: it returns the raw
    compiler output, a crude line-count of ``: error:`` markers, and a
    boolean verdict derived from that count. No taxonomy parsing happens
    here — that is the L2 ``errparse`` layer's job.

    ``run()`` executes (or replays) the program's self-check and returns
    its stdout and exit code. ``run_cmd`` is accepted for parity with the
    real oracle; ``mock`` ignores it.
    """

    @abstractmethod
    def build(self) -> BuildResult:
        """Compile the current workspace and report raw output + crude count."""
        raise NotImplementedError

    @abstractmethod
    def run(self, run_cmd: str | None = None, timeout_s: int = 120) -> RunResult:
        """Run the program's self-check and report stdout + exit code."""
        raise NotImplementedError
