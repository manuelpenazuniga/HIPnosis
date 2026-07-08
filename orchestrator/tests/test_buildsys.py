"""tests/test_buildsys.py — pure L2 tests for ``core.buildsys``.

These tests pin the deterministic rules of blueprint §6.0 to text-level
expectations so that the build loop can rely on them. No subprocess, no
network, no ROCm — the module is pure stdlib by design (the seam for
``hipify-perl`` lives in ``core.phases.port``, not here).

Layers tested:
  * ``adapt_makefile(text, gpu_arch)`` — text-in / text-out, idempotent.
  * ``adapt_cmake(text, gpu_arch)``   — best-effort (E13 fallback elsewhere).
  * ``adapt_build(repo_dir, build_system, gpu_arch)`` — on-disk rewrite,
    returns the list of files actually modified.
"""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path
from textwrap import dedent

import pytest

from core import buildsys
from core.buildsys import adapt_build, adapt_cmake, adapt_makefile


# ---------------------------------------------------------------------------
# Reusable fixtures (representative HeCBench-style Makefiles)
# ---------------------------------------------------------------------------

#: A realistic HeCBench-style Makefile. Mirrors
#: ``tests/fixtures/scan_repo/Makefile`` in spirit but adds the full
#: set of flags §6.0 cares about so a single fixture exercises every
#: rule at once.
HECBENCH_MAKEFILE = dedent("""\
    # HeCBench-style Makefile (CUDA -> HIP adaptation under test)
    CC=nvcc
    NVCC=nvcc
    CFLAGS=-O3 -arch=sm_70 -gencode arch=compute_70,code=sm_70 --use_fast_math -lineinfo

    all: kernel

    kernel: kernel.cu aux.cuh
    \t$(CC) $(CFLAGS) -o kernel kernel.cu

    clean:
    \trm -f kernel
""")


# ---------------------------------------------------------------------------
# adapt_makefile — text in / text out
# ---------------------------------------------------------------------------

def test_adapt_makefile_rewrites_nvcc_to_hipcc() -> None:
    out = adapt_makefile("CC=nvcc\n")
    assert "CC=hipcc" in out
    assert "CC=nvcc" not in out


def test_adapt_makefile_handles_cc_cxx_and_nvcc_vars() -> None:
    """Las TRES variables del blueprint: ``CC``, ``CXX``, ``NVCC``.

    ``CXX=nvcc`` es defensivo: en HeCBench no aparece, pero un repo
    con ``CXX=nvcc -O3`` debe seguir funcionando. La regla reemplaza
    solo el token literal ``nvcc``, no la RHS completa."""
    text = "CC=nvcc\nCXX=nvcc -O3\nNVCC=nvcc\n"
    out = adapt_makefile(text)
    assert "CC=hipcc" in out
    assert "CXX=hipcc -O3" in out  # RHS preserved, solo se cambia el token
    assert "NVCC=hipcc" in out
    assert "nvcc" not in out


def test_adapt_makefile_handles_spaced_equals() -> None:
    """``CC = nvcc`` con espacios debe matchear igual que ``CC=nvcc``."""
    text = "CC = nvcc\nCFLAGS = -O3 -arch=sm_70\n"
    out = adapt_makefile(text)
    assert "CC = hipcc" in out
    assert "-arch=sm_70" not in out


def test_adapt_makefile_drops_arch_sm_flag() -> None:
    out = adapt_makefile("CFLAGS=-O3 -arch=sm_70\n")
    assert "-arch=sm_70" not in out
    # CFLAGS intacta: solo se removió la flag ofensiva.
    assert "CFLAGS=" in out and "-O3" in out


def test_adapt_makefile_drops_arch_sm_various_values() -> None:
    """sm_60, sm_70, sm_80 — todas las variantes HeCBench."""
    for sm in ("sm_60", "sm_70", "sm_75", "sm_80", "sm_86", "sm_89"):
        out = adapt_makefile(f"CFLAGS=-arch={sm} -O3\n")
        assert f"-arch={sm}" not in out, f"failed for {sm}"


