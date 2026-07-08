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
