Trabajás en el worktree actual (rama spike/dash-wow). REDISEÑÁ el dashboard para que sea IMPRESIONANTE
—es lo que ven los jueces de un hackathon (AMD Developer Hackathon, Track 3 Unicorn + premio Gemma).
El actual funciona pero es básico. Objetivo: que se recuerde. SIN build step (F-15): HTML + JS VANILLA +
Tailwind por CDN. Podés agregar highlight.js por CDN para el diff. SIN frameworks, SIN SSE.

ARCHIVOS A REESCRIBIR: dashboard/index.html, dashboard/app.js   (dir dashboard/ en la raíz del repo)

### CONTRATO DE DATOS (endpoints que ya existen — NO los cambies, consumilos):
- `GET /runs/{id}/events?after=N` → lista de eventos JSON del trace (polling cada 1s, incremental
  con after=último `_i` visto). Tipos de "ev" y campos:
  - phase: {phase:"QUEUED|CLONING|SCANNING|PORTING|BUILD_LOOP|RUNNING|PARITY|REPORTING|DONE|DONE_PARTIAL|FAILED"}
  - run_meta: {repo_url, oracle_mode, gpu_arch}
  - scan: {files_cuda, loc_kernels, build_system, difficulty, api_calls:{...}}
  - wave64: {file, line, pattern} (pattern="W01".."W07")
  - build: {iteration, errors, delta}
  - classify: {sig, klass, tier, confidence}
  - fix: {sig, klass, tier:"deterministic|local|remote", applied, delta, commit, tokens}
  - verify: {verdict:"PASS|FAIL|NO_ORACLE", detail}
  - report: {fixes_deterministic, fixes_local, fixes_remote, tokens_local, tokens_remote, errors_initial, iterations, wave64_findings}
  (ignorá "ev" desconocidos sin romper)
- `GET /runs/{id}` → {id, state, counters:{...}, budgets:{...}}
- `GET /runs/{id}/diff` → {diff: "<texto diff unificado CUDA→HIP>"}  ← la transformación REAL del código
- `GET /runs/{id}/certificate` → {markdown: "<certificado en markdown>"}
El run_id: query param ?run=<id>, default "run_bsw01a2" (el trace demo de replay).

### DISEÑO (intención — la historia que cuenta el dashboard):
Marca: AMD = rojo (#ED1C24) como ACENTO (no todo rojo). Tema oscuro pro (slate/zinc-900). Tipografía
system-ui. Verde = éxito (PASS, DONE), rojo = AMD/errores, ámbar = suspicious. Jerarquía clara.

1. **HERO** (arriba, lo primero que se ve):
   - Título "HIPnosis" + tagline "Autonomous CUDA → ROCm/AMD porting agent".
   - Estado del run (badge grande, color por estado; DONE=verde, FAILED=rojo, en curso=azul pulsante).
   - **Fila de 4 MÉTRICAS GRANDES** (cards, número enorme + label):
     (a) **Errores resueltos**: `errors_initial → 0` (de report/build). Con mini-sparkline descendente.
     (b) **Resuelto localmente**: `%` = (fixes_deterministic+fixes_local)/(total fixes)*100. Badge "Gemma 3 · $0 API".
     (c) **Costo en API cloud**: `$0.00` si tokens_remote==0 (de report). El ángulo del premio Gemma.
     (d) **Problemas wave64 cazados**: nº de eventos wave64. Destacado (es EL diferencial: "nadie más detecta esto").

2. **WAVE64 — panel HÉROE** (el diferencial, destacalo con estética de alerta/insight):
   - Tabla: file:line · pattern (W0x badge) · severidad (correctness=rojo / suspicious=ámbar) · explicación.
   - Un texto arriba: "wave64 divergence — el wavefront de AMD es de 64 lanes, no 32. HIPnosis lo detecta
     estáticamente; un port textual (hipify) lo pasa por alto → resultados numéricos silenciosamente incorrectos."

3. **TRANSFORMACIÓN DE CÓDIGO** (fetch /diff, la prueba de que es real):
   - Renderizá el diff con colores (líneas `-` rojo, `+` verde), monospace, scroll horizontal.
   - Usá highlight.js (CDN) si querés resaltar sintaxis C++. Título: "El código, antes → después".

4. **BURNDOWN de errores**: gráfico (barras o línea) de build (iteration→errors) bajando a 0. Animado.

5. **TIMELINE de fases**: horizontal, 9 fases, la actual pulsa; pasadas en verde tenue.

6. **FIXES aplicados**: tabla clase(klass) → tier(badge: deterministic=gris/local=verde-Gemma/remote=azul) →
   commit. Contadores por tier. Y una barra "tokens local vs remoto" (local lleno, remoto vacío = la narrativa).

7. **VEREDICTO**: PASS/FAIL/NO_ORACLE grande y claro (PASS verde enorme). Detalle abajo (tolerancias).

8. **CERTIFICADO** (fetch /certificate): render del markdown (podés usar un mini-parser o marked.js por CDN),
   en una card colapsable/scrollable, con botón "descargar .md". Es el entregable.

### Comportamiento:
- Polling cada 1s con ?after=<último _i>, render INCREMENTAL (no re-render total; acumulá estado).
- /diff y /certificate se fetchean UNA vez cuando el run llega a REPORTING/DONE (o al cargar).
- Fallback: si el API no responde (offline), cargá fixtures/demo-run.jsonl (relativo) para ver el layout.
- Sin errores de consola. Responsive (se ve bien en la laptop del juez y proyectado).

### Cómo probarlo:
Levantá el server en replay:  (desde orchestrator/)
  ORACLE_MODE=replay <VENV> -m uvicorn app.main:app --port 8080
y abrí http://localhost:8080/?run=run_bsw01a2  → debe reproducir el run bsw en vivo (drip-feed) con las
8 secciones. El trace demo tiene wave64 W01/W02, errores 8→0, fixes deterministas+local, verify PASS.

--- FIN TAREA ---

Criterios de aceptación:
1. El dashboard carga y polea; muestra las 8 secciones con datos del trace demo (run_bsw01a2 en replay).
2. Las 4 métricas hero calculan bien (% local, $0, errores, wave64) desde los eventos.
3. /diff se renderiza con colores (antes/después). /certificate se renderiza (markdown).
4. SIN build step (vanilla + CDNs), SIN SSE, polling 1s incremental. Sin errores de consola.
5. Estética pro: AMD rojo como acento, verde=éxito, jerarquía clara, responsive.

Reglas duras:
- F-15: polling JSON ?after=N. F-17: los números salen del trace/API, no inventados.
- NO cambies los endpoints (consumilos). L7: cero Python.
- Al terminar: COMMIT ("feat(dashboard): rediseño wow — hero + wave64 + diff + certificado"). Respuesta CORTA: qué hiciste + cómo lo probaste. Bloqueo: 'BLOCKED | ...'.
