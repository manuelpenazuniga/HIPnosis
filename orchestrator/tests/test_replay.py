"""Tests del modo replay (AD-4): siembra del run grabado + drip-feed por reloj."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.replay import ReplayClock, bootstrap_replay
from app.store import InMemoryRunStore
from core.config import Config


def _replay_config() -> Config:
    # Config mínima en modo replay (los demás campos con defaults razonables).
    return Config(
        oracle_mode="replay",
        local_llm_base_url="", local_llm_model="", remote_llm_base_url="",
        remote_llm_model="", fireworks_api_key="", hf_token="", github_token="",
        gpu_arch="gfx942", max_iterations=25, max_attempts_per_group=3,
        max_errors_parsed=30, confidence_threshold=0.6,
        price_h100_hr=0.0, price_mi300x_hr=0.0,
    )


def test_clock_lazy_start_and_monotonic():
    c = ReplayClock(total_events=10, events_per_second=2.0)
    # Lazy: sin start explícito, el primer visible_count fija t0 => 0 revelados.
    t = 1000.0
    assert c.visible_count(now=t) == 0
    # Avanza monótono y satura en el total.
    assert c.visible_count(now=t + 1.0) == 2
    assert c.visible_count(now=t + 3.0) == 6
    assert c.visible_count(now=t + 100.0) == 10  # saturado


def test_bootstrap_seeds_recorded_run():
    store = InMemoryRunStore()
    session = bootstrap_replay(store, _replay_config())
    assert session is not None
    run = store.get(session.run_id)
    assert run is not None
    assert run.id == "run_bsw01a2"          # del trace grabado
    # Contadores vienen del evento 'report' del trace (F-17), no inventados.
    assert run.counters.errors_initial == 8
    assert run.counters.fixes_deterministic == 6
    assert run.counters.fixes_local == 2


def test_bootstrap_none_when_not_replay():
    cfg = _replay_config()
    object.__setattr__(cfg, "oracle_mode", "mock")
    assert bootstrap_replay(InMemoryRunStore(), cfg) is None


def test_events_endpoint_dripfeeds(monkeypatch):
    from app import main as main_mod
    # Forzar modo replay en la construcción de la app.
    monkeypatch.setattr(main_mod, "bootstrap_replay",
                        lambda store: bootstrap_replay(store, _replay_config()))
    app = main_mod.create_app()
    client = TestClient(app)

    # El run grabado está registrado.
    assert client.get("/runs/run_bsw01a2").status_code == 200

    # Reloj determinista: t0 en el pasado lejano => todos los eventos visibles.
    app.state.replay.clock.start(now=time.monotonic() - 10_000.0)
    evs = client.get("/runs/run_bsw01a2/events?after=-1").json()
    assert len(evs) == 28                       # trace completo
    assert evs[0]["ev"] == "phase" and evs[0]["phase"] == "QUEUED"
    assert evs[-1]["phase"] == "DONE"
    # Poll incremental: after = último _i => nada nuevo.
    assert client.get(f"/runs/run_bsw01a2/events?after={evs[-1]['_i']}").json() == []
