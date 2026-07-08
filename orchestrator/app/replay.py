"""app/replay.py — modo replay (L6 transporte, AD-4).

El modo replay NO ejecuta el pipeline (blueprint §9): sirve un trace JSONL
grabado, con timing acelerado, para que los jueces vean el dashboard vivo sin
una MI300X. Vive en la capa `app` (no es un modo de oráculo — AD-4): reutiliza
el mismo endpoint `GET /runs/{id}/events?after=N` que el dashboard ya polea.

Diseño:
- Al arrancar en `ORACLE_MODE=replay`, `bootstrap_replay` lee el trace grabado
  (`fixtures/demo-run.jsonl`), siembra el `Run` correspondiente en el store
  (AD-3: el control pasa por el store) y arma un `ReplayClock`.
- El `ReplayClock` revela los eventos gradualmente por tiempo transcurrido
  (§9 "timing acelerado"): el dashboard, con su polling de 1s, ve la corrida
  "reproducirse" en vivo. Cada carga fresca del dashboard (poll con `after=-1`)
  reinicia el reloj, así cada apertura reproduce desde el inicio.
- Los NÚMEROS salen del trace grabado, nunca inventados (F-17).
"""

from __future__ import annotations

import time
from pathlib import Path

from core.config import Config, budgets, get_config
from core.schemas import Counters, Run, RunState
from core.trace import read_events


# Ruta del trace grabado (relativa a la raíz del repo). El repo lo versiona
# en fixtures/ para que `docker compose --profile replay up` funcione en
# cualquier máquina sin GPU (F-16).
def default_replay_trace_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent.parent / "fixtures" / "demo-run.jsonl"
    )


class ReplayClock:
    """Revela eventos de a poco según el tiempo transcurrido (timing acelerado).

    ``events_per_second`` controla la velocidad de reproducción. El reloj
    arranca LAZY: ``t0`` se fija en el PRIMER ``visible_count`` (= el primer
    poll del dashboard), no al construir. Esto evita el bug de reiniciar la
    reproducción en cada poll ``after=-1`` (el dashboard manda ``after=-1``
    hasta recibir eventos): con arranque lazy, la reproducción empieza cuando
    el dashboard se conecta y avanza monótonamente. El total revelado es
    ``floor((now - t0) * eps)``, saturado al número total de eventos.
    """

    def __init__(self, total_events: int, events_per_second: float = 2.5) -> None:
        self._total = total_events
        self._eps = events_per_second
        self._t0: float | None = None

    def start(self, now: float | None = None) -> None:
        """Fija t0 explícitamente (útil para tests deterministas)."""
        self._t0 = time.monotonic() if now is None else now

    def visible_count(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        if self._t0 is None:
            self._t0 = now
        elapsed = max(0.0, now - self._t0)
        revealed = int(elapsed * self._eps)
        return max(0, min(self._total, revealed))


class ReplaySession:
    """Estado de replay para UN run grabado: el path del trace y su reloj."""

    def __init__(self, run_id: str, trace_path: str, total_events: int) -> None:
        self.run_id = run_id
        self.trace_path = trace_path
        self.clock = ReplayClock(total_events)


def _final_state_from_events(events: list[dict]) -> str:
    """Último estado de fase del trace (el estado 'final' del run grabado)."""
    for ev in reversed(events):
        if ev.get("ev") == "phase":
            phase = ev.get("phase", RunState.DONE)
            return phase if phase in RunState.ALL else RunState.DONE
    return RunState.DONE


def bootstrap_replay(store, config: Config | None = None) -> ReplaySession | None:
    """Si el modo es replay, siembra el run grabado en el store y devuelve la sesión.

    Devuelve ``None`` si no estamos en modo replay (el caller no hace nada).
    Idempotente-ish: siembra un único run derivado del trace grabado.
    """
    config = config if config is not None else get_config()
    if config.oracle_mode != "replay":
        return None

    trace_path = default_replay_trace_path()
    if not trace_path.exists():
        # Sin trace grabado no hay nada que reproducir; degradación honesta.
        return None

    events = read_events(str(trace_path))
    if not events:
        return None

    run_id = events[0].get("run", "run_replay")

    # Sembrar el Run en el store (AD-3). Los contadores vienen del evento
    # 'report' del trace si existe (F-17: números del trace, no inventados).
    counters = _counters_from_events(events)
    run = Run(
        id=run_id,
        repo_url=_repo_url_from_events(events),
        state=_final_state_from_events(events),
        budgets=budgets(config),
        counters=counters,
    )
    store.put(run)  # el store de replay expone put(); ver nota abajo

    return ReplaySession(run_id, str(trace_path), total_events=len(events))


def _counters_from_events(events: list[dict]) -> Counters:
    for ev in reversed(events):
        if ev.get("ev") == "report":
            return Counters(
                errors_initial=int(ev.get("errors_initial", 0)),
                errors_current=0,
                fixes_local=int(ev.get("fixes_local", 0)),
                fixes_remote=int(ev.get("fixes_remote", 0)),
                fixes_deterministic=int(ev.get("fixes_deterministic", 0)),
                tokens_local=int(ev.get("tokens_local", 0)),
                tokens_remote=int(ev.get("tokens_remote", 0)),
                iterations=int(ev.get("iterations", 0)),
            )
    return Counters()


def _repo_url_from_events(events: list[dict]) -> str:
    for ev in events:
        if ev.get("ev") == "run_meta" and ev.get("repo_url"):
            return str(ev["repo_url"])
    return "recorded-run"
