"""tests/test_scan.py — FASE 1 SCAN (inventario + wave64 + dificultad).

Capa L4 (phase). Tests pinnean el contrato público de
``core.phases.scan`` contra el mini-fixture ``tests/fixtures/scan_repo``
+ un directorio temporal para el caso "easy" (sin libs, sin PTX).

Reglas duras cubiertas:
  * L4 importa L2 (wave64/schemas/config) y stdlib — NUNCA state/api/
    oracle. Test de pureza de imports al final.
  * Números del reporte salen de código (F-17), nunca del LLM.
  * ``executive_summary`` queda como string vacío: otra capa lo llena.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

from core.phases.scan import portability_report_data, scan
from core.schemas import ScanResult, Wave64Finding


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scan_repo"


# ---------------------------------------------------------------------------
# Helper: armar un mini-repo "easy" en un tmpdir (sin libs, sin PTX).
# ---------------------------------------------------------------------------

def _write_easy_repo(tmp: Path) -> Path:
    """Crea un mini-repo que la heurística §5.3 debe clasificar como
    "easy": 0 PTX, 0 libs, loc < 2000."""
    (tmp / "Makefile").write_text("CC=nvcc\nall:\n\t$(CC) -o tiny tiny.cu\n")
    (tmp / "tiny.cu").write_text(textwrap.dedent("""\
        // Trivial easy-fixture: no libs, no PTX, no wave64 footguns.
        #include <cuda_runtime.h>
        __global__ void add_one(float *x, int n) {
            int i = blockIdx.x * blockDim.x + threadIdx.x;
            if (i < n) x[i] += 1.0f;
        }
        extern "C" void launch(float *x, int n) {
            float *dx = nullptr;
            cudaMalloc((void **)&dx, n * sizeof(float));
            cudaMemcpy(dx, x, n * sizeof(float), cudaMemcpyHostToDevice);
            add_one<<<(n + 255) / 256, 256>>>(dx, n);
            cudaDeviceSynchronize();
            cudaMemcpy(x, dx, n * sizeof(float), cudaMemcpyDeviceToHost);
            cudaFree(dx);
        }
    """))
    return tmp


# ---------------------------------------------------------------------------
# Inventario: el mini-fixture se reconoce
# ---------------------------------------------------------------------------

def test_scan_returns_pydantic_model() -> None:
    result = scan(str(FIXTURE_DIR))
    assert isinstance(result, ScanResult)


def test_scan_files_cuda_includes_cu_and_cuh() -> None:
    result = scan(str(FIXTURE_DIR))
    assert "kernel.cu" in result.files_cuda
    assert "aux.cuh" in result.files_cuda


def test_scan_loc_kernels_is_positive() -> None:
    result = scan(str(FIXTURE_DIR))
    assert result.loc_kernels > 0


# ---------------------------------------------------------------------------
# Conteo de API calls por regex
# ---------------------------------------------------------------------------

def test_scan_api_calls_counts_cuda_malloc_and_memcpy() -> None:
    result = scan(str(FIXTURE_DIR))
    assert "cudaMalloc" in result.api_calls
    assert "cudaMemcpy" in result.api_calls
    # El fixture tiene 3 cudaMalloc y 4 cudaMemcpy en kernel.cu; los
    # tests pinean números EXACTOS para que un cambio de regex
    # accidental (e.g. que rompa word boundaries) no pase silencioso.
    assert result.api_calls["cudaMalloc"] == 3
    assert result.api_calls["cudaMemcpy"] == 4


def test_scan_api_calls_counts_cuda_device_synchronize() -> None:
    result = scan(str(FIXTURE_DIR))
    assert result.api_calls.get("cudaDeviceSynchronize") == 1


# ---------------------------------------------------------------------------
# Librerías: cublas detectada por include + por call
# ---------------------------------------------------------------------------

def test_scan_libs_includes_cublas() -> None:
    result = scan(str(FIXTURE_DIR))
    assert "cublas" in result.libs


def test_scan_libs_is_sorted_unique() -> None:
    result = scan(str(FIXTURE_DIR))
    # Sin duplicados, ordenada alfabéticamente.
    assert result.libs == sorted(set(result.libs))


# ---------------------------------------------------------------------------
# Build system
# ---------------------------------------------------------------------------

def test_scan_build_system_is_make() -> None:
    result = scan(str(FIXTURE_DIR))
    assert result.build_system == "make"


# ---------------------------------------------------------------------------
# Wave64: el __ballot_sync del fixture dispara W01/W02
# ---------------------------------------------------------------------------

def test_scan_wave64_findings_is_non_empty() -> None:
    result = scan(str(FIXTURE_DIR))
    assert result.wave64_findings, (
        "el fixture tiene __ballot_sync(0xffffffff,...) y "
        "unsigned r = __ballot(...) — debe haber al menos un hallazgo"
    )


def test_scan_wave64_findings_are_pydantic_models() -> None:
    result = scan(str(FIXTURE_DIR))
    for f in result.wave64_findings:
        assert isinstance(f, Wave64Finding)


def test_scan_wave64_findings_trigger_w01_or_w02() -> None:
    result = scan(str(FIXTURE_DIR))
    ids = {f.pattern_id for f in result.wave64_findings}
    assert "W01" in ids or "W02" in ids, (
        f"esperaba W01 (mask 0xffffffff) o W02 (unsigned = __ballot), "
        f"obtuve: {sorted(ids)}"
    )


def test_scan_wave64_findings_file_is_relative_path() -> None:
    """El campo ``file`` de cada hallazgo debe ser la ruta RELATIVA
    al repo, no la absoluta del droplet. Así el dashboard es
    portable entre runs/máquinas."""
    result = scan(str(FIXTURE_DIR))
    for f in result.wave64_findings:
        assert f.file == "kernel.cu" or f.file.startswith("kernel.cu"), (
            f"file debe ser relativa, obtuve {f.file!r}"
        )
        assert not f.file.startswith("/"), (
            f"file NO debe ser absoluta, obtuve {f.file!r}"
        )


# ---------------------------------------------------------------------------
# Dificultad: heurística §5.3 (sin LLM)
# ---------------------------------------------------------------------------

def test_scan_difficulty_is_medium_for_fixture_with_cublas() -> None:
    """El fixture tiene cublas (libs no vacías) → NO es "easy" (0 libs
    es False), no tiene PTX ni cudnn ni loc > 10000 → NO es "hard".
    Resultado esperado: "medium"."""
    result = scan(str(FIXTURE_DIR))
    assert result.difficulty == "medium", (
        f"esperaba 'medium' (libs no vacías, sin PTX, loc < 10000), "
        f"obtuve {result.difficulty!r}"
    )


def test_scan_difficulty_is_easy_for_minimal_repo(tmp_path: Path) -> None:
    """Segundo caso: 0 PTX, 0 libs, pocas líneas → "easy"."""
    repo = _write_easy_repo(tmp_path)
    result = scan(str(repo))
    assert result.libs == [], f"easy fixture no debe tener libs, got {result.libs}"
    assert result.loc_kernels < 2000
    assert result.difficulty == "easy", (
        f"esperaba 'easy' (sin libs, sin PTX, loc < 2000), "
        f"obtuve {result.difficulty!r}"
    )


# ---------------------------------------------------------------------------
# Reporte: portability_report_data (F-17, executive_summary vacío)
# ---------------------------------------------------------------------------

def test_portability_report_data_has_executive_summary_empty() -> None:
    """F-17 + INV-7: el párrafo ejecutivo NO lo escribe esta capa."""
    result = scan(str(FIXTURE_DIR))
    data = portability_report_data(result)
    assert data["executive_summary"] == ""


def test_portability_report_data_propagates_counts_from_scan() -> None:
    """Los números del reporte deben venir DIRECTO del ScanResult, no
    recalcularse (F-17: una sola fuente de verdad)."""
    result = scan(str(FIXTURE_DIR))
    data = portability_report_data(result)

    assert data["loc_kernels"] == result.loc_kernels
    assert data["api_calls"] == result.api_calls
    assert data["libs"] == result.libs
    assert data["build_system"] == result.build_system
    assert data["difficulty"] == result.difficulty
    assert data["files_cuda"] == result.files_cuda
    assert len(data["wave64_findings"]) == len(result.wave64_findings)


def test_portability_report_data_has_wave64_count_breakdown() -> None:
    """El template del certificado necesita el desglose por severidad
    para el semáforo de hallazgos. Viene de código, no de LLM."""
    result = scan(str(FIXTURE_DIR))
    data = portability_report_data(result)

    counts = data["wave64_counts"]
    assert counts["total"] == len(result.wave64_findings)
    assert counts["correctness"] == sum(
        1 for f in result.wave64_findings if f.severity == "correctness"
    )
    assert counts["suspicious"] == sum(
        1 for f in result.wave64_findings if f.severity == "suspicious"
    )


# ---------------------------------------------------------------------------
# Error handling: paths raros
# ---------------------------------------------------------------------------

def test_scan_raises_for_missing_repo_dir() -> None:
    with pytest.raises(NotADirectoryError):
        scan("/nonexistent/path/that/does/not/exist/12345")


# ---------------------------------------------------------------------------
# L4 purity: scan.py no puede importar state / api / oracle / llm
# ---------------------------------------------------------------------------

def test_scan_module_l4_purity_imports() -> None:
    """scan es L4 (phase): importa L2 (wave64/schemas/config) y stdlib.
    NO debe importar state / api / oracle / llm. Dirección L4→L2
    respetada, nunca al revés."""
    from core.phases import scan as scan_mod

    source = inspect.getsource(scan_mod)
    tree = ast.parse(source)

    # Nombres importables explícitamente: módulos del paquete core
    # que scan puede tocar (L2 hacia abajo) o stdlib.
    allowed_core = {"core.schemas", "core.wave64", "core.config"}
    # Y, equivalentemente, vía `from core import wave64` etc.
    allowed_core_names = {"wave64", "ScanResult", "Wave64Finding",
                          "Budgets", "Counters", "Run", "BuildError",
                          "ErrorGroup", "FixAttempt", "VerifyResult",
                          "BuildResult", "RunResult", "RunState",
                          "Config", "get_config", "budgets"}
    forbidden_roots = {"core.state", "core.api", "core.oracle", "core.llm"}
    stdlib_roots = {
        "annotations", "ast", "collections", "contextlib", "copy", "dataclasses",
        "datetime", "enum", "functools", "io", "itertools", "json", "os",
        "pathlib", "re", "sys", "typing", "__future__",
    }

    bad: list[str] = []
    forbidden_hits: list[str] = []
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
                # `from core import wave64` o `from core.wave64 import _strip_...`
                # Validar solo los nombres importados contra la whitelist.
                for alias in node.names:
                    if alias.name not in allowed_core_names and not alias.name.startswith("_strip"):
                        bad.append(
                            f"from {module} import {alias.name}"
                        )
            elif module.split(".")[0] not in stdlib_roots:
                bad.append(f"from {module} import ...")

    assert forbidden_hits == [], (
        "scan.py es L4: NO puede importar state/api/oracle/llm, "
        f"encontrado: {forbidden_hits}"
    )
    assert bad == [], (
        "scan.py solo puede importar core.schemas / core.wave64 / core.config "
        f"y stdlib; encontrado: {bad}"
    )
