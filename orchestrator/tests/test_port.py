"""tests/test_port.py — FASE 2 PORT (structural + mock-mode tests).

Capa L4 (phase). Estos tests pinnean el contrato público de
``core.phases.port`` sin tocar ``hipify-perl`` (que es ROCm-only y no
está disponible en la máquina de dev). Lo que validamos:

  * En modo ``mock`` (default), ``port()`` NO invoca subprocess — el
    seam ``run_hipify`` queda como no-op, los ``.cu/.cuh`` no se
    tocan, y el fixture ya representa el estado post-hipify.
  * En modo ``mock`` SÍ se ejecuta la parte determinista: crear la
    rama ``hipnosis/rocm-port``, adaptar el build con
    ``core.buildsys``, y dejar un commit atómico en el repo vía
    ``core.gitrepo`` (INV-3).
  * Cada paso emite al trace ANTES de actuar (INV-4): phase → hipify
    → build → commit.
  * La rama tiene exactamente el nombre del blueprint (§6.0) y el
    mensaje de commit es la cadena exacta de §6.0.
  * El módulo es L4 puro: importa solo ``core.{buildsys,gitrepo,
    schemas,config,trace}`` y stdlib — NUNCA ``core.{state,api,
    oracle,llm}``.

No testeamos el modo ``real`` (subprocess a ``hipify-perl``) porque
requiere ROCm instalado; ese path lo cubre el droplet MI300X en la
integration. La suite de tests verifica que el modo ``real`` está
correctamente CABLEADO (la rama ``if oracle_mode == "real"`` existe y
apunta a ``_real_hipify``), pero sin ejecutarlo.
"""

from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path
from textwrap import dedent

import pytest
from git import Repo as PyGitRepo

from core import gitrepo as gitrepo_mod
from core.config import Config
from core.gitrepo import GitRepo
from core.phases import port as port_mod
from core.phases.port import (
    BRANCH_NAME,
    COMMIT_MESSAGE,
    HIPIFY_BIN,
    PortResult,
    _hipify_runner_for,
    _mock_hipify,
    _real_hipify,
    port,
)
from core.schemas import ScanResult
from core.trace import TraceWriter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(oracle_mode: str = "mock", gpu_arch: str = "gfx942") -> Config:
    """Construye un ``Config`` mínimo a mano. No llamamos ``get_config``
    para no depender de variables de entorno del shell de pytest."""
    return Config(
        oracle_mode=oracle_mode,
        local_llm_base_url="http://vllm:8000/v1",
        local_llm_model="google/gemma-3-27b-it",
        remote_llm_base_url="https://api.fireworks.ai/inference/v1",
        remote_llm_model="",
        fireworks_api_key="",
        hf_token="",
        github_token="",
        gpu_arch=gpu_arch,
        max_iterations=25,
        max_attempts_per_group=3,
        max_errors_parsed=30,
        confidence_threshold=0.6,
        price_h100_hr=0.0,
        price_mi300x_hr=0.0,
    )


def _init_target_repo(repo_dir: Path) -> None:
    """Crea un mini-repo target con un ``.cu`` y un ``Makefile``.

    El estado pre-port es "tal como vino de upstream": ``CC=nvcc``,
    ``-arch=sm_70`` en el build, código CUDA en el .cu. Después del
    port (en modo mock) el Makefile debe aparecer adaptado pero el
    .cu NO se toca (porque el seam ``_mock_hipify`` es no-op)."""
    repo_dir.mkdir(parents=True, exist_ok=True)

    gr = PyGitRepo.init(repo_dir)
    cfg = gr.config_writer()
    try:
        cfg.set_value("user", "name", "Test")
        cfg.set_value("user", "email", "test@example.com")
    finally:
        cfg.release()

    (repo_dir / "Makefile").write_text(
        dedent("""\
            CC=nvcc
            CFLAGS=-O3 -arch=sm_70
            all: kernel
            \t$(CC) $(CFLAGS) -o kernel kernel.cu
        """)
    )
    # El ``.cu`` es "estado pre-hipify" en este fixture; en modo mock
    # no se toca, así que el contenido debe sobrevivir al port.
    (repo_dir / "kernel.cu").write_text(
        dedent("""\
            #include <cuda_runtime.h>
            __global__ void k(float *x) { x[0] += 1.0f; }
        """)
    )

    gr.index.add(["Makefile", "kernel.cu"])
    gr.index.commit("initial upstream snapshot")


def _make_scan_result(files_cuda: list[str], build_system: str = "make") -> ScanResult:
    """ScanResult con la forma mínima que ``port()`` necesita.

    No llenamos ``loc_kernels`` / ``api_calls`` / ``wave64_findings``
    / etc — ``port()`` no los lee. La regla "no metas más campos de
    los que la fase usa" la enforce el LSP en el editor, pero acá
    nos ahorramos unos cuantos ``model_validate`` repetidos."""
    return ScanResult(
        files_cuda=files_cuda,
        loc_kernels=0,
        api_calls={},
        libs=[],
        build_system=build_system,
        wave64_findings=[],
        difficulty="easy",
    )


