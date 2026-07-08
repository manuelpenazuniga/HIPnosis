Trabajás en el worktree actual (rama spike/t16-report). Implementá SOLO esta tarea.

--- TAREA T16: core/report.py + templates Jinja2 — certificado de port (F-17) ---
Capa L4. Importa core.schemas, core.config, jinja2, stdlib. NO importa oracle/llm/state directo.
⛔ F-17/INV-7: los NÚMEROS salen SIEMPRE del JSON de datos (código), NUNCA de un LLM. El LLM solo
redacta prosa alrededor de un JSON que no puede alterar; el template imprime los valores del JSON.

ARCHIVOS: orchestrator/core/report.py
          orchestrator/templates/certificate.md    (Jinja2)
          orchestrator/templates/portability.md     (Jinja2)
          orchestrator/templates/pr_body.md          (Jinja2)
TEST: orchestrator/tests/test_report.py

### report.py:

    @dataclass
    class ReportData:
        # TODO lo que el certificado imprime — SOLO de código (F-17). Campos:
        repo_url: str
        difficulty: str
        files_cuda: int
        loc_kernels: int
        api_calls: dict[str, int]
        libs: list[str]
        wave64_findings: list            # de core.schemas.Wave64Finding
        fixes_by_class: list             # [{"klass":"E01","n":3,"tier":"deterministic","commits":["a1b2"]}]
        counters: dict                   # errors_initial, fixes_local/remote/deterministic, tokens_*, iterations
        verify_verdict: str              # "PASS"|"FAIL"|"NO_ORACLE"
        verify_detail: str
        timing: dict | None
        needs_human: list                # signatures/descripciones sin resolver
        executive_summary: str = ""      # el ÚNICO campo que un LLM puede redactar (prosa)

    def build_report_data(scan_result, loop_result, verify_result, run, ...) -> ReportData:
        # Ensambla ReportData desde los objetos del pipeline (todos son datos/código). NO llama a ningún LLM.

    def render_certificate(data: ReportData) -> str:
        # Renderiza templates/certificate.md con Jinja2. Los números vienen de `data` (F-17).
    def render_portability(data: ReportData) -> str: ...   # portability.md
    def render_pr_body(data: ReportData) -> str: ...       # pr_body.md

    def compute_savings(counters, config) -> dict:
        # Proyección de ahorro (§5.3): ahorro/año = horas_gpu_año × (precio_h100 - precio_mi300x),
        # con precios de config (config.price_h100_hr, config.price_mi300x_hr). Devolvé el dict con la
        # fórmula y las constantes citadas. Si los precios son 0 (default), devolvé 0 y una nota.

### Templates (Jinja2) — certificate.md secciones OBLIGATORIAS (§8):
1. Resumen ejecutivo ({{ data.executive_summary }} — puede estar vacío).
2. Inventario (files_cuda, loc_kernels, api_calls, libs, difficulty).
3. Fixes aplicados: TABLA clase → n → tier → commits (de fixes_by_class).
4. Hallazgos wave64: tabla file:line → pattern_id → severidad → explicación (de wave64_findings).
5. Verificación: verdict + detalle + tolerancias.
6. Timing (si hay).
7. **"Limitaciones y NEEDS_HUMAN"** — SECCIÓN OBLIGATORIA aunque esté vacía (degradación honesta, INV-5).
8. Métricas de eficiencia: % fixes locales = (fixes_deterministic+fixes_local)/total*100; tokens local vs remoto.

### Test test_report.py:
- build_report_data desde objetos mínimos → ReportData con los campos poblados.
- render_certificate → un str markdown que CONTIENE: el verdict, la tabla de fixes, los hallazgos wave64,
  la sección "NEEDS_HUMAN" (aunque vacía), y el % de fixes locales calculado del counters.
- ⚠️ TEST F-17: construí ReportData con counters conocidos (p.ej. fixes_deterministic=6, fixes_local=2),
  renderizá, y verificá que el % local (80%) aparece EXACTO — el número sale del código, no inventado.
- compute_savings con precios 0 → 0 + nota; con precios seteados → la fórmula correcta.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_report.py -q` verde (incl. test F-17 del % exacto).
2. F-17: TODOS los números del certificado salen de ReportData (código). executive_summary es el único texto de prosa.
3. La sección "Limitaciones y NEEDS_HUMAN" SIEMPRE está (aunque vacía).
4. report.py NO llama a ningún LLM (build_report_data es puro sobre datos).

Reglas duras:
- F-17/INV-7: números solo de código. Prompts NO van acá (§6.5 está en prompts.py).
- Templates en orchestrator/templates/ (Jinja2). Al terminar: pytest verde + COMMIT ("feat(core): report.py + templates certificado (F-17) + tests").
- Respuesta CORTA: archivos + output pytest + confirmá el test F-17. Bloqueo: 'BLOCKED | ...' y pará.