def test_adapt_makefile_drops_gencode_flag_with_value() -> None:
    out = adapt_makefile(
        "CFLAGS=-gencode arch=compute_70,code=sm_70 -O3\n"
    )
    assert "-gencode" not in out
    assert "arch=compute_70,code=sm_70" not in out
    assert "-O3" in out


def test_adapt_makefile_renames_use_fast_math_to_ffast_math() -> None:
    out = adapt_makefile("CFLAGS=-O3 --use_fast_math\n")
    assert "--use_fast_math" not in out
    assert "-ffast-math" in out


def test_adapt_makefile_adds_offload_arch_once() -> None:
    out = adapt_makefile("CC=nvcc\nCFLAGS=-O3\n")
    # Aparece exactamente una vez, con el arch por defecto.
    assert out.count("--offload-arch=gfx942") == 1


def test_adapt_makefile_uses_provided_gpu_arch() -> None:
    out = adapt_makefile("CC=nvcc\n", gpu_arch="gfx90a")
    assert "--offload-arch=gfx90a" in out
    assert "gfx942" not in out


def test_adapt_makefile_does_not_double_inject_offload_arch() -> None:
    """Si el repo YA tenía ``--offload-arch=...``, no se inserta otro."""
    out = adapt_makefile("CC=hipcc --offload-arch=gfx90a\n")
    # El pre-check bloquea la inserción: la línea queda tal cual.
    assert out.count("--offload-arch=") == 1
    assert "gfx90a" in out
    assert "gfx942" not in out


def test_adapt_makefile_idempotent_hecbench_fixture() -> None:
    """Regla dura: ``adapt(makefile) == adapt(adapt(makefile))``."""
    once = adapt_makefile(HECBENCH_MAKEFILE)
    twice = adapt_makefile(once)
    assert once == twice, (
        "adapt_makefile must be idempotent; round-1 != round-2\n"
        f"round 1:\n{once}\nround 2:\n{twice}"
    )


def test_adapt_makefile_hecbench_combined_rules() -> None:
    """Smoke test contra el fixture HeCBench completo: verifica que
    TODAS las reglas §6.0 se aplican en una sola pasada."""
    out = adapt_makefile(HECBENCH_MAKEFILE)
    # nvcc -> hipcc (en CC, NVCC; CXX no aparece en este fixture)
    assert "CC=hipcc" in out
    assert "NVCC=hipcc" in out
    assert "nvcc" not in out
    # sm + gencode out, --use_fast_math renamed
    assert "-arch=sm_70" not in out
    assert "-gencode" not in out
    assert "compute_70" not in out
    assert "--use_fast_math" not in out
    assert "-ffast-math" in out
    # offload-arch inserted exactly once
    assert out.count("--offload-arch=") == 1
    # unrelated content preserved
    assert "all: kernel" in out
    assert "kernel: kernel.cu aux.cuh" in out
    assert "clean:" in out


def test_adapt_makefile_leaves_paths_with_arch_substring_alone() -> None:
    """Defensivo: un path tipo ``sm_70.cu`` no debe ser mutilado por la
    regla ``-arch=sm_XX`` (que está pensada para FLAGS, no para
    filenames)."""
    out = adapt_makefile("OBJS=kernel_sm_70.o\n")
    assert "kernel_sm_70.o" in out


# ---------------------------------------------------------------------------
# adapt_cmake
# ---------------------------------------------------------------------------

def test_adapt_cmake_replaces_find_package_cuda() -> None:
    cm = dedent("""\
        cmake_minimum_required(VERSION 3.10)
        find_package(CUDA REQUIRED)
        project(x CUDA CXX)
        add_executable(k k.cu)
    """)
    out = adapt_cmake(cm)
    assert "find_package(CUDA" not in out
    assert "project(x CUDA CXX)" in out  # project() intacto


