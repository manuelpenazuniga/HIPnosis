# ESTADO — log de avance HIPnosis (append-only, una línea por evento; v2 §8)

# Taxonomía de estados: DONE | BLOCKED (ENV|SPEC|DEPS) | AUDITED | ESTRUCTURA (OK|AJUSTE|RECHAZO) | MERGED
# IDs estables: un T<n> emitido NO se renumera ni reutiliza.

T0: MERGED d69dfda | scaffolding (git init, ARCHITECTURE/BITACORA/DEVIATIONS, gitignore)
T0.5: EN CURSO | curación repos demo HeCBench + manifiestos (HeCBench clonándose en bg)
T1: EN CURSO | schemas+config+.env.example (worker opencode-go/minimax-m3, worktree t1) | riesgo medio-alto → panel pre-merge
T4: EN CURSO | gitrepo wrapper + tests (worker opencode-go/minimax-m3, worktree t4) | riesgo bajo
T0.5: PARCIAL | repos demo provisionales: softmax-cuda (fácil, 154 LOC, self-check PASS/FAIL), shuffle-cuda (wave64, 363 LOC, __shfl 0xffffffff = W01/W04); medio TBD (scan/bitonic-sort/sort). Anti-fuga INV-11: copiar solo -cuda, nunca -hip.
T4: ESTRUCTURA: OK | gitrepo primitiva L2, revert=reset --hard HEAD~1 (INV-3 ✓), sin imports hacia arriba; fix menor de anotación is_dirty aplicado por orquestador
T4: MERGED ab006e8 | pytest 5 passed en main
T1: ESTRUCTURA: OK | contrato fiel 100%, hoja schemas + config→schemas; 2 fixes menores (timing dict param, aplicados por orquestador)
T1: AUDITED | gemini 3.1 pro: CHANGES(2 menor) → resueltos
T1: MERGED 91f3fdd | contrato base congelado; pytest verde en main
T0.5: repo wave64 FIJADO = bsw-cuda (kernel.cu:13 __ballot_sync(0xffffffff)=W01+W02, Smith-Waterman 788 LOC, run: target); fácil = softmax-cuda (154 LOC, self-check, bonus W06); medio TBD.
T2: ESTRUCTURA: OK | trace L1 append-only fsync (INV-4 ✓), read_events after=índice
T2: MERGED | 11 tests verdes en main; riesgo bajo (sin panel externo, techo de calidad = orquestador)
T3: ESTRUCTURA: OK | oracle base+mock, replay secuencial determinista, INV-6 paridad, sin imports prohibidos
T3: AUDITED gemini 3.1 pro: APPROVED | MERGED
T5: ESTRUCTURA: OK | errparse; signature con doble clave (per-error basename anti-loop F-06 / group msg-only)
T5: AUDITED gemini 3.1 pro: CHANGES → HIGH (columna opcional) resuelto + test regresión | MERGED
T5: DEUDA diferida (validar con fixtures reales M0): números entre comillas simples; backtick de ld en signature linker
T6: ESTRUCTURA: OK | wave64 W01-W07, stripper preserva nº línea, explicaciones fijas F-17; audit gemini en curso
T6: ESTRUCTURA: OK | baseline fiel §5.2, stripper preserva líneas, F-17
T6: AUDITED gemini 3.1 pro: CHANGES (precisión más allá de §5.2) → ruteado a T6b (calibración día 2)
T6: MERGED | baseline §5.2, 28 tests verdes
T6b: PENDIENTE | calibrar catálogo wave64 contra repos reales (bsw/softmax); insumo: .agents/audit-t6-findings.md (Gemini: mayúsculas máscara, word boundaries, long int falso pos, tiled_partition funcional, hex &0x1f). Validar SIN introducir falsos negativos.
LANE3 (CP-1 ola1): demo-run.jsonl hand-authored (banca replay, 28 ev QUEUED->DONE, verify PASS) MERGED; golden fixtures bsw build_01-04 (gate fixture-first) MERGED; errparse revalidado contra fixtures reales OK (deuda #2/#3 no se dispara en demo repos).
T9: EN CURSO (api, m3) | T7: EN CURSO (scan, m3)
T9: ESTRUCTURA: OK | api L6, AD-3 (control por store, no fases inline), events?after=N vía read_events
T9: AUDITED gemini 3.1 pro: APPROVED | MERGED (nota: T20 registra run replay en store + coloca demo-run.jsonl)
T7: ESTRUCTURA: OK | scan §5.1-5.3, dificultad exacta, api_calls despoja comentarios, F-17; 19 tests+AST purity
T7: AUDIT gemini NO DISPONIBLE (agy backend colgado x3) → mergeado con pase propio del orquestador (v3 §3 degradación honesta) | MERGED
DEUDA menor: scan importa _strip_comments_and_strings (privado) de wave64 → promover a público en T6b o follow-up
T18: EN CURSO | dashboard estático polling 1s (qwen3.7-plus) — Track A bancar submission
T18: ESTRUCTURA: OK | dashboard vanilla, polling after=_i (F-15), 6 secciones; nit cosmético DONE en rojo
T18: MERGED | riesgo bajo, sin panel externo
T20: modo replay (app/replay.py) — siembra run grabado + drip-feed reloj lazy; e2e verificado (server+curl+browser JS); 4 tests replay; auto-review orquestador (agy erratico) | MERGED
AGY-LEARN: el auditor agy/Gemini a veces intenta EJECUTAR pytest en vez de solo leer → cuelga 0 bytes. Futuro: brief de audit debe decir "NO ejecutes comandos ni corras tests; revisá SOLO leyendo".
T20: MERGED (de verdad) c6a033c | 99 tests en main; corrección: el merge previo fue no-op (olvidé git commit en worktree). Lección: tras tarea propia en worktree, commitear ANTES de mergear y VERIFICAR que el merge movió archivos (git ls-files / conteo de tests), no confiar en el echo.
T19: ESTRUCTURA: OK | docker compose perfiles replay|gpu + Dockerfiles; perfil replay VERIFICADO e2e (docker build+up, dashboard+API :8080, run sembrado, drip-feed); gpu YAML válido (M0). | MERGED
=== HITO: TRACK A (submission ejecutable) BANCADO ===
docker compose --profile replay up → dashboard vivo de un port bsw-cuda real en cualquier laptop sin GPU (F-16). Verificado end-to-end. Requisito DURO del hackathon cumplido.
=== TRACK B (loop) arrancado ===
T11: EN CURSO | patcher SEARCH/REPLACE unicidad dura (deepseek-v4-pro, riesgo ALTO, diseño arquitecto)
T10: EN CURSO | taxonomy rules.yaml + classify (m3)
T12: EN CURSO | llm client/router/prompts (m3)
T6b: VALIDADO (análisis, sin cambio de código) | wave64 baseline corrido contra bsw/softmax REALES: CERO falsos positivos. bsw dispara W01+W02 (kernel.cu:13 __ballot_sync 0xffffffff), W04 (shfl width=32 en 278/279/302), W05 (laneId%32 en 54/55) — TODOS reales. Tightening de Gemini (mayúsculas/word-boundary) solo afecta casos ausentes en demos → deuda NO urgente, baja prioridad. Arma diferencial validada.
T12: ESTRUCTURA: OK | llm cliente/router/prompts, INV-1 función pura, §6.4 verbatim, prompts §6.5 en prompts.py | MERGED (pase propio, 23 tests)
T10: ESTRUCTURA: OK | taxonomy 14 clases (E99 último), classify validado contra bsw real, tabla cuda->hip | MERGED (pase propio + validación fixture real, 28 tests)
T13: EN CURSO | port (hipify-seam mock-aware) + buildsys (adaptación Makefile/CMake) (m3)
T11: AUDIT codex/GPT-5.5: CHANGES — 6 bugs adversariales (2 Crit: bloque malformado ignorado, alias de path; 2 High: symlink escapa workspace, excepciones sin revert; 2 Med: CRLF fuera de bloque, re-búsqueda [0] ambigua). Panel en riesgo alto justificado (mi pase solo olió 1). → ronda de fix a deepseek. Hallazgos en .agents/audit-t11-codex-findings.md
T13: ESTRUCTURA: OK | port hipify-seam mock-aware + buildsys (validado Makefile bsw real); deuda menor: -arch=$(VAR) forma variable (loop lo atrapa E13) | MERGED (pase propio, 46 tests)
T11: ESTRUCTURA: OK | patcher unicidad dura + all-or-nothing (diseño arquitecto)
T11: AUDIT codex/GPT-5.5 (2 rondas): 6 bugs corrupción → resueltos; 2 regresiones del fix → #1 (marker-in-content) fixeado por orquestador + test, #2/#6 deuda fail-safe casi-imposible (chmod-mode, índice-en-commit-fail). Panel riesgo alto JUSTIFICADO. | MERGED (35 tests)
DEUDA fail-safe T11: restore hace chmod 0644 (pierde modo ejecutable); commit-failure deja índice staged. Ambos casi-imposibles en este pipeline.
T8: EN CURSO | state FSM+SQLite+driver (m3, watchpoint AD-3)
T14a: EN CURSO | loop control build-fix §6.4 (deepseek-v4-pro, riesgo ALTO)
T8: ESTRUCTURA: OK | state FSM+SqliteRunStore+driver; AD-3/INV-4/INV-5 verificados directo (watchpoint del arquitecto, pase asignado a mí) | MERGED (21 tests). Pendiente integración: swap InMemoryRunStore→SqliteRunStore en main.py al cablear pipeline completo.
T14a: EN CURSO (deepseek, muy deliberado — estudiando taxonomy/errparse/oracle antes de escribir el control del loop; no colgado, CPU subiendo). Pendiente al aterrizar: verificación + audit (riesgo alto, candidato a codex) → luego T14b (cablear classify/fix/patcher reales) → cablear bsw verde en mock (criterio M2).
T14a: ESTRUCTURA: OK | loop control §6.4 (INV-1/4/7/9/10, F-06)
T14a: AUDIT codex/GPT-5.5: CHANGES 5 hallazgos → #1 INV-7 counters, #2 INV-9 umbrales, #3 oscilación corregidos+tests; #4/#5 deuda menor fail-safe. codex confirmó INV-10 (sin loop infinito). | MERGED (7 tests loop)
HITO PARCIAL M2: el test green-path de T14a demuestra el loop drenando bsw 8->5->2->0 en MOCK hasta success=True → criterio mock de M2 esencialmente cumplido a nivel de loop aislado.
FALTA para cerrar: T14b = integración (BUILD_LOOP handler real en state + propose_fix real determinista/LLM + apply_fn patcher) + swap SqliteRunStore en api + correr pipeline COMPLETO QUEUED->DONE en mock (scan->port->loop->verify-stub).
T14b: EN CURSO | wiring real classify/fix/apply + pipeline mock completo (deepseek) — CIERRA el loop
T14b: ESTRUCTURA: OK | build_loop wiring — integración limpia L4 (no tocó loop/state), 2 caminos de aplicación
T14b: VERIFICADO e2e por orquestador: pipeline bsw QUEUED->DONE en mock, 8->2->0, fix E01 transformó fuente real, counters OK | MERGED (3 tests)
====================================================================
🎯 HITO M2 (Día 2) CERRADO EN MOCK: el loop completo corre end-to-end.
   Pipeline QUEUED->DONE, errores drenan, fixes deterministas aplican al fuente, counters poblados.
   Falta para M2-real: hipcc en MI300X (M0 humano, guía en docs/M0-smoke-test.md).
====================================================================
=== M3 (verify + certificado) arrancado ===
T15b: EN CURSO | comparador paridad rtol/atol F-09 (deepseek, riesgo ALTO)
T15a: EN CURSO | manifest loader + hipnosis.yaml schema (m3)
T16: EN CURSO | report.py + templates certificado F-17 (m3)
T15a: ESTRUCTURA: OK | manifest loader §7.1, validado contra manifiestos demo softmax/bsw reales | MERGED (16 tests). Deuda menor: coercer 1e-5 string→float.
T15b: ESTRUCTURA: OK | parity rtol/atol F-09
T15b: AUDIT codex/GPT-5.5: CHANGES 3 (1 CRITICAL self_check substring→PASS falso) corregidos+tests | MERGED (49 tests)
T16: ESTRUCTURA: OK | report.py + templates certificado F-17 (números de código, sección NEEDS_HUMAN) | MERGED (14 tests, pase propio)
T15c: EN CURSO | verify.py (run + paridad + timing §7) (m3)
T17: EN CURSO | ship.py (certificado + branch/PR §8) (m3)
T15c: MERGED (verify) | T17: MERGED (ship) | T16: MERGED (report)
pipeline.py: integración M3 end-to-end — VERIFICADO: run completo QUEUED->DONE, verify=PASS, certificado HIPNOSIS_CERTIFICATE.md con todas las secciones. Puentea mismatch de ctx entre handlers.
====================================================================
🎯 HITO M3 (Día 3) CERRADO EN MOCK: verify + certificado end-to-end.
   Un run completo sin intervención → DONE + PASS + certificado. Falta M3-real: hipcc/GPU (M0 humano).
====================================================================
====================================================================
🎯 INTEGRACIÓN api↔pipeline COMPLETA (backend end-to-end):
   POST /runs → pipeline en background (thread) → QUEUED..DONE, verify=PASS, certificado.
   VERIFICADO EN VIVO (uvicorn mock): un POST corre el pipeline entero y el dashboard lo polea.
   Piezas: oracle/real.py (M0-ready), runner.py (execute_run), main.py (autorun+SqliteRunStore),
   api.py (POST→background, conexión SQLite por thread). 369 tests.
====================================================================
PENDIENTE (menor/no-bloqueante): unificar contrato de ctx entre handlers; M0 humano (real.py con GPU);
M5 README/video. El backend está funcionalmente completo en mock.
====================================================================
🎨 PULIDO PARA GANAR (dashboard wow + 3 repos + narrativa):
- 3 repos demo verdes en mock: bsw (wave64, 8→0), softmax (fácil, 3→0), scan (medio, 10→3→0).
  runner mapea repo→fixtures+manifiesto; cada POST /runs corre su secuencia.
- Backend: endpoints /diff (transformación real CUDA→HIP) y /certificate + demo bundleado; precios demo.
- Dashboard REDISEÑADO (wow): hero 4 métricas (errores, %local Gemma, $0 API, wave64 cazados) + sparkline,
  wave64 panel héroe, sección diff (highlight.js), burndown, barras tokens local/remoto, certificado (marked.js).
  Verificado funcional (sintaxis JS, IDs, métricas, sirve en replay). Browser extension caído → sin screenshot.
====================================================================
====================================================================
🔒 AUDIT CODEX #1 — TRAMOS 1+2 EJECUTADOS (Gate A "truth before wow" + Gate B "oráculos de verdad"):
Tramo 1: replay Docker reparado (git en imagen slim — la entrega estaba ROTA desde checkout limpio,
  gate build --no-cache+up+healthz verificado); rocm/vllm pineada gfx94X + HF_TOKEN por env_file
  (environment pisaba env_file — trampa evitada); procedencia honesta: fixture oracle_mode=mock,
  badge 'REPLAY · synthetic demo' derivado del trace (auto-upgrade a 'recorded' con trace real M0),
  README según tabla del audit.
Tramo 2 (P0.3/4/5/7/8/9): green exige returncode==0 (grupo sintético E13 si exit!=0 sin ': error:');
  delta de fix MEDIDO por el compilador (before/apply/after) con REVERT si no mejora (INV-3);
  una build por transición (apply_fn ya no compila ni inventa deltas); verify exige ran+exit 0 y
  borra output stale antes de correr; DONE_PARTIAL cableado en la FSM (loop fail → REPORTING →
  DONE_PARTIAL, salta RUNNING/PARITY); cert==trace==sqlite (ctx.loop_result + refresh ctx.run);
  tokens medidos del usage real de la API (F-17). Fixtures demo RE-AUTORADOS CAUSALES: el workspace
  staged contiene exactamente lo que los fixtures reportan; softmax 3→2→1→0, scan 10→7→5→3→2→1→0;
  E05 de bsw vía demo-patch enlatado (SOLO la propuesta es fixture; patcher/commit/build/delta reales).
  378 tests (8 gates nuevos en test_oracle_gates.py). Verificado en vivo: 3 repos demo DONE con
  todos los fixes applied=true y deltas reales.
Tramo 3 (M0 llave-en-mano, sin GPU): 3 repos demo STANDALONE armados (bsw/softmax/scan-cuda desde
  HeCBench BSD-3, solo variante -cuda INV-11, sin CMake; test-data real de bsw traído del DVC remote
  S3 anónimo, md5 verificado 7824d06...; hipnosis.yaml + LICENSE + README de procedencia c/u) — listos
  para push a github.com/manuelpenazuniga (el push lo dispara el humano). record_fixture.sh: graba
  trace+cert+diff de un run real a fixtures en un comando (verifica oracle_mode=real; smoke-test OK).
  Allowlist P0.12: REPO_ALLOWLIST en config+api (403 si repo fuera de lista) + compose gpu la setea a
  los 3 demos. runner ahora emite run_meta(oracle_mode,gpu_arch) — sin esto el badge 'recorded run'
  jamás se activaría en M0. Runbook M0 apunta a los repos standalone + record_fixture.sh. 380 tests.
====================================================================
====================================================================
🛂 WOW #2 PORT PASSPORT (GPU-independiente, ships hoy): atestación de procedencia verificable.
core/attestation.py (L3): build_attestation computa digests SHA-256 del diff y del certificado
  por CÓDIGO (F-17), + source/final commit, environment (gpu_arch/oracle_mode), veredicto.
  Procedencia HONESTA = SLSA-L1 unsigned (no reclama firma que no tiene, audit codex).
ship_handler escribe HIPNOSIS_ATTESTATION.jsonl junto al certificado (azúcar, INV-5 no tumba run).
Endpoint GET /runs/{id}/attestation (workspace vivo o demo bundleado). Fixture demo-attestation.jsonl
  con digest REAL de demo-diff.txt (verificado match). Dashboard: panel Port Passport que recomputa
  sha256(diff) en el browser (SubtleCrypto, CSP-safe) y compara → badge VERIFIED/TAMPERED; botón
  tamper (flip 1 byte → TAMPERED) + re-verify (→ VERIFIED) + download .jsonl. VERIFICADO e2e en Chrome:
  ciclo VERIFIED→TAMPERED→VERIFIED funciona; fix de race (verify obtiene el diff directo del endpoint).
Ademas P1 routing (audit): local_then_remote prueba LOCAL en 1er intento (antes saltaba a remoto).
387 tests (7 nuevos: 5 attestation + 2 router). README con seccion Port Passport.
====================================================================
====================================================================
🌐 DEMO PÚBLICO (vs PortForge): landing AMD + dashboard replay 100% estático, deployable a Vercel.
Estudiado PortForge (repo+submission+demo en vivo): es traductor LLM + terminal SCRIPTEADO (timestamps
  idénticos c/corrida; sus propias tarjetas dicen COMPILE 'Awaiting AMD GPU' y BENCHMARK 'Not run yet',
  pero el terminal canta 'Compiled on MI300X'; "Benchmark result: Compiled successfully" = no hay benchmark;
  100%/99%/98% sin evidencia, 0 tests, 0 oráculo, 0 wave64). ES el strawman de HIPnosis: el port que
  compila y sigue mal. Ventajas de superficie de ellos: demo público clickeable + se siente producto.
Respuesta: index.html landing AMD (tesis 'a port that compiles can still be silently wrong' + firma =
  sello Port Passport VERIFIED con hash real); app.js con fetchStaticFallback (diff/cert/attestation →
  fixtures) para correr SIN backend; loadDemoData distingue apiAlive (offline degradado) vs estático
  (REPLAY synthetic intencional). vercel.json + .vercelignore (deploya solo landing+dashboard+fixtures;
  backend real queda en MI300X, honesto). docs/DEPLOY.md. Verificado e2e local sin backend: landing OK,
  demo completa (loop→wave64→diff→PASS→cert→passport) + ciclo TAMPERED↔VERIFIED. Deploy lo dispara el humano.
====================================================================
====================================================================
🛡️ HIPnosis Guard (wow #3, GPU-independiente): gate estatico de portabilidad para CI.
core/guard.py: CLI (python -m core.guard) que reusa el detector wave64 REAL (W01-W07) +
  scan de CUDA residual (include/API/launch) + regla WARP32-DEFINE. Anotaciones nativas de
  GitHub Actions (::error file=,line=::) en CI; reporte legible en consola; exit!=0 si hay
  correctness (bloquea merge). --fail-on configurable. 6 tests (test_guard.py). Verificado en
  vivo: limpio->exit 0, WARP_SIZE 32 + __ballot_sync(0xffffffff)->exit 1 con anotaciones.
Integracion producto: ship escribe .github/workflows/hipnosis-guard.yml en el repo porteado
  (el PR incluye el gate — 'no solo te migro, evito que vuelvas a quedar locked-in'). Verificado
  e2e (mock pipeline -> workflow emitido). Template en orchestrator/templates/hipnosis-guard.yml.
Dogfood: .github/workflows/hipnosis-guard.yml del propio repo lintea examples/guard/ (kernel HIP
  limpio, pasa). docs/hipnosis-guard.md. README con seccion + roadmap actualizado. 393 tests.
====================================================================
====================================================================
🕵️ INTELIGENCIA COMPETITIVA + 6 ROBOS (vs Bridge y Kernel Olympics, Track Unicorn):
Analizados ambos rivales (memoria competitive-intel-rivals.md). Bridge: clon real pero solo
  porta fixtures de juguete, sin paridad numérica, nunca MI300X; su arma = "agentic security".
  Kernel Olympics: pitch pulido pero "PASSED on MI300X" FABRICADO (texto hardcodeado, warpSize=32
  en wave64), contenedor sin hipcc. Robos implementados priorizados por costo/beneficio:
  #1 SEGURIDAD AGÉNTICA (roba el diferenciador de Bridge): patcher veta paths protegidos
    (PROTECTED_ALWAYS: hipnosis.yaml/.hipnosis/.github/ + golden/output del manifiesto),
    PatchStatus.PROTECTED all-or-nothing; camino determinista salta protegidos + traversal/symlink;
    THREAT_MODEL.md honesto (T1-T7, PLANNED marcados) + seccion README. core.patcher.is_protected.
  #2 GATE DE INTEGRIDAD DEL ORACULO en VERIFY (adapta anti-trampa de Bridge): check_oracle_integrity
    pregunta a git si hipnosis.yaml/golden cambiaron desde el commit fuente o estan dirty → FAIL
    SIN ejecutar el binario (un PASS contra oraculo adulterado no es PASS). Defensa en profundidad
    sobre #1 (el veredicto no confia en el patcher).
  #1+#2: tests/test_redteam.py (22 tests: inyeccion como dato, paths protegidos, traversal/symlink,
    gate de integridad, verify fail-closed). 393→415 tests, suite verde, guard dogfood limpio.
  #3 tabla de resultados honesta en README (bsw 8→0/4it, softmax 3→0/3it, scan 10→0/6it; numeros
    REALES del pipeline mock + fixture hero; DONE_PARTIAL/NEEDS_HUMAN como salida de primera clase).
  #4 tiles de costo ($0.00 cloud, 100% local, 438 tokens) en README, sourced de counters.
  #5 scripts/record_demo_cast.sh: asciinema del run REAL (terminal POST→PASS, cero hardcode — donde
    KO se quemo); integrado al runbook M0 §6. #6 tabla de negocio (manual/hipify/AI-demos/HIPnosis).
  DEVIATIONS D-7 (seguridad) y D-8 (cast). Pendiente humano: M0 (grabar cast/fixtures reales).
====================================================================
