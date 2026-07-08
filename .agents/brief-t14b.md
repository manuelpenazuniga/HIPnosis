Trabajás en el worktree actual (rama spike/t14b-wiring). Implementá SOLO esta tarea. Es la INTEGRACIÓN
que CIERRA el loop: cablea las funciones REALES al run_build_loop (T14a, ya existe) y lo enchufa al
driver de fases (T8, ya existe) para correr el pipeline COMPLETO en mock.

--- TAREA T14b: core/phases/build_loop.py — wiring real del BUILD_LOOP + integración de pipeline ---
Capa L4. Importa core.phases.loop (run_build_loop), core.taxonomy, core.llm.*, core.patcher,
core.gitrepo, core.errparse, core.oracle.base, core.schemas, core.config, core.trace, core.state.
Es el ÚNICO módulo donde se juntan taxonomy+llm+patcher (T14a los dejó inyectables a propósito).

ARCHIVO: orchestrator/core/phases/build_loop.py    TEST: orchestrator/tests/test_build_loop.py

### DISEÑO YA DECIDIDO (no lo re-litigues — resuelve las 2 tensiones de integración):

**Decisión 1 — modelo de build:** `apply_fn(patch, commit_msg)` APLICA el fix, hace `oracle.build()`
para medir el resultado, y devuelve `new_count - count_before`. (Sí, hay 2 builds por iteración: el
del tope del loop y el de apply_fn — es correcto y las fixtures mock lo soportan.)

**Decisión 2 — DOS caminos de aplicación (por eso classify da la estrategia):**
- **determinista** (E01/E02, strategy=="deterministic"): sustitución GLOBAL vía regex/tabla, NO por
  patcher (cudaMemcpy→hipMemcpy aparece N veces → viola la unicidad del patcher a propósito). Usá
  `core.taxonomy.deterministic_fix(klass, group)` para obtener la sustitución y aplicala a los
  archivos del grupo (regex sub global). Commit vía `gitrepo.commit_all`.
- **LLM** (strategy=="llm", E05/E04/etc.): pedí un parche SEARCH/REPLACE al LLM y aplicalo vía
  `core.patcher.apply_patch` (unicidad dura). En modo MOCK o si el LLM no responde, `propose_fix`
  devuelve "" → el loop lo cuenta como intento fallido (ya lo maneja T14a). NO inventes fixes.

### Funciones a construir:

    def make_loop_functions(ctx, oracle, rules) -> tuple[ClassifyFn, DecideTierFn, ProposeFixFn, ApplyFn]:
        # classify_fn = lambda g: core.taxonomy.classify(g, rules)
        # decide_tier_fn = core.llm.router.decide_tier
        # propose_fix_fn = lambda g, tier, attempts: (
        #     "" si tier=="deterministic" (el patch real lo arma apply_fn con deterministic_fix)
        #        -- OJO: para que el loop cuente el fix determinista, ver abajo cómo se modela --
        #     else: llamar al LLM (router.client_for_tier + prompts.render_fixer) y devolver el texto
        #           del parche SEARCH/REPLACE; en mock/sin-LLM devolver "".
        # apply_fn = def(patch, msg):
        #     - determiná la estrategia del grupo actual (pasala por closure/estado).
        #     - determinista: aplicá deterministic_fix a los archivos, commit; luego oracle.build(); return delta.
        #     - llm: si patch=="" → return 1 (intento fallido, sin build). Si no → patcher.apply_patch;
        #            si APPLIED → oracle.build(); return delta. Si NOT_FOUND/AMBIGUOUS/etc → return 1.
        # NOTA: como el loop de T14a inyecta estas 4 fns, para que el camino DETERMINISTA cuente como
        # fix, propose_fix_fn para deterministic debe devolver un marcador NO vacío (p.ej. el texto de
        # deterministic_fix) y apply_fn lo aplica por regex. Ajustá el contrato para que:
        #   applied (delta<0 y patch!="") se cumpla en el camino determinista exitoso.

    def build_loop_handler(ctx) -> None:
        # El handler de la fase BUILD_LOOP para el driver de state (T8). Construye las fns con
        # make_loop_functions, corre run_build_loop, y vuelca LoopResult.counters en ctx (para que
        # REPORTING los use) vía ctx.store.update_counters(ctx.run.id, result.counters).
        # Emití al trace el resultado (success/final_errors/iterations).

    def run_full_pipeline_mock(run_id, store, config, trace, fixtures_dir, repo_dir) -> Run:
        # Helper de integración: arma un MockOracle sobre fixtures_dir, y llama
        # core.state.run_pipeline con overrides={RunState.BUILD_LOOP: build_loop_handler} (+ inyectando
        # el oracle en el ctx). Esto corre el pipeline COMPLETO QUEUED->...->DONE en mock.

### Test test_build_loop.py (con MockOracle sobre fixtures/bsw, SIN red, SIN GPU):
- **make_loop_functions**: classify sobre un grupo de cuda_runtime.h → "E01"; decide_tier determinista.
- **camino determinista**: un grupo E01/E02 con archivos reales en un workspace temporal (copiá un .cu
  con `#include <cuda_runtime.h>` y usos de cudaMemcpy) → apply_fn aplica la sustitución (el archivo
  queda con hip_runtime.h / hipMemcpy) y commitea.
- **PIPELINE COMPLETO EN MOCK (el test que cierra el loop)**: run_full_pipeline_mock sobre fixtures/bsw
  (build_01..04: 8->0) con un workspace temporal → el Run final llega a state DONE, el trace tiene la
  secuencia de fases QUEUED->...->DONE + eventos build con errores DESCENDIENDO, y counters poblados.
  (Este test es el criterio de aceptación M2 en mock.)

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_build_loop.py -q` verde, INCLUYENDO el test de pipeline completo en mock que llega a DONE.
2. Los dos caminos (determinista global / LLM SEARCH-REPLACE vía patcher) funcionan; el determinista NO pasa por el patcher (evita el rechazo por ambigüedad).
3. INV-3 (todo cambio vía gitrepo commit), INV-1 (el loop control no cambió; solo se inyectan fns), INV-7 (counters de conteo).
4. En mock/sin-LLM, las clases LLM devuelven "" y el loop lo maneja (no inventa fixes).

Reglas duras:
- NO modifiques core/phases/loop.py (T14a) ni core/state.py (T8): solo INYECTÁS/cableás. Si necesitás
  un cambio mínimo en ellos, anotalo y pedí confirmación (BLOCKED | SPEC).
- Determinista = sustitución global (no patcher). LLM = patcher SEARCH/REPLACE. Ambos commitean por gitrepo.
- Al terminar: pytest verde + COMMIT ("feat(phases): build_loop wiring — cierra el loop (pipeline mock completo)").
- Respuesta CORTA: archivos + output pytest + confirmá que el test de pipeline completo llega a DONE. Bloqueo: 'BLOCKED | ...' y pará.
