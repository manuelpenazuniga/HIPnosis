"""core.llm.prompts — primitive (L2): exact prompt templates.

INV-9: every prompt that the pipeline sends to an LLM lives in this
file. The two templates below mirror blueprint §6.5 word-for-word;
the :func:`render_*` helpers are the only entry points the build loop
should call. There is no network / control logic here on purpose.

Layering: L2 primitive. Imports stdlib only.
"""

from __future__ import annotations


# --- §6.5-A: classifier --------------------------------------------------

CLASSIFIER_SYSTEM = (
    "Eres un experto en portar CUDA a HIP/ROCm. "
    "Clasifica este grupo de errores de compilación."
)

CLASSIFIER_USER_TEMPLATE = """\
CLASES: {clases_tabla}
ERRORES: {mensajes}
CONTEXTO: {snippet}
Responde SOLO JSON: {{"class": "E05", "confidence": 0.0-1.0, "rationale": "una frase"}}\
"""


# --- §6.5-B: fixer -------------------------------------------------------

FIXER_SYSTEM = (
    "Eres un experto en portar CUDA a HIP/ROCm para GPUs AMD CDNA3 "
    "(MI300X, wavefront de 64 lanes)."
)

FIXER_USER_TEMPLATE = """\
Corrige el siguiente error de compilación. REGLAS:
- Cambia lo MÍNIMO necesario. No refactorices. No cambies lógica no relacionada.
- GPUs AMD: wavefront de 64 (no 32); __ballot devuelve 64 bits; usa __popcll; warpSize es variable runtime.
{class_notes}
- Responde SOLO con bloques FILE/SEARCH/REPLACE (formato de ejemplo abajo). Sin explicación.
ERROR: {error}
ARCHIVO {path} (líneas {a}-{b} de {total}):
{code_window}
{history}\
"""


# --- renderers -----------------------------------------------------------


def render_classifier(
    clases_tabla: str,
    mensajes: list[str],
    snippet: str,
) -> tuple[str, str]:
    """Build the (system, user) pair for the classifier (§6.5-A).

    ``mensajes`` is capped to 5 items — the classifier sees only the
    first 5 error messages of the group, even if the group has more.
    """
    cap = mensajes[:5]
    user = CLASSIFIER_USER_TEMPLATE.format(
        clases_tabla=clases_tabla,
        mensajes=_join_bullets(cap),
        snippet=snippet,
    )
    return CLASSIFIER_SYSTEM, user


def render_fixer(
    error_msgs: list[str],
    path: str,
    code_window: str,
    a: int,
    b: int,
    total: int,
    class_notes: str = "",
    history: str = "",
) -> tuple[str, str]:
    """Build the (system, user) pair for the fixer (§6.5-B).

    ``a``/``b`` delimit the visible code window inside the file;
    ``total`` is the full file's line count. ``class_notes`` is the
    per-class guidance injected from ``rules.yaml`` (empty string when
    the class has none). ``history`` is the previous attempt's outcome,
    only populated on retries.
    """
    user = FIXER_USER_TEMPLATE.format(
        class_notes=class_notes,
        error=_join_bullets(error_msgs),
        path=path,
        a=a,
        b=b,
        total=total,
        code_window=code_window,
        history=history,
    )
    return FIXER_SYSTEM, user


# --- helpers -------------------------------------------------------------


def _join_bullets(items: list[str]) -> str:
    if not items:
        return "(sin mensajes)"
    return "\n".join(f"- {m}" for m in items)
