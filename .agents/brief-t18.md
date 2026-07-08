Trabajás en el worktree actual (rama spike/t18-dashboard). Implementá SOLO esta tarea.

--- TAREA T18: dashboard/index.html + dashboard/app.js — dashboard estático (polling 1s) ---
Capa L7: HTML + JS VANILLA. ⛔ SIN build step, SIN framework (no React/Vue/Node), SIN SSE. Solo
polling con fetch cada 1s. Tailwind por CDN está permitido (una etiqueta <script>), nada más.
El dashboard NO importa Python; consume SOLO el JSON del API (contrato de eventos del trace §4.3).

ARCHIVOS: dashboard/index.html, dashboard/app.js   (en la raíz del repo, dir `dashboard/`)

### Contrato del API que consumís (ya existe, NO lo cambies):
- GET /runs/{run_id}/events?after=N  → devuelve lista de eventos JSON. Cada evento tiene:
  "ts" (ISO8601), "run" (id), "ev" (tipo), "_i" (índice de línea, 0-based), + campos según "ev".
  Polea con ?after=<último _i visto> cada 1s; agregá los nuevos de forma INCREMENTAL (no re-render total).
- GET /runs/{run_id}  → metadata del run (id, state, counters, budgets).
- Tipos de evento "ev" y sus campos (blueprint §4.3 — manejá estos):
  - "phase": {phase:"QUEUED|CLONING|SCANNING|PORTING|BUILD_LOOP|RUNNING|PARITY|REPORTING|DONE|DONE_PARTIAL|FAILED"}
  - "scan": {files_cuda, loc_kernels, build_system, difficulty, api_calls:{...}}
  - "wave64": {file, line, pattern} (pattern = "W01".."W07")
  - "build": {iteration, errors, delta}
  - "classify": {sig, klass, tier, confidence}
  - "fix": {sig, tier:"deterministic|local|remote", applied, delta, commit, tokens}
  - "verify": {verdict:"PASS|FAIL|NO_ORACLE", detail}
  - "report": {fixes_deterministic, fixes_local, fixes_remote, tokens_local, tokens_remote, errors_initial, iterations, wave64_findings}
  - (ignorá con gracia cualquier "ev" desconocido: no rompas)

### Qué mostrar (el dashboard cuenta la historia del port):
1. **Timeline de fases** horizontal o vertical: las 9 fases, resaltando la actual (del último "phase").
2. **Contador de errores DESCENDENTE**: gráfico/lista de builds (iteration → errors), mostrando cómo
   baja de errors_initial a 0. Es el momento visual clave.
3. **Badge "% resuelto localmente"**: de los counters/report, (fixes_deterministic+fixes_local) /
   total_fixes * 100. Y tokens local vs remoto. (la narrativa de eficiencia Track 1).
4. **Hallazgos wave64**: tabla file:line → pattern (W0x). Es el arma diferencial: destacala.
5. **Tabla de fixes**: clase (klass) → tier → commit. Contadores por tier.
6. **Veredicto de verificación**: PASS/FAIL/NO_ORACLE bien grande al final.
El run_id: tomalo de un query param ?run=<id> (default "run_bsw01a2" que es el trace demo de replay).

### Cómo probarlo SIN backend corriendo:
Incluí en app.js un modo que, si fetch al API falla (no hay server), cargue un JSON local de ejemplo
para que el layout se pueda ver. Pero el camino principal es fetch al API real.
Podés mirar el trace demo real en `fixtures/demo-run.jsonl` (raíz del repo) para calibrar el render:
tiene un run bsw-cuda completo (QUEUED→DONE, wave64 W01/W02, 8→0 errores, verify PASS).

--- FIN TAREA ---

Criterios de aceptación:
1. `dashboard/index.html` abre en un browser y `app.js` polea GET /runs/<id>/events?after=N cada 1s,
   renderizando incrementalmente (verificá la lógica de `after` = último _i visto).
2. Maneja los 8 tipos de "ev" de arriba + ignora desconocidos sin romper. Sin errores de consola.
3. SIN build step, SIN framework JS (solo vanilla + Tailwind CDN). SIN SSE.
4. Muestra las 6 secciones (timeline, contador descendente, badge % local, wave64, fixes, verdict).

Reglas duras:
- F-15: polling JSON cada 1s con ?after=N. Nada de websockets/SSE.
- L7: cero Python; consumís solo JSON del API. No inventes endpoints nuevos.
- Al terminar: COMMIT ("feat(dashboard): timeline + contador errores + badge %local + wave64 (polling 1s)").
- Respuesta CORTA: archivos creados + cómo lo probaste. Bloqueo: 'BLOCKED | ...' y pará.
