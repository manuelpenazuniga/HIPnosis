"""Test de integración end-to-end del pipeline completo (M3): QUEUED→DONE + verify + certificado."""
from __future__ import annotations
import subprocess
from pathlib import Path
import pytest
from core.state import SqliteRunStore
from core.trace import TraceWriter, read_events
from core.config import Config
from core.oracle.mock import MockOracle
from core.manifest import Manifest, BuildSpec, RunSpec, VerifySpec
from core.phases.pipeline import run_full_pipeline
from core.schemas import RunState

FIX_BSW = Path(__file__).resolve().parent.parent.parent / "fixtures" / "bsw"


def _cfg() -> Config:
    return Config(oracle_mode="mock", local_llm_base_url="", local_llm_model="",
                  remote_llm_base_url="", remote_llm_model="", fireworks_api_key="",
                  hf_token="", github_token="", gpu_arch="gfx942", max_iterations=25,
                  max_attempts_per_group=3, max_errors_parsed=30, confidence_threshold=0.6,
                  price_h100_hr=0.0, price_mi300x_hr=0.0)


def test_full_pipeline_reaches_done_with_verify_and_certificate(tmp_path):
    # Workspace causal: contiene lo que los fixtures bsw reportan (audit P0.5).
    from core.runner import _stage_mock_workspace
    repo = tmp_path / "repo"
    _stage_mock_workspace(str(repo), key="bsw")

    store = SqliteRunStore(str(tmp_path / "r.db")); cfg = _cfg()
    run = store.create("https://ex/bsw.git")
    trace = TraceWriter(str(tmp_path / "trace.jsonl"), run.id)
    oracle = MockOracle(str(FIX_BSW))
    manifest = Manifest(build=BuildSpec(cmd="make"), run=RunSpec(cmd="./main"),
                        verify=VerifySpec(mode="self_check", pass_regex="PASS"))

    final = run_full_pipeline(run.id, store, cfg, trace, oracle, manifest, str(repo))

    assert final.state == RunState.DONE
    evs = read_events(trace.path)
    phases = [e["phase"] for e in evs if e["ev"] == "phase"]
    assert phases[0] == RunState.QUEUED and phases[-1] == RunState.DONE
    assert any(e["ev"] == "verify" and e.get("verdict") == "PASS" for e in evs)
    builds = [e["errors"] for e in evs if e["ev"] == "build"]
    assert builds[0] > builds[-1] and builds[-1] == 0     # errores descienden a 0
    cert = repo / "HIPNOSIS_CERTIFICATE.md"
    assert cert.exists()
    txt = cert.read_text()
    assert "PASS" in txt and "NEEDS_HUMAN" in txt.upper().replace(" ", "_") or "NEEDS_HUMAN" in txt
