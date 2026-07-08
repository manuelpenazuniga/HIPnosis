Trabajás en el worktree actual (rama spike/t3-oracle). Implementá SOLO esta tarea.

--- TAREA T3: core/oracle/base.py + core/oracle/mock.py — el oráculo (interfaz + mock de fixtures) ---
Capa L3. base.py y mock.py importan SOLO de core.oracle.base, core.schemas, core.config y stdlib.
⛔ PROHIBIDO importar phases, llm, state, errparse (oracle es superficie de ejecución pura; NO
parsea errores con la taxonomía — solo cuenta líneas de error crudamente).

Los tipos de resultado BuildResult y RunResult YA EXISTEN en core.schemas (decisión AD-2): NO los
redefinas, importalos.

ARCHIVOS DE PRODUCTO: orchestrator/core/oracle/base.py, orchestrator/core/oracle/mock.py
TEST: orchestrator/tests/test_oracle_mock.py
FIXTURES (crealas vos): orchestrator/tests/fixtures/mock_build/build_01.txt, build_02.txt, build_03.txt
  y orchestrator/tests/fixtures/mock_build/run.txt

### base.py — interfaz abstracta:

    from abc import ABC, abstractmethod
    from core.schemas import BuildResult, RunResult

    class Oracle(ABC):
        @abstractmethod
        def build(self) -> BuildResult: ...
        @abstractmethod
        def run(self, run_cmd: str | None = None, timeout_s: int = 120) -> RunResult: ...

### mock.py — replay determinista de fixtures (INV-6: mismo contrato que el real):

    class MockOracle(Oracle):
        def __init__(self, fixtures_dir: str): ...
            # fixtures_dir contiene build_01.txt, build_02.txt, ... (salidas de compilador
            # simuladas, secuenciales) y opcionalmente run.txt (stdout de la corrida).
        def build(self) -> BuildResult:
            # En llamadas sucesivas devuelve build_01, build_02, ... en orden. Para cada fixture:
            #   raw_output = contenido del archivo
            #   count = nº de líneas que matchean ': error:' o ': fatal error:' (conteo CRUDO,
            #           NO uses la taxonomía ni errparse — eso es de otra capa)
            #   ok = (count == 0);  returncode = 0 si count==0 else 1
            # La ÚLTIMA fixture debe representar un build limpio (0 errores) para simular el verde.
            # Si se llama build() más veces que fixtures hay, seguí devolviendo la última (clean).
        def run(self, run_cmd=None, timeout_s=120) -> RunResult:
            # Devuelve RunResult(ran=True, exit_code=0, stdout=<contenido de run.txt>, timing=None).
            # Si no hay run.txt, stdout="PASS\n".

Las fixtures que creás deben ser REALISTAS (formato clang/hipcc real). Ejemplos:
- build_01.txt: 3-4 líneas de error estilo
    src/main.cu:12:10: fatal error: 'cuda_runtime.h' file not found
    src/main.cu:45:3: error: use of undeclared identifier 'cudaMemcpy'
- build_02.txt: 1 error restante (simula progreso).
- build_03.txt: vacío o "Build succeeded" (0 errores → verde).
- run.txt: una salida con "PASS" al final (self-check estilo HeCBench).

### Test test_oracle_mock.py:
- MockOracle sobre el dir de fixtures: build() 1ª vez → count>0, ok=False; sucesivas van bajando;
  la última → count=0, ok=True. Llamar una vez más sigue devolviendo clean (idempotente al final).
- run() → ran=True, exit_code=0, "PASS" en stdout.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_oracle_mock.py -q` verde.
2. base.py/mock.py NO importan phases/llm/state/errparse (grep vacío). Solo oracle.base/schemas/config/stdlib.
3. MockOracle.build() secuencial y determinista; la última fixture es clean (ok=True).

Reglas duras:
- INV-6: mock y real comparten el contrato de base.py; ninguna fase debe distinguir el modo.
- INV-2: el oráculo decide éxito por conteo/exit code, jamás un LLM (acá no hay LLM).
- Oracle NO parsea la taxonomía: conteo crudo de errores, nada más (layering L3, no importa errparse L2).
- Al terminar: pytest verde + COMMIT ("feat(oracle): interfaz base + mock de fixtures + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
