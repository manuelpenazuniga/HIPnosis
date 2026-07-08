Trabajás en el worktree actual (rama spike/t14a-loop). Implementá SOLO esta tarea. Es el CORAZÓN del
producto y de riesgo ALTO: el control del build-fix loop. Los INVARIANTES son sagrados. Seguí §6.4.

--- TAREA T14a: core/phases/loop.py — CONTROL del build-fix loop (lógica pura, con fns inyectadas) ---
Capa L4. Importa core.schemas, core.config, core.errparse, core.trace, y los TIPOS de oracle
(core.oracle.base / core.schemas.BuildResult). ⛔ NO importa llm/patcher/taxonomy DIRECTO: las
funciones classify/propose_fix/apply se INYECTAN (así T14a se testea con stubs; T14b cablea las reales).

ARCHIVO: orchestrator/core/phases/loop.py    TEST: orchestrator/tests/test_loop.py

### Contrato — el control loop (blueprint §6.4). Las 3 operaciones "de contenido" se inyectan:

    ClassifyFn   = Callable[[ErrorGroup], str]                    # grupo -> clase "E05"
    ProposeFixFn = Callable[[ErrorGroup, str, int], str]          # (grupo, tier, attempts) -> patch text
    ApplyFn      = Callable[[str, str], int]                      # (patch, commit_msg) -> build_delta aplicado
                 # ApplyFn devuelve el delta REAL de errores tras aplicar+rebuild, o un sentinel si no aplicó.
                 # (En T14a el test las stubbea; en T14b: classify=taxonomy/llm, propose_fix=llm, apply=patcher+rebuild.)

    @dataclass
    class LoopResult:
        success: bool             # True si llegó a 0 errores
        final_errors: int
        iterations: int
        needs_human: list[str]    # signatures de grupos que quedaron sin resolver
        counters: Counters        # fixes_deterministic/local/remote, iterations pobladas

    def run_build_loop(oracle, config, trace,
                       classify_fn, decide_tier_fn, propose_fix_fn, apply_fn) -> LoopResult:

### ALGORITMO (§6.4 — implementalo EXACTO; los contadores son cotas DURAS, INV-10):
    iteration = 0
    signature_history = []        # lista de sets de signatures por iteración (anti-oscilación F-06)
    no_progress = 0               # iteraciones consecutivas sin bajar 'errors'
    prev_errors = None
    while iteration < config.max_iterations:            # MAX_ITERATIONS cota dura
        result = oracle.build()                          # BuildResult
        emit(trace, "build", iteration=iteration, errors=result.count, delta=(result.count-prev_errors if prev_errors is not None else 0))
        if result.count == 0:
            return LoopResult(success=True, ...)         # -> RUNNING
        groups = agrupar(errparse.parse(result.raw_output, config.max_errors_parsed))  # usá errparse (existe)
        # anti-oscilación: registrá el set de signatures de esta iteración
        cur_sigs = {g.signature for g in groups}
        signature_history.append(cur_sigs)
        # estancamiento
        if prev_errors is not None and result.count >= prev_errors:
            no_progress += 1
        else:
            no_progress = 0
        if no_progress >= 5:                             # 5 sin bajar -> salida honesta
            return LoopResult(success=False, ... DONE_PARTIAL semantics ...)
        # elegir grupo abierto con MÁS errores y attempts < MAX_ATTEMPTS_PER_GROUP
        open_groups = [g for g in groups if g.status=="open" and g.attempts < config.max_attempts_per_group]
        if not open_groups:
            return LoopResult(success=False, ...)         # nada más que intentar -> DONE_PARTIAL
        g = max(open_groups, key=lambda x: len(x.errors))
        klass = classify_fn(g)                            # (stub en test)
        tier = decide_tier_fn(estrategia_de(klass), g.attempts, tier_sugerido_de(klass))
        # forzar remoto si estancamiento==3 (§6.4)
        if no_progress >= 3: tier = "remote"
        patch = propose_fix_fn(g, tier, g.attempts)
        delta = apply_fn(patch, f"fix({klass}): iter {iteration} [tier={tier}]")
        emit(trace, "fix", sig=g.signature, tier=tier, applied=(delta<=0 and patch!=""), delta=delta, ...)
        if delta > 0:                                     # EMPEORÓ -> revertir, contar intento
            # (el revert lo hace apply_fn/patcher internamente al detectar delta>0, o marcalo)
            g.attempts += 1
        else:
            actualizá_contadores_por_tier(tier)           # deterministic/local/remote
        # anti-oscilación F-06: si una signature DESAPARECIÓ y REAPARECIÓ 2 veces -> sospechosa:
        #   revertir sus fixes + mandar el grupo directo a tier remoto con historial. (implementá la detección)
        prev_errors = result.count
        iteration += 1
    return LoopResult(success=False, ...)                 # agotó iteraciones -> DONE_PARTIAL

Notas: los umbrales (max_iterations, max_attempts_per_group, max_errors_parsed) SALEN DE config
(INV-9/INV-10, NUNCA hardcodeados). El loop NO decide contenido (INV-1): classify/propose_fix son
inyectadas. Los números de LoopResult.counters salen de contar eventos, no de un LLM (F-17/INV-7).

### Test test_loop.py (con MockOracle real + stubs de las fns):
Usá core.oracle.mock.MockOracle sobre fixtures/bsw (build_01..04: 8->5->2->0 errores, ya existen).
- **Camino verde**: classify_fn stub devuelve "E01"; decide_tier_fn = el real (core.llm.router.decide_tier);
  propose_fix_fn stub devuelve un patch no vacío; apply_fn stub devuelve delta negativo (simula fix
  exitoso). Con el MockOracle drenando 8->0, run_build_loop → success=True, iterations coherente,
  counters poblados. (el mock avanza la secuencia en cada build()).
- **MAX_ITERATIONS**: config con max_iterations=2 y un mock que NUNCA llega a 0 → success=False,
  iterations==2 (cota dura respetada).
- **Estancamiento**: un mock que devuelve SIEMPRE el mismo count>0 → tras 3 fuerza tier remoto
  (verificá que el tier pasado a propose_fix pasa a "remote"), tras 5 → success=False.
- **revert-si-empeora**: apply_fn stub que devuelve delta>0 (empeoró) → el grupo suma attempts;
  tras max_attempts_per_group el grupo deja de elegirse → success=False con needs_human poblado.
- **INV-4**: cada build/fix emite su evento al trace ANTES del siguiente paso.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_loop.py -q` verde (los 4 caminos: verde, max_iter, estancamiento, revert).
2. Umbrales SOLO de config (INV-9/INV-10): test con max_iterations=2 corta en 2.
3. INV-1: classify/propose_fix inyectadas (el loop no las importa directo). INV-7: counters de conteo, no de LLM.
4. loop.py usa errparse (existe) para parse/group; oracle vía la interfaz (mock en test).

Reglas duras:
- INV-10: MAX_ITERATIONS y MAX_ATTEMPTS_PER_GROUP son cotas DURAS. NUNCA loop infinito. F-06 anti-oscilación.
- INV-1: el loop es control determinista; el contenido (clasificar/proponer) es inyectado. INV-4 trace antes de actuar.
- DONE_PARTIAL/needs_human son finales legítimos (INV-5), no errores.
- Al terminar: pytest verde + COMMIT ("feat(phases): loop control build-fix (§6.4) + tests"). Bloqueo: 'BLOCKED | ...' y pará.
- Respuesta CORTA: archivos + output pytest + confirmá los 4 caminos.
