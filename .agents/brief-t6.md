Trabajás en el worktree actual (rama spike/t6-wave64). Implementá SOLO esta tarea.

--- TAREA T6: core/wave64.py — linter estático wave64 (catálogo cerrado W01-W07) ---
Capa L2: importa SOLO core.schemas y stdlib (re). NO importa phases/oracle/llm/state/config.
Es el ARMA DIFERENCIAL del producto: detecta suposiciones de warp=32 que rompen en AMD wave64.
Catálogo CERRADO y determinista; las explicaciones son TEXTO FIJO (NUNCA generadas por LLM — F-17).

ARCHIVO DE PRODUCTO: orchestrator/core/wave64.py    TEST: orchestrator/tests/test_wave64.py
FIXTURE YA EXISTE: orchestrator/tests/fixtures/wave64/shuffle_main.cu (repo real HeCBench)
FIXTURE A CREAR: orchestrator/tests/fixtures/wave64/wave64_patterns.cu  (sintético, con UN
  ejemplo claro de CADA patrón W01..W07 — es el que el test usa para asegurar los 7).

### Contrato de wave64.py:

    def lint(source: str, filename: str = "<mem>") -> list[Wave64Finding]:
        # 1) Despojá comentarios (// y /* */) y strings ANTES de matchear (parser de estados
        #    simple, ~30 líneas: recorré char a char llevando estado in_line_comment/in_block/
        #    in_string; reemplazá esos tramos por espacios preservando saltos de línea para no
        #    correr los números de línea).
        # 2) Aplicá el catálogo por línea. Cada match → Wave64Finding con:
        #    file=filename, line=<nº 1-based>, pattern_id="W0x", snippet=<línea ±2 unidas por \n>,
        #    severity y explanation FIJOS del catálogo de abajo.

    def lint_file(path: str) -> list[Wave64Finding]:   # helper: lee el archivo y llama lint().

### CATÁLOGO (regex sobre líneas de código ya despojadas; blueprint §5.2). severity y explanation EXACTOS:
W01 | regex: __ballot(_sync)?\s*\(\s*0xffffffff              | severity=correctness | expl="Máscara de 32 bits; en wave64 la máscara/resultado son de 64 bits"
W02 | regex: (unsigned|uint32_t|int)\s+\w+\s*=\s*__ballot     | severity=correctness | expl="Resultado de ballot truncado a 32 bits en wave64"
W03 | regex: __popc\s*\(\s*__ballot                           | severity=correctness | expl="Debe ser __popcll sobre máscara de 64 bits"
W04 | regex: __shfl(_up|_down|_xor)?(_sync)?\s*\([^)]*\b32\b   | severity=suspicious  | expl="Ancho 32 hardcodeado; wavefront AMD = 64"
W05 | regex: (%|&|/|>>)\s*(32|31|5)\b   SOLO en líneas que además contengan threadIdx|laneId|lane_id | severity=suspicious | expl="Aritmética de lane asumiendo warp de 32 (&31, >>5)"
W06 | regex: tiled_partition\s*<\s*32\s*>                     | severity=suspicious  | expl="Partición cooperative-groups de tamaño warp NVIDIA"
W07 | regex: #define\s+WARP_SIZE\s+32  ó  constexpr\s+\w*\s*=\s*32.*warp (case-insensitive) | severity=suspicious | expl="warpSize debe consultarse en runtime en HIP, no fijarse en 32"

Regla: los `suspicious` (W04-W07) NO se autocorrigen; van al reporte. Los `correctness` (W01-W03)
sí. (Esto lo consume otra capa; acá solo etiquetás severity correctamente.)

### Test test_wave64.py:
- lint sobre wave64_patterns.cu (el sintético) detecta LOS 7 patrones (assert: el set de pattern_id
  encontrados == {W01..W07}). Cada finding tiene la explanation FIJA correcta y la severity correcta.
- Despojado de comentarios: una línea con `// __ballot(0xffffffff)` COMENTADA no debe generar W01
  (test negativo explícito). Un string "__ballot(0xffffffff)" tampoco.
- El número de línea del finding es correcto (1-based) pese al despojado.
- lint_file sobre shuffle_main.cu no explota y devuelve una lista (0 o más findings) — smoke real.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_wave64.py -q` verde, con los 7 patrones detectados en el sintético.
2. wave64.py NO importa nada más que core.schemas + re (grep). Explicaciones son literales fijos en el código.
3. El despojado de comentarios/strings NO corre los números de línea (test lo verifica).

Reglas duras:
- F-17/determinismo: las explanation son TEXTO FIJO del catálogo, jamás generadas. Copialas EXACTO de arriba.
- Catálogo CERRADO: implementá exactamente W01-W07, ni uno más ni uno menos.
- Capa L2 pura. Al terminar: pytest verde + COMMIT ("feat(core): linter wave64 W01-W07 + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
