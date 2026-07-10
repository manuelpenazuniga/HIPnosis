"""core.llm.router — primitive (L2): tier policy and client factory.

Pure policy module (blueprint §6.4). No network, no state, no I/O.
The loop calls ``decide_tier`` to pick a tier and ``client_for_tier``
to obtain the corresponding ``LLMClient`` — both functions are
deterministic given their inputs, so the build loop is testable and
replayable (F-16).

Layering: L2 primitive. Imports ``core.config`` and ``core.llm.client``
only. No reference to ``phases``, ``oracle`` or ``state``.
"""

from __future__ import annotations

from core.config import Config
from core.llm.client import LLMClient


_TIER_DETERMINISTIC = "deterministic"
_TIER_LOCAL = "local"
_TIER_REMOTE = "remote"
_VALID_TIERS = {_TIER_DETERMINISTIC, _TIER_LOCAL, _TIER_REMOTE}


def decide_tier(
    strategy: str,
    attempts: int,
    tier_sugerido: str | None,
) -> str:
    """Return the tier the loop should use for the next fix attempt.

    Implements blueprint §6.4 verbatim:
      * ``strategy == "deterministic"`` → ``"deterministic"`` (no LLM)
      * first attempt (``attempts == 0``) with suggested tier ``"local"``
        → ``"local"`` (cheap Gemma)
      * everything else → ``"remote"`` (Fireworks)
    """
    if strategy == _TIER_DETERMINISTIC:
        return _TIER_DETERMINISTIC
    # Primer intento: probar el tier local (Gemma, $0 API) cuando la clase lo
    # sugiere — incluye 'local_then_remote' (E99), que antes saltaba directo a
    # remoto en el primer intento (audit codex P1). Reintentos → remoto.
    if attempts == 0 and tier_sugerido in (_TIER_LOCAL, "local_then_remote"):
        return _TIER_LOCAL
    return _TIER_REMOTE


def client_for_tier(tier: str, config: Config) -> LLMClient:
    """Build the :class:`LLMClient` for ``tier`` using ``config`` values.

    URL / model / key come from ``config`` (never hardcoded — F-01).
    Raises :class:`ValueError` if asked for a tier that should not
    trigger an LLM call (``"deterministic"``).
    """
    if tier == _TIER_LOCAL:
        return LLMClient(
            base_url=config.local_llm_base_url,
            model=config.local_llm_model,
        )
    if tier == _TIER_REMOTE:
        return LLMClient(
            base_url=config.remote_llm_base_url,
            model=config.remote_llm_model,
            api_key=config.fireworks_api_key,
        )
    raise ValueError(
        f"tier {tier!r} does not require an LLM client "
        f"(valid tiers: {_TIER_LOCAL!r}, {_TIER_REMOTE!r})"
    )
