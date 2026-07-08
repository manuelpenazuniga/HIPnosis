Trabajás en el worktree actual (rama spike/t7-scan). Implementá SOLO esta tarea.

--- TAREA T7: core/phases/scan.py — FASE 1 SCAN (inventario + wave64 + dificultad) ---
Capa L4 (phase). Importa core.schemas, core.wave64 (YA EXISTE), core.config y stdlib (os, re).
⛔ Dirección: scan(L4) importa wave64/errparse(L2), NUNCA al revés. NO importes state/api/oracle.

ARCHIVO: orchestrator/core/phases/scan.py    TEST: orchestrator/tests/test_scan.py
FIXTURE A CREAR: un mini-repo en orchestrator/tests/fixtures/scan_repo/ con 2-3 archivos .cu que
  contengan llamadas CUDA (cudaMalloc, cudaMemcpy), un uso de cublas, y un patrón wave64 (p.ej.
  __ballot_sync(0xffffffff,...)) + un Makefile con CC=nvcc. Es la entrada del test.

### Contrato de scan.py (blueprint §5.1-§5.3):

    def scan(repo_dir: str) -> ScanResult:
        # 1) INVENTARIO (sin LLM, puro parsing):
        #    - Walk de repo_dir: archivos .cu .cuh .h .hpp .cpp + Makefile/CMakeLists.txt.
        #    - files_cuda = lista de rutas .cu/.cuh (relativas a repo_dir).
        #    - loc_kernels = total de líneas de esos archivos .cu/.cuh.
        #    - api_calls: conteo por regex de llamadas CUDA. Whitelist: r'\bcuda[A-Z]\w+' → nombre
        #      exacto (p.ej. "cudaMemcpy": 12). Y librerías: r'\bcu(BLAS|RAND|FFT|DNN)\w*' o
        #      includes tipo <cublas...>/<curand...> → normalizá a lib ("cublas","curand","cufft","cudnn").
        #    - libs = lista ordenada única de librerías detectadas.
        #    - build_system = "cmake" si hay CMakeLists.txt, si no "make" si hay Makefile, si no "make".
        #    - Detección de PTX (para dificultad): presencia de r'asm\s*(volatile)?\s*\('.
        # 2) WAVE64: corré core.wave64.lint_file sobre cada .cu/.cuh; juntá wave64_findings.
        # 3) difficulty (heurística FIJA §5.3, NO LLM):
        #    - "easy"  si (0 PTX ∧ 0 libs ∧ loc_kernels < 2000)
        #    - "hard"  si (hay PTX ∨ "cudnn" en libs ∨ loc_kernels > 10000)
        #    - si no  → "medium"
        # Devolvé ScanResult (importado de core.schemas; NO lo redefinas).

    def portability_report_data(scan: ScanResult) -> dict:
        # Devuelve un dict con los datos ESTRUCTURADOS para el template (inventario, findings,
        # dificultad, conteos). Los NÚMEROS salen de acá (F-17), nunca de un LLM. El párrafo
        # ejecutivo que redacta Gemma se agrega en otra tarea (T12/report); NO llames a ningún LLM acá.
        # Dejá un campo "executive_summary": "" (placeholder que otra capa llenará).

### Test test_scan.py (con el mini-repo fixture que creaste):
- scan(fixture) → files_cuda tiene los .cu; loc_kernels > 0; api_calls incluye "cudaMalloc"/"cudaMemcpy"
  con conteos correctos; libs incluye "cublas"; build_system=="make".
- wave64_findings NO vacío (el __ballot_sync del fixture dispara W01/W02).
- difficulty: el mini-repo (sin PTX, con lib cublas → NO cumple "0 libs") → "medium". Agregá un
  segundo caso: un repo sin libs ni PTX y pocas LOC → "easy". (armá un 2º mini-fixture o dir temporal)
- portability_report_data(scan) devuelve dict con los conteos correctos y "executive_summary"=="".

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_scan.py -q` verde.
2. scan.py importa wave64/schemas/config, NUNCA state/api/oracle (grep vacío). Dirección L4→L2 respetada.
3. difficulty es la heurística FIJA (sin LLM); los números del report salen de código (F-17).

Reglas duras:
- INV-7/F-17: números solo de código; executive_summary queda vacío (lo llena otra capa, no vos, no un LLM).
- Capa L4: no importes hacia arriba (state/api). Importá wave64 (L2) hacia abajo, correcto.
- Al terminar: pytest verde + COMMIT ("feat(phases): scan — inventario + wave64 + dificultad + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
