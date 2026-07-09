"""core/runner.py — servicio de ejecución de runs (entre api y el pipeline).

La api (L6) llama a ``execute_run`` (típicamente en un thread de fondo) para correr el pipeline
completo de un run ya encolado. Este módulo arma las 3 cosas que el pipeline necesita y que
dependen del modo (INV-6, el pipeline no distingue mock/real):
  - **workspace**: en real clona ``repo_url``; en mock stage una fuente CUDA mínima hermética
    (para no bajar 1GB de HeCBench en dev; la fuente real la trae M0).
  - **oracle**: mock (fixtures) o real (subprocess hipcc/make).
  - **manifiesto**: el demo escrito a mano si la URL matchea un repo demo, si no un draft.

Respeta AD-3 (el control lo maneja el driver de state vía run_full_pipeline) e INV-5 (un fallo
deja el run en FAILED/DONE_PARTIAL, nunca colgado). No importa app (evita ciclo).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from core.config import Config
from core.gitrepo import GitRepo
from core.manifest import BuildSpec, Manifest, RunSpec, VerifySpec, load_manifest
from core.oracle.base import Oracle
from core.oracle.mock import MockOracle
from core.phases.pipeline import run_full_pipeline
from core.schemas import Run, RunState
from core.state import SqliteRunStore
from core.trace import TraceWriter


# Raíz del repo (para localizar fixtures/ y manifiestos demo).
_ORCH_ROOT = Path(__file__).resolve().parent.parent           # orchestrator/
_REPO_ROOT = _ORCH_ROOT.parent                                # raíz del repo
_FIXTURES = _REPO_ROOT / "fixtures"


def _workspace_dir(run_id: str) -> str:
    return str(_ORCH_ROOT / "workspaces" / run_id / "repo")


def trace_path_for_run(run_id: str) -> str:
    """Path del trace del run (mismo layout que app.api / core.state)."""
    return str(_ORCH_ROOT / "workspaces" / run_id / "trace.jsonl")


def _stage_mock_workspace(repo_dir: str) -> None:
    """Stage una fuente CUDA mínima + git init (mock hermético, sin red).

    Incluye un ``#include <cuda_runtime.h>`` y llamadas cudaX para que los fixes
    deterministas (E01/E02) tengan algo real que transformar en la demo.
    """
    os.makedirs(repo_dir, exist_ok=True)
    Path(repo_dir, "kernel.cu").write_text(
        "#include <cuda_runtime.h>\n"
        '\nextern "C" void launch() {\n'
        "  float *d;\n"
        "  cudaMalloc(&d, 1024);\n"
        "  cudaMemcpy(d, d, 1024, cudaMemcpyHostToDevice);\n"
        "  cudaFree(d);\n"
        "}\n"
    )
    Path(repo_dir, "Makefile").write_text("CC = nvcc\nARCH = sm_60\nmain: kernel.cu\n\t$(CC) -arch=$(ARCH) kernel.cu -o main\nrun: main\n\t./main\n")
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=pipeline@hipnosis.local", "-c", "user.name=HIPnosis",
         "commit", "-qm", "initial import"],
        cwd=repo_dir, check=True, capture_output=True,
    )


def _resolve_manifest(repo_url: str, oracle_mode: str) -> Manifest:
    """Manifiesto para el run.

    En modo **real** se usa el manifiesto demo escrito a mano si la URL matchea (bsw usa
    golden_output contra su ``test-data/result_aa`` real; softmax self_check). En modo **mock**
    la verificación es contra el ``run.txt`` de fixtures (que trae PASS), así que SIEMPRE se usa
    ``self_check`` — el golden por archivo no aplica al workspace hermético staged.
    """
    if oracle_mode == "mock":
        return Manifest(
            build=BuildSpec(cmd="make -f Makefile"),
            run=RunSpec(cmd="./main", timeout_s=120),
            verify=VerifySpec(mode="self_check", pass_regex="PASS"),
        )
    lower = repo_url.lower()
    for key in ("bsw", "softmax", "scan"):
        if key in lower:
            path = _FIXTURES / "manifests" / f"{key}.yaml"
            if path.exists():
                return load_manifest(str(path))
    # default razonable para un repo arbitrario (real)
    return Manifest(
        build=BuildSpec(cmd="make -f Makefile"),
        run=RunSpec(cmd="./main", timeout_s=120),
        verify=VerifySpec(mode="self_check", pass_regex="PASS"),
    )


def _make_oracle(config: Config, repo_dir: str, repo_url: str, manifest: Manifest) -> Oracle:
    """Fabrica el oráculo según el modo (INV-6, mismo contrato)."""
    if config.oracle_mode == "real":
        from core.oracle.real import RealOracle
        return RealOracle(
            repo_dir=repo_dir,
            build_cmd=manifest.build.cmd,
            build_dir=manifest.build.dir,
        )
    # mock: cada repo demo usa SU secuencia de builds (repo→fixtures). Default bsw.
    return MockOracle(str(_FIXTURES / _fixtures_key(repo_url)))


def _fixtures_key(repo_url_or_dir: str) -> str:
    lower = repo_url_or_dir.lower()
    for key in ("bsw", "softmax", "scan"):
        if key in lower:
            return key
    return "bsw"


def execute_run(run_id: str, store: SqliteRunStore, config: Config) -> Run:
    """Corre el pipeline completo de un run ya encolado. Pensado para thread de fondo.

    Nunca propaga excepción (INV-5): run_full_pipeline / el driver dejan el run en un estado
    final (DONE/DONE_PARTIAL/FAILED) y persistido. Devuelve el Run final.
    """
    run = store.get(run_id)
    if run is None:
        raise KeyError(f"run {run_id!r} not found")

    repo_dir = _workspace_dir(run_id)
    os.makedirs(os.path.dirname(trace_path_for_run(run_id)), exist_ok=True)
    trace = TraceWriter(trace_path_for_run(run_id), run_id)

    # Workspace: real clona; mock stage hermético.
    if config.oracle_mode == "real":
        os.makedirs(os.path.dirname(repo_dir), exist_ok=True)
        GitRepo.clone(run.repo_url, repo_dir)
    else:
        _stage_mock_workspace(repo_dir)

    manifest = _resolve_manifest(run.repo_url, config.oracle_mode)
    oracle = _make_oracle(config, repo_dir, run.repo_url, manifest)

    return run_full_pipeline(run_id, store, config, trace, oracle, manifest, repo_dir)