# ---------------------------------------------------------------------------
# Seams
# ---------------------------------------------------------------------------

def test_hipify_runner_for_mock_mode_returns_mock_runner() -> None:
    runner, mode = _hipify_runner_for(_make_config(oracle_mode="mock"))
    assert mode == "mock"
    assert runner is _mock_hipify


def test_hipify_runner_for_replay_mode_uses_mock() -> None:
    """Replay (T19) tampoco debe invocar hipify-perl: comparte seam
    con mock. Esto evita que el modo ``replay`` (que es como los
    jueces ejecutan el demo sin MI300X, F-16) termine corriendo
    ROCm en la laptop."""
    runner, mode = _hipify_runner_for(_make_config(oracle_mode="replay"))
    assert mode == "mock"
    assert runner is _mock_hipify


def test_hipify_runner_for_real_mode_returns_real_runner() -> None:
    runner, mode = _hipify_runner_for(_make_config(oracle_mode="real"))
    assert mode == "real"
    assert runner is _real_hipify


def test_hipify_runner_for_unknown_mode_falls_back_to_mock() -> None:
    """Si alguien setea ``oracle_mode="banana"``, mejor no invocar
    subprocess. Caer a mock es fail-safe."""
    runner, mode = _hipify_runner_for(_make_config(oracle_mode="banana"))
    assert mode == "mock"
    assert runner is _mock_hipify


def test_mock_hipify_is_a_noop() -> None:
    """``_mock_hipify`` no debe hacer absolutamente nada — ni siquiera
    tocar el filesystem. La guardamos como ``None``-returning
    explícito para que un assert abajo documente el contrato."""
    assert _mock_hipify(["/nonexistent/file.cu", "/another.cu"]) is None


# ---------------------------------------------------------------------------
# port() — flujo end-to-end en modo mock
# ---------------------------------------------------------------------------

def test_port_mock_mode_creates_branch_adapts_build_and_commits(
    tmp_path: Path,
) -> None:
    """Caso feliz: repo target con ``.cu`` + ``Makefile``, modo mock.

    Verifica:
      * La rama ``hipnosis/rocm-port`` existe y está chequeada.
      * El Makefile fue adaptado (CC=hipcc, --offload-arch insertado).
      * El .cu NO fue tocado (mock_hipify es no-op).
      * Hay un commit atómico con el mensaje exacto del blueprint.
      * El PortResult tiene los campos correctos."""
    repo_dir = tmp_path / "src"
    _init_target_repo(repo_dir)
    gr = GitRepo(str(repo_dir))
    cfg = _make_config(oracle_mode="mock")
    scan_result = _make_scan_result(files_cuda=["kernel.cu"])

    result = port(gr, str(repo_dir), scan_result, cfg)

    # 1. Rama correcta.
    assert result.branch == "hipnosis/rocm-port"
    assert gr.current_branch() == "hipnosis/rocm-port"

    # 2. Build file adaptado en disco.
    mk_path = repo_dir / "Makefile"
    mk_content = mk_path.read_text()
    assert "CC=hipcc" in mk_content
    assert "--offload-arch=gfx942" in mk_content
    assert "nvcc" not in mk_content
    assert result.build_files == [str(mk_path)]

    # 3. .cu intacto: el seam mock NO corre hipify.
    cu_path = repo_dir / "kernel.cu"
    cu_after = cu_path.read_text()
    assert "#include <cuda_runtime.h>" in cu_after  # literal pre-hipify
    assert result.hipified_files == ["kernel.cu"]

    # 4. Commit atómico.
    assert result.commit_sha, "port() debe producir un SHA cuando hubo cambios"
    assert len(result.commit_sha) >= 7
    assert gr.head_sha() == result.commit_sha

    # 5. El mensaje del commit es el literal §6.0 (no "fix", no
    #    "wip" — esto es lo que el orquestador va a buscar para
    #    detectar la fase en el log del repo).
    last_msg = gr._repo.head.commit.message  # type: ignore[attr-defined]
    assert last_msg.strip() == COMMIT_MESSAGE

    # 6. Mode declarado en el resultado.
    assert result.mode == "mock"


