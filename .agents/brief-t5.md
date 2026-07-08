Trabajás en el worktree actual (rama spike/t5-errparse). Implementá SOLO esta tarea.

--- TAREA T5: core/errparse.py — parser de errores de compilador + signature + agrupación ---
Capa L2: importa SOLO core.schemas, core.config y stdlib (re, hashlib, os). NO importa
phases/oracle/llm/state. Es el insumo del loop: convierte raw_output del compilador en grupos.

ARCHIVO DE PRODUCTO: orchestrator/core/errparse.py    TEST: orchestrator/tests/test_errparse.py
FIXTURES (crealas, realistas — formato hipcc/clang real): orchestrator/tests/fixtures/errparse/
  build_leftover_include.txt, build_undeclared_api.txt, build_cascade.txt

### Contrato de errparse.py (blueprint §6.1):

    def parse(raw_output: str, max_errors: int = 30) -> list[BuildError]:
        # Regex principal (clang/hipcc):
        #   ^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s+(?P<sev>error|fatal error):\s+(?P<msg>.*)$
        # Más líneas de linker: 'undefined reference to .*'  → BuildError(file="<link>", line=0, col=0).
        # Tomá MÁXIMO max_errors errores (el resto suele ser cascada). Cada BuildError lleva su signature.

    def signature(file: str, msg: str) -> str:
        # sha1 hexdigest de f"{basename(file)}|{normalize(msg)}".
        # normalize(msg): números -> '#', direcciones hex (0x[0-9a-f]+) -> '@', pero el contenido
        # entre COMILLAS SIMPLES se CONSERVA literal (distingue identificadores como 'cudaMemcpy').
        # Ej: "use of undeclared identifier 'cudaMemcpy'" y la misma con 'cudaFree' → signatures DISTINTAS.
        #     "expected 42 args" y "expected 7 args" → MISMA signature (números normalizados a #).

    def group(errors: list[BuildError]) -> list[ErrorGroup]:
        # Agrupá por msg normalizado (misma signature) AUNQUE estén en archivos distintos:
        # un header roto genera el mismo error en 40 archivos → UN solo grupo.
        # Cada ErrorGroup: signature (la del grupo), errors (la lista), klass=None, attempts=0, status="open".
        # Ordená los grupos por nº de errores DESC (mayor impacto primero) — el loop toma el primero.

BuildError y ErrorGroup YA EXISTEN en core.schemas: importalos, no los redefinas.
max_errors default debe poder venir de config (Config.max_errors_parsed=30); en la firma dejá 30
como default pero permití pasarlo.

### Test test_errparse.py (con las fixtures reales que creaste):
- parse(build_leftover_include): detecta el 'cuda_runtime.h' file not found con file/line/col correctos.
- parse(build_undeclared_api): detecta "use of undeclared identifier 'cudaMemcpy'".
- signature: dos msgs que solo difieren en un número → MISMA signature; dos que difieren en el
  identificador entre comillas simples → signatures DISTINTAS. (tests NEGATIVOS explícitos)
- group sobre build_cascade (mismo error en varios archivos) → UN grupo con N errores.
- parse respeta max_errors (armá un raw con 50 errores, pedí max_errors=30 → len==30).
- línea de linker 'undefined reference to `foo`' → un BuildError con file="<link>".

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_errparse.py -q` verde.
2. errparse.py NO importa phases/oracle/llm/state (grep vacío).
3. La normalización de signature es EXACTA: números→#, hex→@, comillas simples conservadas
   (el test negativo de identificadores distintos debe pasar).

Reglas duras:
- Capa L2 pura. Umbrales (max_errors) vienen de config, no hardcodeados en lógica (INV-9).
- Fixtures realistas: formato de error clang/hipcc REAL (file:line:col: error: msg). No inventes un formato propio.
- Al terminar: pytest verde + COMMIT ("feat(core): errparse (parse/signature/group) + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
