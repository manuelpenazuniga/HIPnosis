Trabajás en el worktree actual (rama spike/t15a-manifest). Implementá SOLO esta tarea.

--- TAREA T15a: core/manifest.py + schema del manifiesto por repo (hipnosis.yaml) ---
Capa L2: importa core.schemas, pyyaml, stdlib. NO importa phases/oracle/llm/state.
El manifiesto (§7.1) le dice a VERIFY cómo correr y verificar cada repo (así el producto es general).

ARCHIVO: orchestrator/core/manifest.py    TEST: orchestrator/tests/test_manifest.py
FIXTURE: orchestrator/tests/fixtures/manifests/sample.yaml (un ejemplo válido para el test)

### Formato del manifiesto (blueprint §7.1) — hipnosis.yaml por repo:
    build: { cmd: "make -f Makefile", dir: "src/reduction-cuda" }
    run:   { cmd: "./main 1000000 100", timeout_s: 120 }
    verify:
      mode: self_check              # self_check | golden_output | none
      pass_regex: "PASS"            # para self_check
      # golden_output: { file: "expected.txt", numeric_rtol: 1e-5 }
    timing_regex: "Average kernel execution time.*?([\\d.]+)"

### Contrato de manifest.py:

    @dataclass
    class BuildSpec:  cmd: str; dir: str = "."
    @dataclass
    class RunSpec:    cmd: str; timeout_s: int = 120
    @dataclass
    class VerifySpec:
        mode: str                    # "self_check" | "golden_output" | "none"
        pass_regex: str | None = None
        golden_file: str | None = None
        numeric_rtol: float = 1e-5
        numeric_atol: float = 1e-8
    @dataclass
    class Manifest:
        build: BuildSpec
        run: RunSpec
        verify: VerifySpec
        timing_regex: str | None = None

    def load_manifest(path: str) -> Manifest:
        # Parsea el YAML y valida:
        #   - build.cmd y run.cmd presentes (no vacíos).
        #   - verify.mode in {"self_check","golden_output","none"}.
        #   - si mode=="self_check" → pass_regex requerido.
        #   - si mode=="golden_output" → golden_file requerido.
        # Lanzá ValueError con mensaje claro si algo falta/está mal.

    def draft_manifest(scan_result, repo_dir: str) -> Manifest:
        # Heurística para SCAN (§7.1): borrador automático. Busca 'make run' o binario 'main',
        # default verify.mode="self_check" pass_regex="PASS", timeout 120. Es un BORRADOR (para
        # repos demo se escribe a mano); devolvé algo razonable, no perfecto.

### Test test_manifest.py:
- load_manifest sobre sample.yaml (self_check) → Manifest con build/run/verify correctos.
- load_manifest con mode inválido → ValueError. self_check sin pass_regex → ValueError.
  golden_output sin golden_file → ValueError.
- draft_manifest sobre un ScanResult mínimo → devuelve un Manifest con defaults sanos.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_manifest.py -q` verde.
2. Validación fail-closed: mode inválido / campos requeridos faltantes → ValueError.
3. manifest.py NO importa phases/oracle/llm/state.

Reglas duras:
- El manifiesto es DATA; no ejecuta nada (eso es verify.py, otra tarea). Umbrales de tolerancia default en la firma.
- Al terminar: pytest verde + COMMIT ("feat(core): manifest loader + schema hipnosis.yaml + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
