ENTORNO: para verificar usá el intérprete del venv compartido (ya tiene pydantic, gitpython, pytest):
  /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python
Ejemplo: cd orchestrator && /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python -m pytest tests/ -q   |   /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python -c "from core.schemas import Run; print('ok')"
NO crees otro venv ni instales deps. NO uses 'python' pelado (el sistema no tiene las libs).

Trabajás en el worktree actual (rama spike/t1-contrato). Implementá SOLO esta tarea.

--- TAREA T1: config.py + schemas.py + .env.example (el contrato congelado del sistema) ---
Creá TRES archivos. Son la base de la que depende TODO el proyecto: nombres de campo exactos,
sin agregar ni renombrar nada (el dashboard y los templates dependen de ellos).

ARCHIVOS A TOCAR (exactamente estos, ninguno más):
1. orchestrator/core/schemas.py
2. orchestrator/core/config.py
3. orchestrator/.env.example

### 1) orchestrator/core/schemas.py — modelos Pydantic v2. COPIÁ estos contratos AL PIE DE LA
LETRA (agregá tipos auxiliares Budgets/Counters que faltan, con los campos que se mencionan en
los comentarios). Usá `from pydantic import BaseModel`. NADA de imports internos del proyecto
(este archivo es una HOJA del grafo de dependencias: no importa de config ni de ningún módulo).

    class Budgets(BaseModel):
        max_iterations: int
        max_attempts_per_group: int
        max_errors_parsed: int

    class Counters(BaseModel):
        errors_initial: int = 0
        errors_current: int = 0
        fixes_local: int = 0
        fixes_remote: int = 0
        fixes_deterministic: int = 0
        tokens_local: int = 0
        tokens_remote: int = 0
        iterations: int = 0

    class Run(BaseModel):
        id: str                    # "run_" + 8 hex
        repo_url: str
        state: str                 # ver RunState abajo
        budgets: Budgets
        counters: Counters

    class Wave64Finding(BaseModel):
        file: str; line: int; pattern_id: str    # "W01".."W07"
        snippet: str; severity: str              # "correctness" | "suspicious"
        explanation: str                         # texto fijo del catálogo, NO generado por LLM

    class ScanResult(BaseModel):
        files_cuda: list[str]; loc_kernels: int
        api_calls: dict[str, int]          # {"cudaMemcpy": 12, ...}
        libs: list[str]                    # ["cublas", "curand"]
        build_system: str                  # "make" | "cmake"
        wave64_findings: list[Wave64Finding]
        difficulty: str                    # "easy" | "medium" | "hard"

    class BuildError(BaseModel):
        file: str; line: int; col: int; message: str
        signature: str             # clave de dedupe/historial

    class ErrorGroup(BaseModel):
        signature: str; errors: list[BuildError]
        klass: str | None = None   # id de taxonomía "E01".. (None hasta clasificar)
        attempts: int = 0; status: str = "open"   # "open" | "fixed" | "needs_human"

    class FixAttempt(BaseModel):
        group_signature: str; tier: str        # "deterministic" | "local" | "remote"
        patch: str                             # bloques SEARCH/REPLACE crudos
        applied: bool; build_delta: int        # errores_después - errores_antes
        commit_sha: str | None = None; tokens: int = 0

    class VerifyResult(BaseModel):
        ran: bool; exit_code: int
        verdict: str               # "PASS" | "FAIL" | "NO_ORACLE"
        parity_details: str
        timing: dict | None = None

Además, por decisión de arquitectura AD-2, agregá acá (NO en oracle/base.py) los resultados del
oráculo, que son contrato compartido por real/mock/loop/trace:

    class BuildResult(BaseModel):
        ok: bool                   # count == 0
        count: int                 # nº de errores parseados (0 = build limpio)
        raw_output: str            # stdout+stderr crudo del compilador (insumo de errparse)
        returncode: int

    class RunResult(BaseModel):
        ran: bool
        exit_code: int
        stdout: str
        timing: dict | None = None

Y los estados de la FSM como constantes (un módulo, no un Enum de valores raros — los strings
son el contrato del trace/dashboard):

    class RunState:
        QUEUED = "QUEUED"; CLONING = "CLONING"; SCANNING = "SCANNING"; PORTING = "PORTING"
        BUILD_LOOP = "BUILD_LOOP"; RUNNING = "RUNNING"; PARITY = "PARITY"
        REPORTING = "REPORTING"; DONE = "DONE"; DONE_PARTIAL = "DONE_PARTIAL"
        FAILED = "FAILED"
        ALL = [QUEUED, CLONING, SCANNING, PORTING, BUILD_LOOP, RUNNING, PARITY, REPORTING,
               DONE, DONE_PARTIAL, FAILED]

