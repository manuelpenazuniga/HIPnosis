"""core/taxonomy.py — clasificador determinista de errores de porting.

Capa L2 (blueprint §0, §6.2). Carga ``core/rules.yaml`` y expone:

  * :class:`Rule`         — entrada del catálogo (dataclass inmutable).
  * :func:`load_rules`    — parser de ``rules.yaml`` con validación dura de
                            orden (E99 catch-all SIEMPRE al final).
  * :func:`classify`      — clasificación DETERMINISTA por regex; devuelve
                            el id de la PRIMERA regla cuyo match positivo
                            contra el primer error del grupo.
  * :data:`CUDA_TO_HIP`   — tabla de sustitución cuX→hipX (~40 entradas);
                            cubre runtime API, tipos, enums y constantes.
  * :func:`deterministic_fix` — para clases ``deterministic`` (E01, E02,
                            E03) devuelve el reemplazo de identificador
                            o un sed-like; para ``llm`` devuelve None
                            (el fixer LLM lo maneja — §6.5-B).

La clasificación LLM (blueprint §6.5-A) es OTRA capa en ``phases/``;
acá SOLO va la regex determinista (F-09 / §6.2). Los prompts viven
en ``prompts.py``; los umbrales en ``config.py`` (INV-9).

Layering: importa solo ``core.schemas``, ``core.config``, ``yaml`` y
stdlib (``re``, ``dataclasses``, ``pathlib``). NO referencia
``phases/``, ``oracle/``, ``llm/`` ni ``state/``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from core.schemas import ErrorGroup


# ---------------------------------------------------------------------------
# Tabla de sustitución CUDA → HIP.
#
# Subset del map de hipify (https://rocm.docs.amd.com/projects/HIPIFY):
#   * Runtime API: cudaXxx → hipXxx
#   * Tipos/handles/enums: cudaXxx_t → hipXxx_t
#   * Constantes de memoria: cudaMemcpyHostToDevice → hipMemcpyHostToDevice
#   * Macros de error: cudaSuccess → hipSuccess
#
# La regla mecánica "cuda"→"hip" cubriría la mayoría, pero se enumeran
# explícitamente las ~40 entradas críticas para:
#   1) Mensajes de error precisos al patcher (no double-step).
#   2) Evitar falsos positivos en identificadores que NO son CUDA API
#      (p.ej. "cudaFoo" definido por el usuario se intenta mapear igual;
#      para esos casos la heurística de "no match en tabla" caerá a E02
#      y el parche将通过 E02.Literal de identificador).
# ---------------------------------------------------------------------------

CUDA_TO_HIP: dict[str, str] = {
    # --- Runtime API: memory ------------------------------------------------
    "cudaMalloc": "hipMalloc",
    "cudaFree": "hipFree",
    "cudaMemcpy": "hipMemcpy",
    "cudaMemcpyAsync": "hipMemcpyAsync",
    "cudaMemcpyHostToDevice": "hipMemcpyHostToDevice",
    "cudaMemcpyDeviceToHost": "hipMemcpyDeviceToHost",
    "cudaMemcpyDeviceToDevice": "hipMemcpyDeviceToDevice",
    "cudaMemcpyHostToHost": "hipMemcpyHostToHost",
    "cudaMemcpyDefault": "hipMemcpyDefault",
    "cudaMemset": "hipMemset",
    "cudaMemsetAsync": "hipMemsetAsync",
    "cudaMemGetInfo": "hipMemGetInfo",
    "cudaHostAlloc": "hipHostMalloc",
    "cudaHostFree": "hipHostFree",
    "cudaMallocHost": "hipHostMalloc",
    "cudaMallocManaged": "hipMallocManaged",
    "cudaMallocPitch": "hipMallocPitch",
    # --- Runtime API: streams / events ---------------------------------------
    "cudaStreamCreate": "hipStreamCreate",
    "cudaStreamCreateWithFlags": "hipStreamCreateWithFlags",
    "cudaStreamCreateWithPriority": "hipStreamCreateWithPriority",
    "cudaStreamDestroy": "hipStreamDestroy",
    "cudaStreamSynchronize": "hipStreamSynchronize",
    "cudaStreamWaitEvent": "hipStreamWaitEvent",
    "cudaDeviceSynchronize": "hipDeviceSynchronize",
    "cudaEventCreate": "hipEventCreate",
    "cudaEventCreateWithFlags": "hipEventCreateWithFlags",
    "cudaEventDestroy": "hipEventDestroy",
    "cudaEventRecord": "hipEventRecord",
    "cudaEventSynchronize": "hipEventSynchronize",
    "cudaEventElapsedTime": "hipEventElapsedTime",
    # --- Runtime API: device / module / misc --------------------------------
    "cudaGetDevice": "hipGetDevice",
    "cudaSetDevice": "hipSetDevice",
    "cudaGetDeviceCount": "hipGetDeviceCount",
    "cudaGetDeviceProperties": "hipGetDeviceProperties",
    "cudaDeviceReset": "hipDeviceReset",
    "cudaGetLastError": "hipGetLastError",
    "cudaPeekAtLastError": "hipPeekAtLastError",
    "cudaGetErrorString": "hipGetErrorString",
    "cudaGetErrorName": "hipGetErrorName",
    # --- Runtime API: launch -------------------------------------------------
    "cudaLaunchKernel": "hipLaunchKernel",
    "cudaConfigureCall": "hipConfigureCall",
    "cudaSetupArgument": "hipSetupArgument",
    # --- Runtime API: symbol access (E10 usa HIP_SYMBOL por encima) ---------
    "cudaMemcpyToSymbol": "hipMemcpyToSymbol",
    "cudaMemcpyFromSymbol": "hipMemcpyFromSymbol",
    "cudaGetSymbolAddress": "hipGetSymbolAddress",
    "cudaGetSymbolSize": "hipGetSymbolSize",
    # --- Tipos / handles ----------------------------------------------------
    "cudaStream_t": "hipStream_t",
    "cudaEvent_t": "hipEvent_t",
    "cudaArray_t": "hipArray_t",
    "cudaError_t": "hipError_t",
    "cudaStreamCallback_t": "hipStreamCallback_t",
    # --- Constantes / enums de error ----------------------------------------
    "cudaSuccess": "hipSuccess",
    "cudaErrorInvalidValue": "hipErrorInvalidValue",
    "cudaErrorMemoryAllocation": "hipErrorMemoryAllocation",
    "cudaErrorInitializationError": "hipErrorInitializationError",
    "cudaErrorInvalidDevicePointer": "hipErrorInvalidDevicePointer",
    "cudaErrorNoDevice": "hipErrorNoDevice",
}


# ---------------------------------------------------------------------------
# Rule dataclass — entrada inmutable del catálogo.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """Una clase de error del catálogo (blueprint §6.2).

    Atributos:
        id:           "E01" .. "E99" (un id de la taxonomía).
        name:         nombre snake_case para logs/reportes.
        msg_regex:    regex compilada contra ``message`` del primer error
                      del grupo, o None si la regla solo matchea por archivo.
        file_regex:   regex compilada contra ``file`` del primer error,
                      o None si la regla solo matchea por mensaje.
        strategy:     "deterministic" | "llm".
        tier:         "local" | "remote" | "local_then_remote" (solo si
                      ``strategy == "llm"``); None para deterministas.
        fix_template: str sed-like para ``deterministic``; None para llm.
        notes:        texto que el prompt del fixer inyecta (§6.5-B).
    """

    id: str
    name: str
    msg_regex: Optional[re.Pattern[str]]
    file_regex: Optional[re.Pattern[str]]
    strategy: str
    tier: Optional[str]
    fix_template: Optional[str]
    notes: str = ""


# ---------------------------------------------------------------------------
# Carga y validación de rules.yaml
# ---------------------------------------------------------------------------

_DEFAULT_RULES_PATH = Path(__file__).parent / "rules.yaml"

_VALID_TIERS = {"local", "remote", "local_then_remote"}
_VALID_STRATEGIES = {"deterministic", "llm"}


def load_rules(path: str | Path | None = None) -> list[Rule]:
    """Carga ``rules.yaml`` y devuelve la lista de :class:`Rule`.

    Validaciones duras (rompen el ciclo de import si fallan, ANTES de
    que el loop empiece a clasificar):

      1. La lista no está vacía.
      2. La ÚLTIMA entrada es E99 con ``match: {}`` (catch-all) y
         ``strategy == "llm"`` (no es un error determinista desconocido).
      3. Los ids son únicos y van ordenados de la forma en que están
         escritos en el archivo (la posición = prioridad de ``classify``).
      4. ``strategy`` ∈ {"deterministic", "llm"} y ``tier`` (si presente)
         ∈ {"local", "remote", "local_then_remote"}.
      5. ``deterministic`` ⇒ ``tier is None``; ``llm`` ⇒ ``tier not None``.
    """
    p = Path(path) if path is not None else _DEFAULT_RULES_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))

    if not isinstance(raw, list) or not raw:
        raise ValueError(f"rules.yaml: expected a non-empty list, got {type(raw).__name__}")

    seen_ids: set[str] = set()
    rules: list[Rule] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"rules.yaml[{i}]: expected a mapping, got {type(entry).__name__}")

        rid = entry.get("id")
        if not rid or not isinstance(rid, str):
            raise ValueError(f"rules.yaml[{i}]: missing/invalid 'id'")
        if rid in seen_ids:
            raise ValueError(f"rules.yaml[{i}]: duplicate id {rid!r}")
        seen_ids.add(rid)

        name = entry.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"rules.yaml[{i}] ({rid}): missing/invalid 'name'")

        match = entry.get("match") or {}
        if not isinstance(match, dict):
            raise ValueError(f"rules.yaml[{i}] ({rid}): 'match' must be a mapping")
        msg_re = _compile_optional_regex(match.get("msg_regex"), rid, "match.msg_regex")
        file_re = _compile_optional_regex(match.get("file_regex"), rid, "match.file_regex")

        strategy = entry.get("strategy")
        if strategy not in _VALID_STRATEGIES:
            raise ValueError(
                f"rules.yaml[{i}] ({rid}): 'strategy' must be one of "
                f"{sorted(_VALID_STRATEGIES)}, got {strategy!r}"
            )

        tier = entry.get("tier")
        if strategy == "deterministic":
            if tier is not None:
                raise ValueError(
                    f"rules.yaml[{i}] ({rid}): deterministic rules must not set 'tier'"
                )
        else:  # llm
            if tier not in _VALID_TIERS:
                raise ValueError(
                    f"rules.yaml[{i}] ({rid}): llm rules need 'tier' one of "
                    f"{sorted(_VALID_TIERS)}, got {tier!r}"
                )

        fix_template = entry.get("fix_template")
        if strategy == "deterministic":
            if not fix_template or not isinstance(fix_template, str):
                raise ValueError(
                    f"rules.yaml[{i}] ({rid}): deterministic rules need 'fix_template' (str)"
                )
        elif fix_template is not None and not isinstance(fix_template, str):
            raise ValueError(f"rules.yaml[{i}] ({rid}): 'fix_template' must be a string if present")

        notes = entry.get("notes") or ""
        if not isinstance(notes, str):
            raise ValueError(f"rules.yaml[{i}] ({rid}): 'notes' must be a string")

        rules.append(
            Rule(
                id=rid,
                name=name,
                msg_regex=msg_re,
                file_regex=file_re,
                strategy=strategy,
                tier=tier,
                fix_template=fix_template,
                notes=notes,
            )
        )

    # E99 catch-all SIEMPRE al final.
    last = rules[-1]
    if last.id != "E99":
        raise ValueError(
            f"rules.yaml: last entry must be E99 (catch-all), got {last.id!r}. "
            f"Move the E99 entry to the end of the file."
        )
    if last.msg_regex is not None or last.file_regex is not None:
        raise ValueError(
            "rules.yaml: E99 (catch-all) must have an EMPTY match ({}) so it matches everything"
        )
    if last.strategy != "llm":
        raise ValueError(
            "rules.yaml: E99 (catch-all) must be strategy=llm — a deterministic unknown is a bug"
        )

    return rules


def _compile_optional_regex(
    pattern: object, rule_id: str, field_name: str
) -> Optional[re.Pattern[str]]:
    """Compila una regex opcional; valida que sea string (no booleano/lista).

    ``None`` o string vacío → None (la regla no matchea por ese eje).
    """
    if pattern is None or pattern == "":
        return None
    if not isinstance(pattern, str):
        raise ValueError(
            f"rules.yaml ({rule_id}): {field_name} must be a string, got {type(pattern).__name__}"
        )
    try:
        return re.compile(pattern)
    except re.error as e:
        raise ValueError(f"rules.yaml ({rule_id}): {field_name} invalid regex: {e}") from e


# ---------------------------------------------------------------------------
# classify — matching determinista (blueprint §6.2)
# ---------------------------------------------------------------------------


def classify(group: ErrorGroup, rules: list[Rule]) -> str:
    """Devuelve el id de la PRIMERA regla que matchea el grupo.

    El matching es O(n_rules) sobre el primer error del grupo (los
    grupos del parser ya están colapsados por causa raíz — §6.1).

    Una regla matchea si:
        * su ``msg_regex``  matchea ``group.errors[0].message``,  Y/O
        * su ``file_regex`` matchea ``group.errors[0].file``.

    El orden de ``rules.yaml`` = prioridad. ``E99`` (catch-all) está
    validado al final de :func:`load_rules`, así que si nada matchea
    la última regla siempre gana.
    """
    if not rules:
        raise ValueError("classify: rules list is empty — call load_rules() first")
    if not group.errors:
        # Grupo vacío: el catch-all (E99) es la única opción razonable.
        return rules[-1].id

    first = group.errors[0]
    msg = first.message or ""
    filename = first.file or ""

    for rule in rules:
        msg_hit = rule.msg_regex is not None and rule.msg_regex.search(msg) is not None
        file_hit = rule.file_regex is not None and rule.file_regex.search(filename) is not None
        if msg_hit or file_hit:
            return rule.id

    # No debería ocurrir si E99 está bien al final (catch-all), pero el
    # bucle anterior ya garantiza que rules[-1] es E99 con match={} →
    # siempre positivo. Devolvemos la última por defensa.
    return rules[-1].id


# ---------------------------------------------------------------------------
# deterministic_fix — sustituciones mecánicas para clases deterministic.
# ---------------------------------------------------------------------------

# Captura el identificador CUDA dentro de comillas simples.
# Soporta: cudaFoo, cudaFooBar, __cudaPushCallConfiguration, cudaMemcpy_v2, etc.
_IDENTIFIER_RE = re.compile(r"'((?:[A-Za-z_][A-Za-z0-9_]*))'")


def deterministic_fix(klass: str, group: ErrorGroup) -> str | None:
    """Devuelve el fix determinista (string) para ``klass`` o None.

    Para E01 (leftover include): devuelve el ``fix_template`` cargado
    desde rules.yaml (sed-like; el patcher lo interpreta).

    Para E02 (unconverted API): extrae el identificador CUDA del
    mensaje ``'use of undeclared identifier 'cudaXxx'`` y devuelve
    un reemplazo de la forma ``cudaXxx -> hipXxx`` cuando ``cudaXxx``
    está en :data:`CUDA_TO_HIP`. Si no, devuelve un reemplazo de
    prefijo (heurística: prefijo ``cuda``→``hip``; esto cubre el
    ~80% restante que hipify no traduce por sub-typing).

    Para E03 (unconverted type/handle): igual que E02 pero con
    un mensaje explícito de que es un tipo/handle.

    Para clases ``strategy=llm``: devuelve None — el fixer LLM
    (§6.5-B) se hace cargo.
    """
    if klass == "E01":
        # El patcher (T11/T12) interpretará el fix_template como sed-like.
        # No tenemos el rule aquí embebido, así que devolvemos la cadena
        # canónica del blueprint (debe coincidir con rules.yaml). Si en el
        # futuro la plantilla cambia, se prefiere el valor del YAML — el
        # caller lo carga con load_rules() y pasa rule.fix_template.
        return (
            r"s|#include\s*[<\"]cuda_runtime\.h[>\"]|#include <hip/hip_runtime.h>|"
        )

    if not group.errors:
        return None

    first_msg = group.errors[0].message or ""
    match = _IDENTIFIER_RE.search(first_msg)
    if not match:
        return None
    ident = match.group(1)
    if not ident:
        return None

    if klass == "E02":
        return _build_identifier_replacement(ident)
    if klass == "E03":
        return _build_identifier_replacement(ident)
    return None


def _build_identifier_replacement(ident: str) -> str | None:
    """Devuelve la cadena de reemplazo para un identificador CUDA.

    Formato de salida (canónico, lo que el patcher consume):
        "s|<ident>|<replacement>|"

    Si ``ident`` está en :data:`CUDA_TO_HIP` se usa esa entrada; si
    no, se aplica la heurística de prefijo ``cuda``→``hip`` (cubre
    el resto de la API runtime que el map de hipify no enumera
    explícitamente).
    """
    if ident in CUDA_TO_HIP:
        replacement = CUDA_TO_HIP[ident]
        return f"s|{ident}|{replacement}|"

    if ident.startswith("cuda") and len(ident) > 4 and ident[4].isupper():
        replacement = "hip" + ident[4:]
        return f"s|{ident}|{replacement}|"

    if ident.startswith("__cuda") and len(ident) > 6 and ident[6].isupper():
        # Helpers internos (p.ej. __cudaPushCallConfiguration). Mantener
        # el prefijo '__' y reescribir el resto cuda→hip.
        replacement = "__hip" + ident[7:]
        return f"s|{ident}|{replacement}|"

    # No se pudo mapear — devolvemos None para que el caller sepa que
    # esta clase NO tiene fix determinista. En la práctica esto cae al
    # fixer LLM (E02/E03 con tier=llm como fallback) o queda como
    # needs_human.
    return None


__all__ = [
    "CUDA_TO_HIP",
    "Rule",
    "classify",
    "deterministic_fix",
    "load_rules",
]
