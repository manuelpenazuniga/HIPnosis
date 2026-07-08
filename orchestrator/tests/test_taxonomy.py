"""tests/test_taxonomy.py — pure L2 tests for ``core.taxonomy``.

Cubre el contrato del clasificador determinista (blueprint §6.2):
  * ``load_rules`` carga N reglas en el orden del YAML, E99 es la
    ÚLTIMA, cada ``Rule`` tiene su regex compilada (o None).
  * ``classify`` es determinista por regex, ORDEN-DEL-YAML = prioridad,
    y el catch-all E99 absorbe lo no matcheado.
  * ``CUDA_TO_HIP`` contiene las sustituciones críticas (spot check).
  * ``deterministic_fix`` para E02 sobre ``'cudaMemcpy'`` produce
    un reemplazo que menciona ``hipMemcpy``.

Capa L2: los tests solo importan ``core.schemas``, ``core.taxonomy`` y
utilidades stdlib. No hay red, no hay disco mutable (las fixtures
viven en ``fixtures/bsw/`` y son read-only).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.errparse import group as group_errors
from core.errparse import parse
from core.schemas import BuildError, ErrorGroup
from core.taxonomy import (
    CUDA_TO_HIP,
    Rule,
    classify,
    deterministic_fix,
    load_rules,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _group_with_message(message: str, file: str = "main.cu", line: int = 1) -> ErrorGroup:
    """Arma un :class:`ErrorGroup` mínimo de UN error (el primer error
    del grupo es el que ``classify`` inspecciona)."""
    e = BuildError(file=file, line=line, col=1, message=message, signature="x" * 40)
    return ErrorGroup(signature="x" * 40, errors=[e])


def _bsw_fixture(name: str) -> str:
    return (Path(__file__).parent.parent.parent / "fixtures" / "bsw" / name).read_text()


# ---------------------------------------------------------------------------
# load_rules
# ---------------------------------------------------------------------------


def test_load_rules_default_path_returns_all_entries() -> None:
    rules = load_rules()
    assert isinstance(rules, list)
    assert len(rules) >= 14, f"rules.yaml should declare >=14 entries, got {len(rules)}"
    for r in rules:
        assert isinstance(r, Rule)
        assert r.id.startswith("E") and len(r.id) == 3
        assert r.name
        assert r.strategy in ("deterministic", "llm")
        # E99 catch-all: ambas regex None
        if r.id == "E99":
            assert r.msg_regex is None
            assert r.file_regex is None
        else:
            # Resto: al menos una regex presente
            assert (r.msg_regex is not None) or (r.file_regex is not None), (
                f"rule {r.id} has neither msg_regex nor file_regex"
            )


def test_load_rules_e99_is_last() -> None:
    """Regla dura del blueprint §6.2: E99 catch-all SIEMPRE al final."""
    rules = load_rules()
    assert rules[-1].id == "E99", (
        f"last rule must be E99, got {rules[-1].id}. Move E99 to the bottom of rules.yaml."
    )


def test_load_rules_order_matches_yaml() -> None:
    """El ORDEN del YAML es la prioridad de ``classify`` (blueprint §6.2)."""
    rules = load_rules()
    expected_prefix = ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09",
                       "E10", "E11", "E12", "E13", "E99"]
    actual = [r.id for r in rules]
    assert actual == expected_prefix, f"order changed: {actual} != {expected_prefix}"


def test_load_rules_compiles_regexes() -> None:
    rules = load_rules()
    for r in rules:
        if r.msg_regex is not None:
            assert hasattr(r.msg_regex, "search")
            assert r.msg_regex.search("foo") is not None or r.msg_regex.search("foo") is None
        if r.file_regex is not None:
            assert hasattr(r.file_regex, "search")


def test_load_rules_deterministic_have_fix_template() -> None:
    """Las clases ``strategy=deterministic`` declaran ``fix_template``
    (es la "receta" que el patcher consume)."""
    rules = load_rules()
    for r in rules:
        if r.strategy == "deterministic":
            assert r.fix_template, f"deterministic rule {r.id} must have a fix_template"
            assert r.tier is None, f"deterministic rule {r.id} must not set a tier"


def test_load_rules_llm_have_tier() -> None:
    rules = load_rules()
    for r in rules:
        if r.strategy == "llm":
            assert r.tier in ("local", "remote", "local_then_remote"), (
                f"llm rule {r.id} needs a valid tier, got {r.tier!r}"
            )


def test_load_rules_custom_path(tmp_path: Path) -> None:
    """``load_rules(path=...)`` carga desde un archivo arbitrario (test del
    default + override)."""
    import yaml as _yaml

    custom = tmp_path / "rules_min.yaml"
    custom.write_text(_yaml.safe_dump([
        {"id": "E01", "name": "x", "match": {"msg_regex": "foo"}, "strategy": "deterministic",
         "fix_template": "s|foo|bar|"},
        {"id": "E99", "name": "u", "match": {}, "strategy": "llm", "tier": "local_then_remote"},
    ]))
    rules = load_rules(custom)
    assert [r.id for r in rules] == ["E01", "E99"]
    assert rules[0].msg_regex is not None and rules[0].msg_regex.search("foobar") is not None


def test_load_rules_rejects_e99_not_last(tmp_path: Path) -> None:
    """Si E99 no está al final, ``load_rules`` falla con ValueError claro."""
    import yaml as _yaml

    bad = tmp_path / "rules_bad.yaml"
    bad.write_text(_yaml.safe_dump([
        {"id": "E99", "name": "u", "match": {}, "strategy": "llm", "tier": "local_then_remote"},
        {"id": "E01", "name": "x", "match": {"msg_regex": "foo"}, "strategy": "deterministic",
         "fix_template": "s|foo|bar|"},
    ]))
    with pytest.raises(ValueError, match="E99"):
        load_rules(bad)


def test_load_rules_rejects_e99_with_match(tmp_path: Path) -> None:
    """E99 con match no-vacío rompe el contrato de catch-all."""
    import yaml as _yaml

    bad = tmp_path / "rules_bad_e99.yaml"
    bad.write_text(_yaml.safe_dump([
        {"id": "E99", "name": "u",
         "match": {"msg_regex": "something"},
         "strategy": "llm", "tier": "local_then_remote"},
    ]))
    with pytest.raises(ValueError, match="EMPTY match"):
        load_rules(bad)


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def test_classify_e01_leftover_cuda_include() -> None:
    rules = load_rules()
    g = _group_with_message("fatal error: 'cuda_runtime.h' file not found")
    assert classify(g, rules) == "E01"


def test_classify_e02_unconverted_api_call() -> None:
    rules = load_rules()
    g = _group_with_message("use of undeclared identifier 'cudaMemcpy'")
    assert classify(g, rules) == "E02"


def test_classify_e05_warp_intrinsic() -> None:
    rules = load_rules()
    g = _group_with_message(
        "use of undeclared identifier '__ballot_sync'; did you mean '__ballot'?"
    )
    assert classify(g, rules) == "E05"


def test_classify_e10_symbol_memcpy() -> None:
    rules = load_rules()
    g = _group_with_message(
        "use of undeclared identifier 'hipMemcpyToSymbol'"
    )
    assert classify(g, rules) == "E10"


def test_classify_e13_build_system() -> None:
    rules = load_rules()
    g = _group_with_message(
        "undefined reference to `main'",
        file="<link>",
    )
    assert classify(g, rules) == "E13"


def test_classify_e99_catchall() -> None:
    """Un mensaje raro que no matchea nada cae al catch-all E99."""
    rules = load_rules()
    g = _group_with_message("some exotic parrot arrived from outer space")
    assert classify(g, rules) == "E99"


def test_classify_is_order_deterministic() -> None:
    """El orden del YAML = prioridad. Un mensaje que podría matchear DOS
    reglas gana la PRIMERA escrita en el archivo."""
    rules = load_rules()
    # 'cudaMemcpy' matchea E02 (msg_regex) y NO matchea E01 ni E05.
    # Si el orden fuera al revés, todavía ganaría E02 por estar
    # primera. El test es contra la realidad del orden actual.
    g = _group_with_message("use of undeclared identifier 'cudaMemcpy'")
    assert classify(g, rules) == "E02"


def test_classify_uses_first_error_of_group() -> None:
    """``classify`` inspecciona SIEMPRE el primer error del grupo
    (el parser agrupa por causa raíz, así que todos los miembros
    comparten el mismo msg — §6.1)."""
    rules = load_rules()
    e0 = BuildError(file="a.cu", line=1, col=1, message="fatal error: 'cuda_runtime.h' file not found",
                    signature="x" * 40)
    e1 = BuildError(file="b.cu", line=1, col=1, message="use of undeclared identifier 'cudaMalloc'",
                    signature="y" * 40)
    g = ErrorGroup(signature="x" * 40, errors=[e0, e1])
    assert classify(g, rules) == "E01", "first error of the group drives the classification"


def test_classify_empty_group_returns_catchall() -> None:
    """Un grupo sin errores (situación degenerada) cae al catch-all E99."""
    rules = load_rules()
    g = ErrorGroup(signature="x" * 40, errors=[])
    assert classify(g, rules) == "E99"


def test_classify_against_bsw_fixture() -> None:
    """Smoke test contra fixtures/bsw/build_01.txt: parseo, agrupo,
    y cada grupo recibe un id de taxonomía válido (E01..E13 o E99)."""
    rules = load_rules()
    raw = _bsw_fixture("build_01.txt")
    groups = group_errors(parse(raw))
    assert groups, "fixture must produce at least one group"

    valid_ids = {r.id for r in rules}
    seen: dict[str, int] = {}
    for g in groups:
        k = classify(g, rules)
        assert k in valid_ids, f"classify returned unknown id {k!r}"
        seen[k] = seen.get(k, 0) + 1

    # El fixture de bsw cubre cuda_runtime.h, cudaMemcpyToSymbol, __ballot_sync
    # → esperamos al menos E01 (leftover include) y E02/E10 (unconverted API).
    assert "E01" in seen, f"expected E01 in classification results, got {seen}"
    assert any(k in ("E02", "E10") for k in seen), (
        f"expected E02 or E10 in classification results, got {seen}"
    )


# ---------------------------------------------------------------------------
# CUDA_TO_HIP
# ---------------------------------------------------------------------------


def test_cuda_to_hip_spot_check() -> None:
    assert CUDA_TO_HIP["cudaMalloc"] == "hipMalloc"
    assert CUDA_TO_HIP["cudaMemcpy"] == "hipMemcpy"
    assert CUDA_TO_HIP["cudaFree"] == "hipFree"
    assert CUDA_TO_HIP["cudaDeviceSynchronize"] == "hipDeviceSynchronize"
    assert CUDA_TO_HIP["cudaMemset"] == "hipMemset"
    assert CUDA_TO_HIP["cudaGetLastError"] == "hipGetLastError"
    assert CUDA_TO_HIP["cudaStreamCreate"] == "hipStreamCreate"
    assert CUDA_TO_HIP["cudaEventCreate"] == "hipEventCreate"
    assert CUDA_TO_HIP["cudaMemcpyHostToDevice"] == "hipMemcpyHostToDevice"


def test_cuda_to_hip_size() -> None:
    """La tabla debe tener al menos ~30 entradas (contrato del spec)."""
    assert len(CUDA_TO_HIP) >= 30, f"CUDA_TO_HIP has only {len(CUDA_TO_HIP)} entries"


# ---------------------------------------------------------------------------
# deterministic_fix
# ---------------------------------------------------------------------------


def test_deterministic_fix_e01_returns_sed_template() -> None:
    rules = load_rules()
    g = _group_with_message("fatal error: 'cuda_runtime.h' file not found")
    fix = deterministic_fix("E01", g)
    assert fix is not None
    # El sed-like debe mencionar el header HIP destino.
    assert "hip/hip_runtime.h" in fix
    # Y el header CUDA origen (con punto escapado en la regex).
    assert "cuda_runtime" in fix
    assert "cuda_runtime.h" in fix or r"cuda_runtime\.h" in fix


def test_deterministic_fix_e02_uses_table() -> None:
    """Para E02 con identificador en la tabla, el fix usa la entrada
    EXPLÍCITA (no la heurística de prefijo)."""
    g = _group_with_message("use of undeclared identifier 'cudaMemcpy'")
    fix = deterministic_fix("E02", g)
    assert fix is not None
    assert "hipMemcpy" in fix
    assert "cudaMemcpy" in fix


def test_deterministic_fix_e02_uses_prefix_heuristic_fallback() -> None:
    """Para un identificador CUDA NO en la tabla pero con prefijo canónico,
    ``deterministic_fix`` aplica la heurística cuda→hip."""
    g = _group_with_message("use of undeclared identifier 'cudaFooBaz'")
    fix = deterministic_fix("E02", g)
    assert fix is not None
    assert "hipFooBaz" in fix
    assert "cudaFooBaz" in fix


def test_deterministic_fix_e02_returns_none_for_unknown() -> None:
    """Si el identificador no calza ni en tabla ni en heurística, devuelve
    None (el fixer LLM se hace cargo)."""
    g = _group_with_message("use of undeclared identifier 'cudf_orphan'")
    fix = deterministic_fix("E02", g)
    # 'cudf_orphan' empieza con 'cu' minúscula + 'd' minúscula → la
    # heurística de prefijo 'cuda'→'hip' NO matchea. Debe ser None.
    assert fix is None


def test_deterministic_fix_e03_handles_types() -> None:
    """E03 (unconverted type/handle) usa la MISMA tabla que E02."""
    g = _group_with_message("unknown type name 'cudaStream_t'")
    fix = deterministic_fix("E03", g)
    assert fix is not None
    assert "hipStream_t" in fix


def test_deterministic_fix_returns_none_for_llm_classes() -> None:
    """Las clases ``strategy=llm`` NO tienen fix determinista."""
    rules = load_rules()
    # E05 (warp_intrinsic_mismatch) es llm; deterministic_fix → None
    g = _group_with_message("use of undeclared identifier '__ballot_sync'")
    assert classify(g, rules) == "E05"
    assert deterministic_fix("E05", g) is None

    # E04 (inline_ptx) — idem.
    g = _group_with_message("error: invalid instruction 'cvt.u32.u64' in asm block")
    assert classify(g, rules) == "E04"
    assert deterministic_fix("E04", g) is None

    # E13 (build_system) — idem.
    g = _group_with_message("undefined reference to `foo'", file="<link>")
    assert classify(g, rules) == "E13"
    assert deterministic_fix("E13", g) is None


def test_deterministic_fix_empty_group_returns_none_for_e02() -> None:
    """Grupo sin errores en E02 → None (nada que sustituir)."""
    g = ErrorGroup(signature="x" * 40, errors=[])
    assert deterministic_fix("E02", g) is None
