Trabajás en el worktree actual (rama spike/t9-api). Implementá SOLO esta tarea.

--- TAREA T9: app/main.py + app/api.py — capa HTTP FastAPI (foco: BANCAR el modo replay) ---
Capa L6. Importa core.schemas, core.config, core.trace (reader). ⛔ PROHIBIDO importar phases u
oracle directo (AD-3: todo control pasa por state). state.py aún NO existe (es otra tarea): por eso
esta tarea usa un RunStore MÍNIMO en memoria que la tarea de state reemplazará luego. No lo bloquees.

ARCHIVOS: orchestrator/app/main.py, orchestrator/app/api.py, orchestrator/app/store.py
TEST: orchestrator/tests/test_api.py   (usá fastapi.testclient.TestClient)

### store.py — RunStore mínimo (interfaz + impl en memoria; state.py la sustituirá):
    from core.schemas import Run
    class RunStore:               # protocolo mínimo
        def create(self, repo_url: str) -> Run: ...   # genera id "run_"+8hex, state=QUEUED, budgets/counters default
        def get(self, run_id: str) -> Run | None: ...
        def list(self) -> list[Run]: ...
    class InMemoryRunStore(RunStore): ...   # dict interno; para generar el id usá uuid4().hex[:8]
    (budgets: leé de core.config.budgets(); counters: Counters() por defecto)

### api.py — router FastAPI (APIRouter):
    POST /runs           body {"repo_url": "..."} → crea run vía store, devuelve el Run (200). ⛔ NO
                         ejecuta el pipeline acá (eso es de state, otra tarea): solo registra QUEUED.
    GET  /runs           → lista de runs.
    GET  /runs/{run_id}  → el Run o 404.
    GET  /runs/{run_id}/events?after=N  → EL ENDPOINT CLAVE DEL DASHBOARD/REPLAY.
                         Lee el trace jsonl del run con core.trace.read_events(path, after=N) y
                         devuelve la lista de eventos (cada uno con su "_i"). after default = -1.
                         La ruta del trace por run: usá una función resolvible por config/const:
                         workspaces/<run_id>/trace.jsonl  (para replay, el archivo puede ser un
                         trace grabado copiado ahí). Si no existe el trace → devolvé [] (200), no 404.
    GET  /healthz        → {"ok": true}

### main.py — app FastAPI:
    - crea FastAPI(), incluye el router de api.py.
    - monta el dashboard estático (dir ../dashboard o orchestrator-relativo) en "/" si existe
      (StaticFiles); si no existe el dir, no falla (el dashboard es otra tarea).
    - instancia UN InMemoryRunStore y lo inyecta al router (p.ej. app.state.store o dependencia).

### Test test_api.py (TestClient, sin servidor real):
- POST /runs {"repo_url":"https://x/y"} → 200, devuelve id que empieza con "run_", state=="QUEUED".
- GET /runs/{id} del creado → 200 mismo id; GET /runs/inexistente → 404.
- GET /runs/{id}/events sobre un run cuyo trace escribiste a mano (usá core.trace.TraceWriter a un
  path temporal y apuntá el resolver del run a ese path, o monkeypatch): devuelve los eventos, y
  con ?after=0 devuelve los posteriores. Trace inexistente → [] y 200.
- GET /healthz → 200 {"ok":true}.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_api.py -q` verde (necesitás fastapi instalado; si
   falta en el venv, PARÁ y reportá 'BLOCKED | ENV: falta fastapi en el venv' — NO instales vos).
2. api.py/main.py NO importan phases ni oracle (grep vacío). El control de runs pasa por store (futuro state).
3. GET events usa core.trace.read_events (NO reimplementa el parseo del jsonl).

Reglas duras:
- AD-3: la capa HTTP nunca ejecuta fases; POST /runs solo encola (QUEUED). state.py hará el driving.
- INV-8: nombres de campo del Run intactos (vienen de schemas).
- Al terminar: pytest verde + COMMIT ("feat(api): FastAPI runs + events?after=N (replay) + store en memoria").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
