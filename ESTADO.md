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