def test_adapt_cmake_renames_enable_language_cuda_to_hip() -> None:
    cm = "enable_language(CUDA)\n"
    out = adapt_cmake(cm)
    assert "enable_language(HIP)" in out
    assert "enable_language(CUDA)" not in out


def test_adapt_cmake_inserts_hip_architectures() -> None:
    cm = "project(x LANGUAGES CXX)\n"
    out = adapt_cmake(cm)
    assert "set(CMAKE_HIP_ARCHITECTURES gfx942)" in out


def test_adapt_cmake_does_not_double_set_hip_arch() -> None:
    cm = "set(CMAKE_HIP_ARCHITECTURES gfx90a)\n"
    out = adapt_cmake(cm)
    # Idempotente: el set preexistente bloquea la inserción.
    assert out.count("CMAKE_HIP_ARCHITECTURES") == 1
    assert "gfx90a" in out
    assert "gfx942" not in out


def test_adapt_cmake_uses_provided_gpu_arch() -> None:
    cm = "project(x LANGUAGES CXX)\n"
    out = adapt_cmake(cm, gpu_arch="gfx90a")
    assert "set(CMAKE_HIP_ARCHITECTURES gfx90a)" in out
    assert "gfx942" not in out


def test_adapt_cmake_idempotent_full_snippet() -> None:
    cm = dedent("""\
        cmake_minimum_required(VERSION 3.10)
        find_package(CUDA REQUIRED)
        project(mybench CUDA CXX)
        enable_language(CUDA)
        set(CMAKE_CUDA_ARCHITECTURES 70)
        add_executable(k k.cu)
    """)
    once = adapt_cmake(cm)
    twice = adapt_cmake(once)
    assert once == twice


def test_adapt_cmake_combined_rules() -> None:
    cm = dedent("""\
        cmake_minimum_required(VERSION 3.10)
        find_package(CUDA REQUIRED)
        project(mybench CUDA CXX)
        enable_language(CUDA)
        set(CMAKE_CUDA_ARCHITECTURES 70)
        add_executable(k k.cu)
    """)
    out = adapt_cmake(cm)
    assert "find_package(CUDA" not in out
    assert "enable_language(HIP)" in out
    assert "set(CMAKE_HIP_ARCHITECTURES gfx942)" in out
    # Lo que NO tocamos queda intacto.
    assert "cmake_minimum_required(VERSION 3.10)" in out
    assert "set(CMAKE_CUDA_ARCHITECTURES 70)" in out
    assert "add_executable(k k.cu)" in out


# ---------------------------------------------------------------------------
# adapt_build — on-disk rewrite
# ---------------------------------------------------------------------------

def test_adapt_build_rewrites_makefile_and_returns_path(tmp_path: Path) -> None:
    mk = tmp_path / "Makefile"
    mk.write_text(HECBENCH_MAKEFILE)

    modified = adapt_build(str(tmp_path), "make")

    assert modified == [str(mk)]
    content = mk.read_text()
    assert "nvcc" not in content
    assert "--offload-arch=gfx942" in content
    assert "-arch=sm_70" not in content
    assert "-ffast-math" in content


def test_adapt_build_rewrites_cmakelists(tmp_path: Path) -> None:
    cm = tmp_path / "CMakeLists.txt"
    cm.write_text(
        "find_package(CUDA REQUIRED)\n"
        "enable_language(CUDA)\n"
        "project(x LANGUAGES CXX)\n"
        "add_executable(k k.cu)\n"
    )
    modified = adapt_build(str(tmp_path), "cmake")
    assert modified == [str(cm)]
    content = cm.read_text()
    assert "find_package(CUDA" not in content
    assert "enable_language(HIP)" in content
    assert "set(CMAKE_HIP_ARCHITECTURES gfx942)" in content


def test_adapt_build_picks_up_lowercase_makefile(tmp_path: Path) -> None:
    """``makefile`` (todo minúscula) es válido (autotools)."""
    mk = tmp_path / "makefile"
    mk.write_text("CC=nvcc\nCFLAGS=-arch=sm_60\n")
    modified = adapt_build(str(tmp_path), "make")
    assert modified == [str(mk)]
    assert "CC=hipcc" in mk.read_text()