def test_port_mock_mode_does_not_call_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard dura: en modo mock, ``subprocess.run`` NUNCA debe ser
    llamado. Lo verificamos con un monkeypatch que tira si se
    invoca — equivalente a "no se ejecutó hipify-perl".

    El comando probado (``["hipify-perl", "-inplace", path]``) es
    la ÚNICA razón por la que ``port`` tocaría ``subprocess``: el
    resto del módulo es filesystem puro. Si este test pasa, sabemos
    que la CI (sin ROCm) puede correr la suite completa de port."""
    repo_dir = tmp_path / "src"
    _init_target_repo(repo_dir)
    gr = GitRepo(str(repo_dir))
    cfg = _make_config(oracle_mode="mock")
    scan_result = _make_scan_result(files_cuda=["kernel.cu"])

    def _fail_if_called(*_a, **_kw):
        raise AssertionError(
            "subprocess.run called in mock mode — seam leaked"
        )

    monkeypatch.setattr(port_mod.subprocess, "run", _fail_if_called)
    port(gr, str(repo_dir), scan_result, cfg)


def test_port_mock_mode_emits_trace_events_in_order(
    tmp_path: Path,
) -> None:
    """INV-4: cada paso observable se emite al trace ANTES de
    actuar. Verificamos que existen los 4 eventos esperados, en el
    orden correcto, y que cada uno lleva los campos que el
    dashboard va a leer."""
    repo_dir = tmp_path / "src"
    _init_target_repo(repo_dir)
    gr = GitRepo(str(repo_dir))
    cfg = _make_config(oracle_mode="mock")
    scan_result = _make_scan_result(files_cuda=["kernel.cu"])

    trace_path = tmp_path / "trace.jsonl"
    tw = TraceWriter(str(trace_path), run_id="run_test")

    port(gr, str(repo_dir), scan_result, cfg, trace=tw)

    raw = trace_path.read_text().splitlines()
    events = [__import__("json").loads(line) for line in raw if line.strip()]
    ev_names = [e["ev"] for e in events]

    # El contrato exacto: 4 eventos de la fase, en este orden.
    assert ev_names == [
        "port.phase",
        "port.hipify",
        "port.build",
        "port.commit",
    ]

    # Cada evento lleva su run_id inyectado por el TraceWriter.
    assert all(e["run"] == "run_test" for e in events)

    # port.phase lleva el modo y la rama.
    phase = events[0]
    assert phase["branch"] == BRANCH_NAME
    assert phase["mode"] == "mock"
    assert phase["files_cuda"] == 1

    # port.hipify lleva la lista de archivos.
    hip = events[1]
    assert hip["mode"] == "mock"
    assert hip["files"] == ["kernel.cu"]

    # port.build lleva el build_system y la gpu_arch del config.
    build = events[2]
    assert build["build_system"] == "make"
    assert build["gpu_arch"] == "gfx942"

    # port.commit lleva el sha, que debe coincidir con el del
    # PortResult.
    commit = events[3]
    assert commit["sha"]  # non-empty
    assert commit["branch"] == BRANCH_NAME
    assert commit["hipified"] == 1
    assert commit["build_files"] == 1


def test_port_works_without_trace(tmp_path: Path) -> None:
    """``trace=None`` es la firma que usa el modo replay / dry-run.
    El flujo no debe depender de tener un trace vivo."""
    repo_dir = tmp_path / "src"
    _init_target_repo(repo_dir)
    gr = GitRepo(str(repo_dir))
    cfg = _make_config(oracle_mode="mock")
    scan_result = _make_scan_result(files_cuda=["kernel.cu"])

    result = port(gr, str(repo_dir), scan_result, cfg, trace=None)

    assert result.branch == BRANCH_NAME
    assert result.commit_sha  # non-empty: hubo cambios


def test_port_uses_gitconfig_gpu_arch(tmp_path: Path) -> None:
    """INV-9: el arch viene de ``config.gpu_arch``. El ``adapt_build``
    lo propaga al ``--offload-arch=...`` flag del Makefile."""
    repo_dir = tmp_path / "src"
    _init_target_repo(repo_dir)
    gr = GitRepo(str(repo_dir))
    cfg = _make_config(oracle_mode="mock", gpu_arch="gfx90a")
    scan_result = _make_scan_result(files_cuda=["kernel.cu"])

    port(gr, str(repo_dir), scan_result, cfg)

    mk_content = (repo_dir / "Makefile").read_text()
    assert "--offload-arch=gfx90a" in mk_content
    assert "gfx942" not in mk_content


def test_port_no_cuda_files_still_adapts_build(tmp_path: Path) -> None:
    """Repo sin ``.cu`` (puro C++ + HIP, por ejemplo): el port no
    tiene a qué hipificar, pero el build igual se adapta. El
    commit puede ser vacío (``""``) o no, según el build file
    haya cambiado — lo que nos importa es que NO explota."""
    repo_dir = tmp_path / "src"
    _init_target_repo(repo_dir)
    gr = GitRepo(str(repo_dir))
    cfg = _make_config(oracle_mode="mock")
    scan_result = _make_scan_result(files_cuda=[])  # nada que hipificar

    result = port(gr, str(repo_dir), scan_result, cfg)

    assert result.hipified_files == []
    assert "CC=hipcc" in (repo_dir / "Makefile").read_text()
    assert result.commit_sha  # el build sí cambió → sí hay commit


def test_port_clean_tree_returns_empty_sha(tmp_path: Path) -> None:
    """Repo donde ni el build ni los ``.cu`` necesitan cambios
    (ya estaban adaptados). El commit es ``""`` (limpio) y la
    fase reporta éxito igual — la contractura del loop es que
    ``port()`` siempre es safe-to-call."""
    repo_dir = tmp_path / "src"
    _init_target_repo(repo_dir)

    # Pre-adapt the Makefile so the port phase has nothing to do.
    (repo_dir / "Makefile").write_text(
        "CC=hipcc --offload-arch=gfx942\nCFLAGS=-O3 -ffast-math\n"
    )
    # Commit the pre-adaptation so the tree is "already ported" from
    # the pipeline's point of view.
    gr_pre = PyGitRepo(str(repo_dir))
    gr_pre.index.add(["Makefile"])
    gr_pre.index.commit("pre: already ported")

    gr = GitRepo(str(repo_dir))
    cfg = _make_config(oracle_mode="mock")
    scan_result = _make_scan_result(files_cuda=["kernel.cu"])

    result = port(gr, str(repo_dir), scan_result, cfg)

    assert result.commit_sha == ""
    assert gr.head_sha() != ""  # HEAD sigue apuntando al commit pre-existente
    assert result.branch == BRANCH_NAME


def test_port_branch_name_matches_blueprint() -> None:
    """Snapshot del nombre de rama. El blueprint §6.0 lo fija como
    ``hipnosis/rocm-port``; cambiarlo rompería el contrato con la
    CI y el script de extracción de branches en el merge final."""
    assert BRANCH_NAME == "hipnosis/rocm-port"


def test_port_commit_message_matches_blueprint() -> None:
    """Idem para el mensaje de commit (§6.0 paso 4)."""
    assert COMMIT_MESSAGE == "port: hipify-perl + build adaptation"


def test_port_uses_perl_not_clang() -> None:
    """F-02: ``hipify-perl``, NUNCA ``hipify-clang``. Esta constante
    es lo que el módulo exporta; cambiarla a ``hipify-clang``
    rompería la build en máquinas sin headers CUDA (Droplet MI300X)."""
    assert HIPIFY_BIN == "hipify-perl"
    assert "clang" not in HIPIFY_BIN


# ---------------------------------------------------------------------------
# L4 purity: port.py no importa state / api / oracle / llm
# ---------------------------------------------------------------------------

def test_port_module_l4_purity_imports() -> None:
    """``port`` es L4 (phase): importa L2 (buildsys, gitrepo) y L1
    (schemas, config, trace). NUNCA state/api/oracle/llm — el camino
    de la dependencia va solo para abajo, nunca al revés."""
    source = inspect.getsource(port_mod)
    tree = ast.parse(source)

    allowed_core = {
        "core.schemas", "core.gitrepo", "core.config", "core.trace",
        "core.buildsys", "core",  # `from core import buildsys`
    }
    allowed_core_names = {
        "buildsys",
        "Config", "GitRepo", "GitRepoError",
        "ScanResult",
        "TraceWriter",
    }
    forbidden_roots = {"core.state", "core.api", "core.oracle", "core.llm"}
    stdlib_roots = {
        "annotations", "ast", "collections", "contextlib", "copy",
        "dataclasses", "datetime", "enum", "functools", "io", "itertools",
        "json", "os", "pathlib", "re", "subprocess", "sys", "typing",
        "__future__",
    }

    forbidden_hits: list[str] = []
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in forbidden_roots:
                    forbidden_hits.append(f"import {alias.name}")
                elif root not in stdlib_roots and alias.name not in allowed_core:
                    bad.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "__future__":
                continue
            if any(module == f or module.startswith(f + ".")
                   for f in forbidden_roots):
                forbidden_hits.append(f"from {module} import ...")
                continue
            if module in allowed_core or module == "core" or module.startswith("core."):
                for alias in node.names:
                    if alias.name not in allowed_core_names and not alias.name.startswith("_"):
                        bad.append(f"from {module} import {alias.name}")
            elif module.split(".")[0] not in stdlib_roots:
                bad.append(f"from {module} import ...")

    assert forbidden_hits == [], (
        "port.py es L4: NO puede importar state/api/oracle/llm, "
        f"encontrado: {forbidden_hits}"
    )
    assert bad == [], (
        "port.py solo puede importar core.{buildsys,gitrepo,schemas,"
        "config,trace} y stdlib; encontrado: " + str(bad)
    )
