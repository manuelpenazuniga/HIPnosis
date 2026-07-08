Trabajás en el worktree actual (rama spike/t8-state). Implementá SOLO esta tarea. Es el WATCHPOINT
de arquitectura: state.py es el ÚNICO driver de fases (AD-3). Cuidá la dirección de dependencias.

--- TAREA T8: core/state.py — máquina de estados (FSM) + persistencia SQLite + driver de fases ---
Capa L5. Importa core.schemas, core.config, core.trace, core.phases.* y stdlib (sqlite3, json,
uuid). ⛔ AD-3: state.py es el ÚNICO que llama a las fases; NADIE más las orquesta. La capa api
(app/) llama a state, nunca a phases directo. state NO importa app.

ARCHIVOS: orchestrator/core/state.py    TEST: orchestrator/tests/test_state.py

### Parte A — SqliteRunStore (reemplaza al InMemoryRunStore respetando el MISMO protocolo):
    class SqliteRunStore:
        def __init__(self, db_path: str = ":memory:"): ...   # crea tabla runs si no existe
        def create(self, repo_url: str) -> Run: ...          # id "run_"+uuid4().hex[:8], state=QUEUED,
                                                             # budgets de config.budgets(), Counters()
        def get(self, run_id: str) -> Run | None: ...
        def list(self) -> list[Run]: ...
        def put(self, run: Run) -> Run: ...                  # upsert (para replay/seed)
        def update_state(self, run_id: str, state: str) -> None: ...
        def update_counters(self, run_id: str, counters: Counters) -> None: ...
    # Tabla runs: id TEXT PK, repo_url TEXT, state TEXT, budgets_json TEXT, counters_json TEXT.
    # Serializá budgets/counters con model_dump_json (pydantic). Debe satisfacer el protocolo
    # RunStore de app/store.py (create/get/list/put) para ser drop-in del InMemoryRunStore.

### Parte B — el DRIVER de la FSM (AD-3: la única autoridad de control):
    FSM (blueprint §3): QUEUED → CLONING → SCANNING → PORTING → BUILD_LOOP → RUNNING → PARITY →
                        REPORTING → DONE.  (BUILD_LOOP sin progreso/presupuesto → REPORTING → DONE_PARTIAL;
                        excepción no manejada → FAILED(reason)).

    PhaseHandler = Callable[[PipelineContext], None]   # cada fase recibe el contexto y actúa

    @dataclass
    class PipelineContext:
        run: Run
        repo_dir: str
        config: Config
        store: SqliteRunStore
        trace: TraceWriter
        scan_result: ScanResult | None = None   # lo llena SCANNING
        # (campos que las fases van poblando)

    def default_handlers(config) -> dict[str, PhaseHandler]:
        # Mapea CADA estado-fase a su handler. Los que YA existen se cablean:
        #   SCANNING -> corre core.phases.scan.scan(ctx.repo_dir) y guarda en ctx.scan_result
        #   PORTING  -> core.phases.port.port(...)
        # Los que AÚN NO existen (BUILD_LOOP=loop, RUNNING/PARITY=verify, REPORTING=ship) → STUB:
        #   un handler que emite un evento al trace y no hace más (marcá "stub" en el evento).
        #   Estos stubs se REEMPLAZAN cuando aterricen T14 (loop), T15 (verify), T16/T17 (report/ship).
        #   Dejá EXPLÍCITO el seam: default_handlers acepta overrides para inyectar los reales/mocks.
        # CLONING -> clona el repo con core.gitrepo.GitRepo.clone (o, en test/mock, un dir dado).

    def run_pipeline(run_id: str, store, config, trace, handlers=None, repo_dir=None) -> Run:
        # El corazón del driver:
        # 1. Cargar el run. handlers = handlers or default_handlers(config).
        # 2. Recorrer la secuencia de estados. Por CADA transición:
        #    a. INV-4: emitir evento {"ev":"phase","phase":<nuevo estado>} al trace ANTES de ejecutar.
        #    b. store.update_state(run_id, estado).
        #    c. ejecutar handlers[estado](ctx) si existe.
        # 3. Si un handler lanza excepción no manejada → estado FAILED, guardar reason en el trace,
        #    NO relanzar (DONE_PARTIAL/FAILED son finales legítimos — INV-5). Nunca dejar el run "colgado".
        # 4. Estado final DONE (o DONE_PARTIAL/FAILED). Devolver el Run actualizado.
        # NO implementes reanudación fina intra-fase (sobreingeniería, §3): re-ejecutar la fase entera OK.

### Test test_state.py (con stubs/mocks — SIN red, SIN GPU, SIN hipify):
- SqliteRunStore in-memory: create/get/list/put/update_state/update_counters round-trip; satisface
  el protocolo (create devuelve QUEUED con budgets/counters).
- run_pipeline con handlers STUB (o mocks que solo marcan que se llamaron): un run recorre
  QUEUED→...→DONE, y el trace tiene UN evento "phase" por transición EN ORDEN (verificá la secuencia).
- INV-4: el evento phase se emite ANTES de ejecutar el handler (podés hacer que un handler falle y
  verificar que su evento phase ya está en el trace).
- INV-5: un handler que lanza excepción → estado final FAILED (o DONE_PARTIAL), NO propaga la excepción,
  el run queda persistido con ese estado.
- Integración liviana: con el handler real de SCANNING sobre fixtures/scan_repo (ya existe), ctx.scan_result
  se puebla.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_state.py -q` verde.
2. AD-3: state.py es el único driver; NO importa app. api llamará a state (no al revés).
3. INV-4: evento phase ANTES de ejecutar cada fase (test lo verifica). INV-5: FAILED/DONE_PARTIAL no propagan excepción.
4. SqliteRunStore satisface el protocolo RunStore (drop-in del InMemoryRunStore).

Reglas duras:
- AD-3: la FSM es la ÚNICA autoridad de control. Los LLM/fases no deciden el flujo (INV-1).
- INV-4 (trace antes de actuar), INV-5 (finales honestos), §3 (no reanudación intra-fase).
- Umbrales desde config (INV-9). Stubs para fases no implementadas, con seam para inyectar los reales.
- Al terminar: pytest verde + COMMIT ("feat(core): state FSM + SqliteRunStore + driver de fases + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
