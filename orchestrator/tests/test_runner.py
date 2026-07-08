"""Test de integración de core.runner.execute_run (mock, síncrono → DONE + certificado)."""
from __future__ import annotations
import os
from pathlib import Path
import pytest
from core.state import SqliteRunStore
from core.config import Config
from core.schemas import RunState
from core import runner


def _cfg(mode="mock") -> Config:
    return Config(oracle_mode=mode, local_llm_base_url="", local_llm_model="",
                  remote_llm_base_url="", remote_llm_model="", fireworks_api_key="",
                  hf_token="", github_token="", gpu_arch="gfx942", max_iterations=25,
                  max_attempts_per_group=3, max_errors_parsed=30, confidence_threshold=0.6,
                  price_h100_hr=0.0, price_mi300x_hr=0.0)


def test_execute_run_mock_reaches_done(tmp_path, monkeypatch):
    # Redirigir workspaces a tmp para no ensuciar el repo.
    monkeypatch.setattr(runner, "_ORCH_ROOT", tmp_path)
    store = SqliteRunStore(str(tmp_path / "r.db"))
    run = store.create("https://github.com/zjin-lcf/HeCBench (bsw)")
    final = runner.execute_run(run.id, store, _cfg("mock"))
    assert final.state == RunState.DONE
    # certificado generado en el workspace del run
    cert = tmp_path / "workspaces" / run.id / "repo" / "HIPNOSIS_CERTIFICATE.md"
    assert cert.exists()
    assert "PASS" in cert.read_text()
    # trace escrito y con la secuencia de fases
    from core.trace import read_events
    evs = read_events(runner.trace_path_for_run(run.id))
    phases = [e["phase"] for e in evs if e["ev"] == "phase"]
    assert phases[0] == RunState.QUEUED and phases[-1] == RunState.DONE