def test_adapt_build_picks_up_gnumakefile(tmp_path: Path) -> None:
    mk = tmp_path / "GNUmakefile"
    mk.write_text("CC=nvcc\n")
    modified = adapt_build(str(tmp_path), "make")
    assert modified == [str(mk)]


def test_adapt_build_no_makefile_returns_empty(tmp_path: Path) -> None:
    """Si el repo no tiene build file, ``adapt_build`` retorna ``[]``
    silenciosamente — la falla real la va a reportar el build loop
    (E13) con el contexto completo, no acá."""
    assert adapt_build(str(tmp_path), "make") == []
    assert adapt_build(str(tmp_path), "cmake") == []


def test_adapt_build_unknown_build_system_returns_empty(tmp_path: Path) -> None:
    """``build_system`` desconocido: no tocamos nada. El error se
    surfacea en el loop como E13 (clase ``build_system``)."""
    mk = tmp_path / "Makefile"
    mk.write_text("CC=nvcc\n")
    assert adapt_build(str(tmp_path), "meson") == []
    # Y el archivo no fue tocado.
    assert mk.read_text() == "CC=nvcc\n"


def test_adapt_build_round_trip_is_noop(tmp_path: Path) -> None:
    """Segunda llamada: nada que adaptar, retorna ``[]`` y deja el
    archivo en paz. Esto es la garantía que el build loop necesita para
    re-correr la fase sin inflar el historial de commits."""
    mk = tmp_path / "Makefile"
    mk.write_text(HECBENCH_MAKEFILE)

    first = adapt_build(str(tmp_path), "make")
    assert first  # modified

    second = adapt_build(str(tmp_path), "make")
    assert second == []


def test_adapt_build_passes_through_gpu_arch(tmp_path: Path) -> None:
    mk = tmp_path / "Makefile"
    mk.write_text("CC=nvcc\n")
    adapt_build(str(tmp_path), "make", gpu_arch="gfx90a")
    assert "--offload-arch=gfx90a" in mk.read_text()
    assert "gfx942" not in mk.read_text()


# ---------------------------------------------------------------------------
# L2 purity: buildsys.py NO toca red / subprocess / nada fuera de stdlib
# ---------------------------------------------------------------------------

def test_buildsys_module_is_pure_stdlib() -> None:
    """Regla dura: ``core.buildsys`` es primitivo L2, stdlib only.

    Lo verificamos parseando el AST del módulo y mirando qué importa:
    solo ``__future__`` y stdlib (re, os). Si alguien agrega ``import
    subprocess`` o ``from core.oracle import ...`` acá, este test
    rompe antes de que el problema llegue a producción.
    """
    source = inspect.getsource(buildsys)
    tree = __import__("ast").parse(source)

    allowed_stdlib_roots = {
        "annotations", "os", "re", "__future__",
    }
    bad: list[str] = []
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in allowed_stdlib_roots:
                    bad.append(f"import {alias.name}")
        elif isinstance(node, __import__("ast").ImportFrom):
            module = (node.module or "").split(".")[0]
            if module not in allowed_stdlib_roots:
                bad.append(f"from {node.module} import ...")

    assert bad == [], (
        "buildsys.py es L2 primitivo: solo stdlib + __future__, "
        f"encontrado: {bad}"
    )


def test_buildsys_exposes_expected_public_api() -> None:
    """Snapshot del contrato público: lo que la fase ``port`` y el
    build loop importan de acá. Si alguien renombra o borra alguna de
    estas funciones, este test rompe y obliga a actualizar el caller
    en el mismo commit (en vez de fallar silenciosamente en runtime)."""
    for name in ("adapt_makefile", "adapt_cmake", "adapt_build"):
        assert callable(getattr(buildsys, name, None)), (
            f"buildsys.{name} debe ser público y callable"
        )
