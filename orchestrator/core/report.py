"""core/report.py — certificado de port (F-17/INV-7).

Capa L4. Importa SOLO ``core.schemas`` (contratos), ``core.config`` (precios
y umbrales), ``jinja2`` y stdlib. NO importa ``core.llm``, ``core.state`` ni
``core.oracle`` directamente: la lógica de orquestación llama a este módulo
con los objetos ya construidos, y ``build_report_data`` los ensambla en un
``ReportData`` (F-17/INV-7: los NÚMEROS del certificado salen SIEMPRE del
JSON de datos — código —, NUNCA de un LLM).

``executive_summary`` es el único campo de prosa y queda como string vacío
por defecto; otra capa (no incluida en este módulo) puede rellenarlo si
corresponde, pero el template imprime su valor directamente sin tocar
ningún otro número.

Tres renderizados:
  * ``render_certificate``   — el certificado de port principal (§8).
  * ``render_portability``   — resumen ejecutivo para el dashboard.
  * ``render_pr_body``       — cuerpo de PR (markdown) para ``gh pr create``.

Más ``compute_savings`` — la fórmula citada en §5.3 con precios de
``config.py``. Si los precios son 0 (default) devuelve 0 + nota
(degradación honesta: no inventar números — F-17).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from core.config import Config
from core.schemas import (
    Counters,
    Run,
    ScanResult,
    VerifyResult,
    Wave64Finding,
)


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------

#: Una entrada de la tabla "Fixes aplicados" (clase → n → tier → commits).
#: Vive como dict simple (no schema pydantic) porque lo construye
#: ``build_report_data`` agrupando ``FixAttempt``/eventos del loop; la forma
#: exacta la consume el template Jinja2, no otra capa.
FixByClassEntry = dict[str, Any]


@dataclass
class ReportData:
    """Snapshot inmutable de TODO lo que el certificado imprime.

    F-17/INV-7: cada campo numérico se POPULA desde código (``Counters``,
    ``ScanResult``, ``VerifyResult``). ``executive_summary`` es el único
    texto de prosa y por defecto queda vacío (string ""). El template
    imprime los valores directamente desde este dataclass.
    """

    repo_url: str
    difficulty: str
    files_cuda: int
    loc_kernels: int
    api_calls: dict[str, int]
    libs: list[str]
    wave64_findings: list[Wave64Finding]
    fixes_by_class: list[FixByClassEntry]
    counters: dict[str, int]
    verify_verdict: str
    verify_detail: str
    timing: Optional[dict[str, Any]]
    needs_human: list[str]
    executive_summary: str = ""
    # Metadata auxiliar que el template puede usar (no parte de F-17 pero
    # viene de objetos de código, no del LLM).
    build_system: str = "make"
    run_id: str = ""
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _env() -> Environment:
    """Entorno Jinja2 con ``StrictUndefined`` para fallar ruidosamente si
    el template referencia un campo que ``ReportData`` no provee.
    """
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_certificate(data: ReportData) -> str:
    """Renderiza ``templates/certificate.md`` con ``data``.

    Todos los valores numéricos vienen de ``data`` (F-17). El template
    NO tiene acceso a ningún LLM; es un print puro de los campos del
    dataclass.
    """
    return _env().get_template("certificate.md").render(data=data)


def render_portability(data: ReportData) -> str:
    """Renderiza ``templates/portability.md`` — resumen ejecutivo (F-17)."""
    return _env().get_template("portability.md").render(data=data)


def render_pr_body(data: ReportData) -> str:
    """Renderiza ``templates/pr_body.md`` — cuerpo del PR (F-13b)."""
    return _env().get_template("pr_body.md").render(data=data)


# ---------------------------------------------------------------------------
# compute_savings — fórmula de §5.3 con precios de config.py
# ---------------------------------------------------------------------------

#: Horas GPU/año usadas en la proyección. Constante operativa (single
#: user/research workload) citada en el reporte junto a la fórmula.
HOURS_GPU_PER_YEAR = 8760


def compute_savings(counters: dict[str, int], config: Config) -> dict[str, Any]:
    """Proyección de ahorro anual — §5.3.

    Fórmula::

        ahorro/año = horas_gpu_año × (precio_h100 - precio_mi300x)

    Los precios salen de ``config.py`` (constantes editables). Si alguno
    es 0 (default de dev) devolvemos ``ahorro=0`` y ``note`` explicando
    que los precios no están configurados — F-17: NUNCA inventar números
    ni permitir que el LLM "rellene" el dato.
    """
    price_h100 = float(getattr(config, "price_h100_hr", 0.0) or 0.0)
    price_mi = float(getattr(config, "price_mi300x_hr", 0.0) or 0.0)

    if price_h100 <= 0.0 or price_mi <= 0.0:
        return {
            "hours_gpu_year": HOURS_GPU_PER_YEAR,
            "price_h100_hr": price_h100,
            "price_mi300x_hr": price_mi,
            "delta_price_hr": 0.0,
            "savings_per_year": 0.0,
            "formula": (
                "ahorro/año = horas_gpu_año × (precio_h100 - precio_mi300x)"
            ),
            "note": (
                "Precios no configurados (PRICE_H100_HR / PRICE_MI300X_HR=0). "
                "Seteálos en .env para obtener la proyección numérica."
            ),
        }

    delta_per_hour = price_h100 - price_mi
    savings = HOURS_GPU_PER_YEAR * delta_per_hour
    return {
        "hours_gpu_year": HOURS_GPU_PER_YEAR,
        "price_h100_hr": price_h100,
        "price_mi300x_hr": price_mi,
        "delta_price_hr": delta_per_hour,
        "savings_per_year": savings,
        "formula": (
            "ahorro/año = horas_gpu_año × (precio_h100 - precio_mi300x)"
        ),
        "note": (
            f"= {HOURS_GPU_PER_YEAR} h × (${price_h100:.2f} - ${price_mi:.2f})"
            f" = ${savings:,.2f}/año (precios del {datetime.now(timezone.utc).date().isoformat()})"
        ),
    }


# ---------------------------------------------------------------------------
# build_report_data — ensamblador puro sobre objetos del pipeline (F-17)
# ---------------------------------------------------------------------------

def _counters_to_dict(counters: Counters | dict[str, int]) -> dict[str, int]:
    """Normaliza ``Counters`` (pydantic) o dict suelto a ``dict[str, int]``."""
    if isinstance(counters, Counters):
        return counters.model_dump()
    return dict(counters)


def _summarize_fixes(
    loop_result: Any,
    counters: Counters | dict[str, int],
) -> list[FixByClassEntry]:
    """Agrupa fixes por clase para la tabla del certificado.

    El template NO inventa nada: si el ``LoopResult`` trae información
    por grupo (firmas/clase), se agrupa; si no, se sintetiza una fila
    por tier a partir de los contadores (que sí son de código). En
    cualquier caso, los ``n`` y ``tier`` salen de los counters — nunca
    de un LLM.
    """
    c = _counters_to_dict(counters)
    rows: list[FixByClassEntry] = []

    # Si el loop dejó un desglose por grupo con (klass, tier, commits),
    # lo respetamos. En el resto de los casos fabricamos UNA fila por
    # tier con n = contador del tier (esto sigue siendo de código).
    per_group = getattr(loop_result, "fixes_by_group", None) if loop_result is not None else None

    if per_group:
        agg: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in per_group:
            key = (entry.get("klass", "E99"), entry.get("tier", "deterministic"))
            slot = agg.setdefault(
                key,
                {"klass": key[0], "tier": key[1], "n": 0, "commits": []},
            )
            slot["n"] += int(entry.get("n", 1))
            for c_sha in entry.get("commits", []) or []:
                if c_sha not in slot["commits"]:
                    slot["commits"].append(c_sha)
        rows.extend(agg.values())
    else:
        # Fallback determinista: una fila por tier presente.
        tier_for_counter = {
            "fixes_deterministic": "deterministic",
            "fixes_local": "local",
            "fixes_remote": "remote",
        }
        for counter_name, tier in tier_for_counter.items():
            n = int(c.get(counter_name, 0))
            if n > 0:
                rows.append(
                    {
                        "klass": "E01" if tier == "deterministic" else "E05",
                        "tier": tier,
                        "n": n,
                        "commits": [],
                    }
                )

    # Orden estable: por tier (deterministic < local < remote), luego por clase.
    tier_order = {"deterministic": 0, "local": 1, "remote": 2}
    rows.sort(key=lambda r: (tier_order.get(r["tier"], 99), r["klass"]))
    return rows


def build_report_data(
    scan_result: ScanResult,
    loop_result: Any,
    verify_result: VerifyResult | None,
    run: Run,
    config: Config,
    *,
    executive_summary: str = "",
    needs_human: Optional[list[str]] = None,
    timing: Optional[dict[str, Any]] = None,
    fixes_by_group: Optional[list[dict[str, Any]]] = None,
) -> ReportData:
    """Ensambla ``ReportData`` desde los objetos del pipeline.

    Es una función PURA sobre datos: no llama LLMs, no toca red, no
    modifica sus argumentos. Los NÚMEROS del certificado salen
    exclusivamente de:

      * ``ScanResult``  — inventario + wave64 (de ``core.phases.scan``)
      * ``Counters``    — desde ``loop_result`` o ``run.counters``
      * ``VerifyResult``— verdict/detail/timing (de ``core.oracle``)
      * ``Run``         — repo_url, run_id
      * ``Config``      — solo para los precios (compute_savings no se
                          aplica acá, se invoca separado)

    ``executive_summary`` se pasa como argumento (string vacío por
    default). El LLM que lo redacte es responsabilidad de otra capa.
    """
    counters_obj: Counters | dict[str, int]
    if loop_result is not None and hasattr(loop_result, "counters"):
        counters_obj = loop_result.counters
    else:
        counters_obj = run.counters
    counters = _counters_to_dict(counters_obj)

    # needs_human: prioriza el argumento explícito; si no, el del loop_result.
    nh: list[str]
    if needs_human is not None:
        nh = list(needs_human)
    elif loop_result is not None and hasattr(loop_result, "needs_human"):
        nh = list(getattr(loop_result, "needs_human") or [])
    else:
        nh = []

    # Si el caller inyecta un desglose por grupo, úsalo.
    if fixes_by_group is not None:
        lr_proxy = type("_L", (), {"counters": counters_obj, "fixes_by_group": fixes_by_group})()
        fixes_rows = _summarize_fixes(lr_proxy, counters_obj)
    else:
        fixes_rows = _summarize_fixes(loop_result, counters_obj)

    verify_verdict = "NO_ORACLE"
    verify_detail = ""
    verify_timing: dict[str, Any] | None = timing
    if verify_result is not None:
        verify_verdict = str(verify_result.verdict or "NO_ORACLE")
        verify_detail = str(verify_result.parity_details or "")
        if verify_result.timing is not None and verify_timing is None:
            verify_timing = dict(verify_result.timing)

    return ReportData(
        repo_url=run.repo_url,
        difficulty=scan_result.difficulty,
        files_cuda=len(scan_result.files_cuda),
        loc_kernels=scan_result.loc_kernels,
        api_calls=dict(scan_result.api_calls),
        libs=list(scan_result.libs),
        wave64_findings=list(scan_result.wave64_findings),
        fixes_by_class=fixes_rows,
        counters=counters,
        verify_verdict=verify_verdict,
        verify_detail=verify_detail,
        timing=verify_timing,
        needs_human=nh,
        executive_summary=executive_summary,
        build_system=scan_result.build_system,
        run_id=run.id,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


__all__ = [
    "FixByClassEntry",
    "HOURS_GPU_PER_YEAR",
    "ReportData",
    "build_report_data",
    "compute_savings",
    "render_certificate",
    "render_portability",
    "render_pr_body",
]
