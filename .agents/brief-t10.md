Trabajás en el worktree actual (rama spike/t10-taxonomy). Implementá SOLO esta tarea.

--- TAREA T10: core/rules.yaml + core/taxonomy.py — taxonomía de errores de porteo ---
Capa L2: taxonomy.py importa core.schemas, core.config, pyyaml y stdlib (re). NO importa
phases/oracle/llm/state.

ARCHIVOS: orchestrator/core/rules.yaml, orchestrator/core/taxonomy.py
TEST: orchestrator/tests/test_taxonomy.py

### rules.yaml — catálogo de clases (blueprint §6.2). Formato EXACTO (cada entrada):
    - id: E01
      name: leftover_cuda_include
      match: { msg_regex: "cuda_runtime.h|cuda.h.*(not found|no such)" }
      strategy: deterministic
      fix_template: 's|#include\s*[<"]cuda_runtime.h[>"]|#include <hip/hip_runtime.h>|'
    - id: E02
      name: unconverted_api_call
      match: { msg_regex: "use of undeclared identifier 'cu(da)?[A-Z]" }
      strategy: deterministic
      # tabla cuX->hipX embebida (ver taxonomy.py CUDA_TO_HIP)
    - id: E05
      name: warp_intrinsic_mismatch
      match: { msg_regex: "__(ballot|shfl|any|all|activemask)" }
      strategy: llm
      tier: local
      notes: "AMD wavefront=64: __ballot devuelve 64 bits, usar __popcll, warpSize runtime"
    - id: E04
      name: inline_ptx
      match: { msg_regex: "asm|invalid instruction|ptx" }
      strategy: llm
      tier: remote
    - id: E10
      name: symbol_memcpy
      match: { msg_regex: "hipMemcpyToSymbol|hipGetSymbolAddress" }
      strategy: llm
      tier: local
      notes: "envolver el símbolo en HIP_SYMBOL(x)"
    - id: E13
      name: build_system
      match: { file_regex: "CMakeLists|Makefile|<link>" }
      strategy: llm
      tier: remote
    - id: E99
      name: unknown
      match: {}                         # catch-all, SIEMPRE al final
      strategy: llm
      tier: local_then_remote
Completá además E03, E06, E07, E08, E09, E11, E12 siguiendo el MISMO formato, con regex razonables
para clases comunes de porteo CUDA→HIP (p.ej. E12 = referencia a un patrón wave64 W0x que generó
error; E06 = tipo/textura CUDA sin equivalente directo; etc.). Mantené E99 como ÚLTIMO (catch-all).

### taxonomy.py:
    def load_rules(path: str | None = None) -> list[Rule]:
        # carga rules.yaml (default: junto a este módulo). Rule = dataclass con
        # id, name, msg_regex (compilada o None), file_regex (compilada o None),
        # strategy, tier (o None), fix_template (o None), notes (o "").
        # Valida que E99 (catch-all, match vacío) sea la ÚLTIMA entrada.

    def classify(group, rules: list[Rule]) -> str:
        # group = core.schemas.ErrorGroup. Devuelve el id de la PRIMERA regla que matchea:
        #   - msg_regex contra el message del primer error del grupo, y/o
        #   - file_regex contra el file del primer error.
        # El orden de rules.yaml define prioridad; E99 matchea todo (catch-all) al final.
        # Esta es la clasificación DETERMINISTA por regex (la del LLM es otra capa, §6.5-A).

    CUDA_TO_HIP: dict[str, str]   # tabla de sustitución para E02 (deterministic).
        # Al menos ~30 entradas comunes: cudaMalloc->hipMalloc, cudaMemcpy->hipMemcpy,
        # cudaFree->hipFree, cudaDeviceSynchronize->hipDeviceSynchronize, cudaMemset->hipMemset,
        # cudaGetLastError->hipGetLastError, cudaStreamCreate->hipStreamCreate, cudaEventCreate->
        # hipEventCreate, cudaMemcpyHostToDevice->hipMemcpyHostToDevice, etc. (el prefijo cuda->hip
        # cubre la mayoría; incluí las de enums/constantes también).

    def deterministic_fix(klass: str, group) -> str | None:
        # Para E01: devolvé el fix_template (regex sed-like). Para E02: usando CUDA_TO_HIP,
        # armá el reemplazo del identificador no convertido (extraé el identificador del mensaje
        # 'use of undeclared identifier 'cudaXxx'' y mapealo). Para clases llm → None.

### Test test_taxonomy.py (con fixtures de bsw ya en el repo: fixtures/bsw/build_01.txt):
- load_rules carga N reglas, E99 es la última, cada Rule tiene su regex compilada.
- classify: un ErrorGroup con message "fatal error: 'cuda_runtime.h' file not found" → "E01".
- classify: "use of undeclared identifier 'cudaMemcpy'" → "E02".
- classify: "use of undeclared identifier '__ballot_sync'" → "E05".
- classify: un mensaje raro que no matchea nada → "E99" (catch-all).
- CUDA_TO_HIP tiene cudaMalloc→hipMalloc, cudaMemcpy→hipMemcpy (spot check).
- deterministic_fix para E02 sobre "'cudaMemcpy'" produce un reemplazo que menciona hipMemcpy.
Podés parsear fixtures/bsw/build_01.txt con core.errparse (ya existe) para armar grupos reales.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_taxonomy.py -q` verde.
2. taxonomy.py NO importa phases/oracle/llm/state. E99 SIEMPRE última (validado).
3. classify es determinista por regex; el orden de rules.yaml = prioridad.

Reglas duras:
- Prompts NO van acá (van en prompts.py, otra tarea). Umbrales en config (INV-9).
- E99 catch-all al final SIEMPRE. classify determinista (la clasificación LLM es §6.5-A, otra capa).
- Al terminar: pytest verde + COMMIT ("feat(core): taxonomy rules.yaml + classify + tabla cuda->hip + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
