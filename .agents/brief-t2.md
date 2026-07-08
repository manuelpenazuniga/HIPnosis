Trabajás en el worktree actual (rama spike/t2-trace). Implementá SOLO esta tarea.

--- TAREA T2: core/trace.py — writer/reader JSONL append-only del trace del run ---
Capa L1: importa SOLO de core.schemas (y stdlib json/os/datetime). NO importa config, phases,
oracle, llm, state. Es la fuente de verdad de eventos que el dashboard poleará.

ARCHIVO DE PRODUCTO: orchestrator/core/trace.py    +    TEST: orchestrator/tests/test_trace.py

### Contrato de trace.py:

    class TraceWriter:
        def __init__(self, path: str, run_id: str): ...
            # path al archivo trace.jsonl del run; run_id se inyecta en cada evento.

        def emit(self, ev: str, **fields) -> None: ...
            # Escribe UNA línea JSON al final del archivo (append-only, con fsync/flush).
            # La línea es: {"ts": <ISO8601 UTC>, "run": <run_id>, "ev": <ev>, **fields}
            # "ts" se genera acá con datetime.now(timezone.utc).isoformat() si no viene en fields.
            # Debe ser append puro: abrir en modo "a", escribir json.dumps(obj)+"\n", flush.
            # INVARIANTE (INV-4): el evento se persiste ANTES de que el caller actúe; no bufferees.

    def read_events(path: str, after: int = -1) -> list[dict]: ...
        # Lee el archivo y devuelve los eventos cuyo ÍNDICE DE LÍNEA (0-based) es > after.
        # after=-1 (default) devuelve TODOS. Esto implementa GET /events?after=N del dashboard
        # (N = índice de la última línea ya vista). Ignorá líneas vacías. Cada dict lleva su
        # índice accesible: agregá a cada evento devuelto la clave "_i" = índice de línea (int),
        # para que el dashboard sepa el próximo 'after'. Si el archivo no existe → [].

Formato de evento de referencia (blueprint §4.3), NO cambies estos nombres de clave:
    {"ts":"...","run":"run_ab12cd34","ev":"phase","phase":"BUILD_LOOP"}
    {"ts":"...","run":"...","ev":"build","iteration":3,"errors":17,"delta":-9}
    {"ts":"...","run":"...","ev":"fix","sig":"...","tier":"local","applied":true,"delta":-3,"commit":"a1b2c3","tokens":412}

### Test test_trace.py (pytest, tmp_path):
- emit 3 eventos variados (phase, build, fix), leé el archivo crudo: son 3 líneas JSON válidas,
  cada una con "ts", "run", "ev".
- read_events(path) devuelve 3 dicts con "_i" 0,1,2.
- read_events(path, after=0) devuelve 2 (índices 1,2).
- read_events(path, after=2) devuelve [] (nada nuevo).
- read_events("/no/existe.jsonl") devuelve [].
- "ts" es un ISO8601 parseable (datetime.fromisoformat no explota).

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_trace.py -q` verde.
2. trace.py importa solo core.schemas + stdlib. NO importa config/phases/oracle/llm/state (grep vacío).
3. emit es append puro (modo "a", flush). read_events respeta la semántica after=índice.

Reglas duras:
- INV-4: append-only, persistir antes de actuar. Nada de reescribir el archivo entero.
- Capa L1: no importes hacia arriba.
- Al terminar: pytest verde + COMMIT ("feat(core): trace jsonl writer/reader + tests").
- Respuesta final CORTA: archivos + output del pytest. Si te bloqueás: 'BLOCKED | ...' y pará.