### 2) orchestrator/core/config.py — ÚNICA fuente de umbrales y env vars. Función pura de lectura
de entorno; NO importa nada interno salvo que necesite Budgets de schemas (permitido: schemas es
hoja). Leé con os.getenv y defaults. Exponé un objeto/dataclass `Config` con AL MENOS estos
campos, mapeados 1:1 a estas env vars:

    ORACLE_MODE          -> oracle_mode        default "mock"   # "real"|"mock"|"replay"
    LOCAL_LLM_BASE_URL   -> local_llm_base_url default "http://vllm:8000/v1"
    LOCAL_LLM_MODEL      -> local_llm_model    default "google/gemma-3-27b-it"
    REMOTE_LLM_BASE_URL  -> remote_llm_base_url default "https://api.fireworks.ai/inference/v1"
    REMOTE_LLM_MODEL     -> remote_llm_model   default ""       # id exacto se fija día 1
    FIREWORKS_API_KEY    -> fireworks_api_key  default ""
    HF_TOKEN             -> hf_token           default ""
    GITHUB_TOKEN         -> github_token       default ""
    GPU_ARCH             -> gpu_arch           default "gfx942"
    MAX_ITERATIONS       -> max_iterations     default 25   (int)
    MAX_ATTEMPTS_PER_GROUP -> max_attempts_per_group default 3 (int)
    MAX_ERRORS_PARSED    -> max_errors_parsed  default 30   (int)
    CONFIDENCE_THRESHOLD -> confidence_threshold default 0.6 (float)
    PRICE_H100_HR        -> price_h100_hr      default 0.0  (float)
    PRICE_MI300X_HR      -> price_mi300x_hr    default 0.0  (float)

Proveé también un helper `get_config()` que devuelva una instancia leída del entorno, y un
método/función `budgets()` que arme un `Budgets` (de schemas) desde la config. NINGÚN umbral
hardcodeado fuera de este archivo: este es el contrato (INV-9).

### 3) orchestrator/.env.example — TODAS las vars de arriba, comentadas una por una, con los
defaults como valores de ejemplo. Secretos (FIREWORKS_API_KEY, HF_TOKEN, GITHUB_TOKEN) con
valor VACÍO y un comentario "# completar; NUNCA commitear el .env real". Este archivo SÍ se
commitea (.env real está en .gitignore).

--- FIN TAREA ---

Criterios de aceptación (al pie de la letra):
1. `python -c "from core.schemas import Run, ScanResult, BuildError, ErrorGroup, FixAttempt, VerifyResult, BuildResult, RunResult, Wave64Finding, Counters, Budgets, RunState; print('ok')"` corriendo desde orchestrator/ imprime ok.
2. `python -c "from core.config import get_config; c=get_config(); print(c.oracle_mode, c.max_iterations, c.confidence_threshold)"` desde orchestrator/ imprime: mock 25 0.6
3. Todos los nombres de campo coinciden EXACTO con los de arriba (test negativo: no debe existir ningún campo renombrado tipo `errorsInitial` camelCase — son snake_case).
4. schemas.py NO importa config ni ningún módulo del proyecto (es hoja del grafo). config.py NO importa phases/oracle/llm/state.

Reglas duras (INVARIANTES del proyecto — no las violes):
- INV-8: los nombres de campo de schemas y los strings de estado son CONTRATO CONGELADO. No renombres, no agregues campos que no estén acá.
- INV-9: umbrales SOLO en config.py. Nada de constantes mágicas en otro lado.
- NO inventes APIs ni agregues dependencias. NO toques ningún otro archivo. Pydantic v2 ya está en pyproject.
- Si dudás de un tipo, seguí EXACTO lo que está escrito acá; no "mejores" el diseño.
- Al terminar: corré los 2 comandos de aceptación 1 y 2 desde orchestrator/, dejá que impriman lo esperado, y HACÉ COMMIT (`git add -A && git commit -m "feat(core): schemas + config + .env.example (contrato)"`).
- Respuesta final CORTA: qué archivos creaste, y el output literal de los comandos de aceptación. Sin ensayos.
- Si te bloqueás NO adivines: escribí 'BLOCKED | ENV|SPEC|DEPS: <motivo>' y pará.