"""tests/test_attestation.py — Port Passport (wow #2): atestación verificable.

Verifica que:
  1. El digest del diff es sha256 exacto del texto del diff (verificable por 3ros).
  2. Un byte cambiado en el diff cambia el digest (base del demo TAMPERED).
  3. La atestación declara procedencia L1 honesta (sin claim de firma).
  4. El pipeline completo emite HIPNOSIS_ATTESTATION.jsonl y su digest coincide
     con el diff que sirve el endpoint /diff (cert==passport==diff consistentes).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.attestation import build_attestation, write_attestation
from core.config import Config
from core.manifest import BuildSpec, Manifest, RunSpec, VerifySpec
from core.oracle.mock import MockOracle
from core.phases.pipeline import run_full_pipeline
from core.schemas import Counters, RunState
from core.state import SqliteRunStore
from core.trace import TraceWriter


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_diff_digest_is_verifiable_sha256():
    diff = "diff --git a/kernel.cu b/kernel.cu\n-old\n+new\n"
    att = build_attestation(
        repo_url="https://ex/repo", repo_dir="/nonexistent",
        oracle_mode="mock", gpu_arch="gfx942", verdict="PASS",
        counters=Counters(errors_initial=8, errors_current=0),
        wave64_findings=2, certificate_text="cert", diff_text=diff,
    )
    assert att["predicate"]["materials"]["diff"]["digest"] == _sha(diff)
    assert att["predicate"]["materials"]["certificate"]["digest"] == _sha("cert")


def test_one_byte_change_flips_the_digest():
    diff = "line one\nline two\n"
    d1 = build_attestation(repo_url="r", repo_dir="/nope", oracle_mode="mock",
                           gpu_arch="gfx942", verdict="PASS", counters=None,
                           diff_text=diff)["predicate"]["materials"]["diff"]["digest"]
    d2 = _sha(diff.replace("one", "oNe"))
    assert d1 != d2, "un byte distinto debe cambiar el hash (base del TAMPERED demo)"


def test_provenance_is_honest_L1():
    att = build_attestation(repo_url="r", repo_dir="/nope", oracle_mode="mock",
                            gpu_arch="gfx942", verdict="PASS", counters=None)
    lvl = att["predicate"]["provenance_level"].lower()
    assert "l1" in lvl or "level 1" in lvl or "slsa-l1" in lvl
    assert "unsigned" in lvl, "no debe reclamar firma que no tiene (audit codex)"


def test_write_attestation_roundtrips(tmp_path):
    att = build_attestation(repo_url="r", repo_dir="/nope", oracle_mode="mock",
                            gpu_arch="gfx942", verdict="PASS", counters=None)
    path = write_attestation(att, str(tmp_path))
    assert Path(path).name == "HIPNOSIS_ATTESTATION.jsonl"
    lines = Path(path).read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == att


def _cfg() -> Config:
    return Config(oracle_mode="mock", local_llm_base_url="", local_llm_model="",
                  remote_llm_base_url="", remote_llm_model="", fireworks_api_key="",
                  hf_token="", github_token="", gpu_arch="gfx942", max_iterations=25,
                  max_attempts_per_group=3, max_errors_parsed=30, confidence_threshold=0.6,
                  price_h100_hr=0.0, price_mi300x_hr=0.0)


def test_pipeline_emits_attestation_matching_the_real_diff(tmp_path):
    """El passport que el pipeline escribe debe verificar contra el diff REAL
    del workspace (root..HEAD) — el mismo que sirve /diff. Si coinciden, la
    verificación client-side del dashboard dará VERIFIED."""
    from core.runner import _stage_mock_workspace
    from core.attestation import workspace_diff

    repo = tmp_path / "repo"
    _stage_mock_workspace(str(repo), key="bsw")
    fixtures_bsw = Path(__file__).resolve().parent.parent.parent / "fixtures" / "bsw"

    store = SqliteRunStore(str(tmp_path / "r.db"))
    run = store.create("https://ex/bsw.git")
    trace = TraceWriter(str(tmp_path / "trace.jsonl"), run.id)
    manifest = Manifest(build=BuildSpec(cmd="make"), run=RunSpec(cmd="./main"),
                        verify=VerifySpec(mode="self_check", pass_regex="PASS"))

    final = run_full_pipeline(run.id, store, _cfg(), trace,
                              MockOracle(str(fixtures_bsw)), manifest, str(repo))
    assert final.state == RunState.DONE

    att_path = repo / "HIPNOSIS_ATTESTATION.jsonl"
    assert att_path.exists(), "el pipeline debe escribir el Port Passport"
    att = json.loads(att_path.read_text().splitlines()[0])

    # el digest declarado == sha256 del diff real del workspace
    real_diff = workspace_diff(str(repo))
    assert att["predicate"]["materials"]["diff"]["digest"] == _sha(real_diff)
    assert att["predicate"]["result"]["verdict"] == "PASS"
    assert att["predicate"]["source"]["commit"], "debe registrar el commit source real"
