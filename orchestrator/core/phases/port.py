"""core/phases/port.py — FASE 2 PORT (mechanical port: hipify + build adapt).

Capa L4 (phase). Orquesta el port mecánico del workspace destino: crear la
rama de port, correr ``hipify-perl`` sobre cada ``.cu/.cuh`` detectado en
SCAN, adaptar el build (``core.buildsys``) y dejar todo en un commit
atómico a través de ``core.gitrepo``. La inteligencia del loop de fixes
sigue en la FASE 3 (BUILD_LOOP); esta fase solo deja el repo en el estado
"compilable-en-roc++" para que la build_loop pueda iterar.

Layering: L4 (phase). Importa ``core.gitrepo`` (L2), ``core.schemas`` (L1),
``core.config`` (L1), ``core.trace`` (L1) y ``core.buildsys`` (L2). NUNCA
importa ``core.oracle``, ``core.llm``, ``core.state`` ni ``app``. El
orquestador de más arriba solo pega las piezas; las decisiones de control
las toma la máquina de estados del loop.

Diseño de seam (decisión firme del blueprint §13: desarrollable sin GPU):

    ``run_hipify`` es el ÚNICO punto donde se invoca ``hipify-perl`` vía
    ``subprocess``. En modo ``mock`` (cualquier valor de
    ``config.oracle_mode`` distinto de ``"real"``) ese seam es
    reemplazado por una función vacía que NO toca el filesystem: los
    fixtures del pipeline ya representan el estado post-hipify, y la
    contractura de la CI (que no tiene ROCm) lo agradece. En modo
    ``"real"`` se invoca ``hipify-perl -inplace`` por archivo
    (F-02: PERL, jamás clang; las extensiones ``.cu`` se conservan).

INV-3 / INV-4: cada acción sobre el repo objetivo viaja por
``core.gitrepo`` (commits atómicos y reversibles) y cada paso observable
se emite al ``TraceWriter`` ANTES de actuar, para que un crash a mitad de
la fase deje un rastro consistente en el dashboard.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from core import buildsys
from core.config import Config
from core.gitrepo import GitRepo
from core.schemas import ScanResult
from core.trace import TraceWriter


# ---------------------------------------------------------------------------
# Constantes públicas
# ---------------------------------------------------------------------------

#: Nombre de la rama de port. Convención fija del blueprint §6.0 — los
#: demos y la CI la buscan por este nombre exacto.
BRANCH_NAME = "hipnosis/rocm-port"

#: Mensaje de commit de la fase PORT. Lo único que esta fase escribe en
#: el repo (un solo commit atómico cubre hipify + build adapt).
COMMIT_MESSAGE = "port: hipify-perl + build adaptation"

#: Toolchain por defecto. Invocable explícito (no ``which`` implícito) para
#: que el seam sea trivial de mockear en tests.
HIPIFY_BIN = "hipify-perl"


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class PortResult:
    """Lo que ``port()`` devuelve al orquestador.

    Atributos:
        branch:        nombre de la rama en la que quedó el port (``"hipnosis/rocm-port"``).
        hipified_files: rutas RELATIVAS a ``repo_dir`` de los ``.cu/.cuh`` sobre los
                       que se corrió hipify (o se marcó como ya-hipificados en mock).
        build_files:    rutas ABSOLUTAS de los archivos de build adaptados por
                       ``core.buildsys.adapt_build``. Vacía si el repo no tiene
                       Makefile / CMakeLists.txt.
        commit_sha:     SHA corto del commit atómico creado por la fase, o ``""``
                       si el árbol ya estaba limpio (cero cambios observables —
                       por ejemplo, un repo sin ``.cu`` y sin build file).
        mode:           ``"real"`` o ``"mock"`` — qué ``run_hipify`` se usó.
    """

    branch: str
    hipified_files: List[str] = field(default_factory=list)
    build_files: List[str] = field(default_factory=list)
    commit_sha: str = ""
    mode: str = "mock"


# ---------------------------------------------------------------------------
# Seams: hipify real vs mock
# ---------------------------------------------------------------------------

#: Firma de las funciones que la fase usa para hipificar. ``paths`` son
#: rutas ABSOLUTAS a ``.cu/.cuh`` dentro de ``repo_dir``. La función no
#: retorna nada: la convención es mutar los archivos in-place.
HipifyRunner = Callable[[List[str]], None]


def _real_hipify(paths: List[str]) -> None:
    """Invoca ``hipify-perl -inplace`` por archivo. F-02: PERL, no clang.

    Estrategia: una llamada a ``hipify-perl`` por archivo. Es más lento
    que pasarlos todos de una, pero cada llamada es independiente: si
    hipify se cuelga en un archivo patológico, los anteriores ya
    quedaron adaptados y el commit atómico parcial sigue siendo útil
    para diagnóstico.

    Errores:
      * ``hipify-perl`` no instalado → ``FileNotFoundError`` (subprocess
        propaga la excepción con errno=2). La fase NO lo captura: el
        orquestador decide qué hacer (en modo ``real`` eso es
        probablemente fatal, y el reporte lo dice como ``NEEDS_HUMAN``).
      * ``hipify-perl`` retorna != 0 → ``subprocess.CalledProcessError``.
        Idem: se propaga, con el stderr de hipify dentro de la excepción
        (lo cual es justo lo que el trace quiere registrar).
    """
    for path in paths:
        subprocess.run(
            [HIPIFY_BIN, "-inplace", path],
            check=True,
            # hipify-perl ocasionalmente imprime warnings en stdout que
            # no son errores; los silenciamos para no contaminar el log
            # del orquestador. El stderr sí lo dejamos pasar para que
            # un fallo de perl sea visible.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )


def _mock_hipify(paths: List[str]) -> None:
    """No-op: el modo ``mock`` no toca el repo (los fixtures ya están
    post-hipify). Existe para que el seam sea simétrico y la rama
    ``if config.oracle_mode == "real"`` se lea en una sola línea.
    """
    return None


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _abs_paths(repo_dir: str, rel_paths: List[str]) -> List[str]:
    """Convierte rutas relativas (formato POSIX con ``/``) en absolutas
    dentro de ``repo_dir``. Filtra las que no existen en disco: si SCAN
    reportó un archivo que el workspace ya no tiene, no queremos que el
    subprocess falle con un ENOENT confuso."""
    out: List[str] = []
    for rel in rel_paths:
        abs_path = os.path.join(repo_dir, rel)
        if os.path.isfile(abs_path):
            out.append(abs_path)
    return out


def _hipify_runner_for(config: Config) -> tuple:
    """Devuelve ``(runner, mode_label)`` según ``config.oracle_mode``.

    Cualquier valor distinto de ``"real"`` cae al mock. Esto incluye el
    default (que ya es ``"mock"`` en ``core.config``) y también valores
    como ``"replay"`` que el pipeline ya usaba en T19: replay lee un
    JSONL pregrabado y no debería tocar ROCm, así que comparte el seam
    con mock.
    """
    if getattr(config, "oracle_mode", "mock") == "real":
        return _real_hipify, "real"
    return _mock_hipify, "mock"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def port(
    repo: GitRepo,
    repo_dir: str,
    scan_result: ScanResult,
    config: Config,
    trace: Optional[TraceWriter] = None,
) -> PortResult:
    """FASE 2 — port mecánico de CUDA→HIP/ROCm.

    Pasos (blueprint §6.0):
      1. ``repo.checkout_branch("hipnosis/rocm-port")`` — rama de port.
      2. Por cada ``scan_result.files_cuda`` que exista en disco, correr
         el seam de hipify (``_real_hipify`` o ``_mock_hipify``). En modo
         mock los archivos NO se tocan.
      3. ``buildsys.adapt_build(repo_dir, scan_result.build_system,
         config.gpu_arch)`` — adaptación determinista del build file.
      4. ``repo.commit_all("port: hipify-perl + build adaptation")`` —
         un solo commit atómico cubre toda la fase. Si el árbol queda
         limpio (nada que adaptar, por ejemplo), el SHA es ``""`` y
         igualmente la fase reporta éxito.

    Trazabilidad (INV-4): emitimos ``port.phase`` al inicio, ``port.hipify``
    antes de invocar el seam (con la lista de archivos Y el modo), y
    ``port.build`` antes de la adaptación de build. Los ``ev`` están
    prefijados con ``port.`` para que el dashboard los agrupe visualmente
    como "todo lo que pasó en esta fase" sin ambigüedad con eventos de
    SCAN/BUILD_LOOP.
    """
    runner, mode = _hipify_runner_for(config)

    # 1. Rama.
    repo.checkout_branch(BRANCH_NAME)
    if trace is not None:
        trace.emit(
            "port.phase",
            branch=BRANCH_NAME,
            mode=mode,
            files_cuda=len(scan_result.files_cuda),
        )

    # 2. Hipify (vía seam). En mock NO se ejecuta subprocess; emitimos
    # un evento informativo con la lista para que el dashboard muestre
    # "qué se hubiera tocado".
    abs_cuda = _abs_paths(repo_dir, scan_result.files_cuda)
    if trace is not None:
        trace.emit(
            "port.hipify",
            mode=mode,
            files=[os.path.relpath(p, repo_dir) for p in abs_cuda],
        )
    runner(abs_cuda)

    # 3. Build adapt.
    if trace is not None:
        trace.emit(
            "port.build",
            build_system=scan_result.build_system,
            gpu_arch=config.gpu_arch,
        )
    build_files = buildsys.adapt_build(
        repo_dir, scan_result.build_system, config.gpu_arch
    )

    # 4. Commit atómico (INV-3). ``commit_all`` es seguro de llamar
    # incluso si nada cambió: devuelve "" y no rompe.
    commit_sha = repo.commit_all(COMMIT_MESSAGE)
    if trace is not None:
        trace.emit(
            "port.commit",
            sha=commit_sha,
            branch=BRANCH_NAME,
            hipified=len(abs_cuda),
            build_files=len(build_files),
        )

    return PortResult(
        branch=BRANCH_NAME,
        hipified_files=[os.path.relpath(p, repo_dir) for p in abs_cuda],
        build_files=build_files,
        commit_sha=commit_sha,
        mode=mode,
    )
