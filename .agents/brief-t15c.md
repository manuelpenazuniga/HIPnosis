Trabajás en el worktree actual (rama spike/t15c-verify). Implementá SOLO esta tarea.

--- TAREA T15c: core/phases/verify.py — FASE 4 VERIFY (§7): correr + paridad + timing ---
Capa L4. Importa core.manifest, core.parity (existen), core.oracle.base, core.schemas, core.config,
core.trace, stdlib. NO importa llm/state/patcher.

ARCHIVO: orchestrator/core/phases/verify.py    TEST: orchestrator/tests/test_verify.py

Contrato:
    def verify(manifest, oracle, repo_dir, config, trace=None) -> VerifyResult:
        # 1. Correr el benchmark: result = oracle.run(manifest.run.cmd, manifest.run.timeout_s).
        #    (mock devuelve el run.txt fixture con PASS; real corre el binario).
        # 2. Según manifest.verify.mode:
        #    - "self_check": ParityResult = parity.check_self_check(result.stdout, manifest.verify.pass_regex).
        #      verdict = "PASS" si ok else "FAIL".
        #    - "golden_output": leer el golden (manifest.verify.golden_file, relativo a repo_dir). Si el
        #      manifiesto trae output_file, leer ESE archivo del repo_dir como "actual"; si no, usar
        #      result.stdout. ParityResult = parity.check_golden(actual, golden, rtol, atol de manifest).
        #      verdict = "PASS"/"FAIL".
        #    - "none": verdict = "NO_ORACLE" (el reporte lo dice honestamente, F-08).
        # 3. timing: si manifest.timing_regex, extraer de result.stdout (regex, primer grupo → float).
        # 4. Devolver VerifyResult(ran=result.ran, exit_code=result.exit_code, verdict=<...>,
        #    parity_details=ParityResult.detail, timing={...} o None). Emitir evento "verify" al trace.
    def verify_handler(ctx) -> None:
        # handler de fase para el driver de state (RUNNING+PARITY). Corre verify con el manifest y oracle
        # del ctx, guarda VerifyResult en ctx (para REPORTING) y actualiza el trace.

VerifyResult y ParityResult ya existen (schemas / parity). NO comparación exacta de floats (F-09,
lo hace parity). NO_ORACLE es final legítimo (INV-5).

Test test_verify.py (con MockOracle + manifiestos de fixtures):
- self_check con run.txt que contiene 'PASS' + pass_regex 'PASS' → verdict PASS.
- self_check con stdout 'FAIL' → verdict FAIL.
- mode 'none' → verdict NO_ORACLE.
- golden_output: stdout/golden con mismos floats → PASS; distintos → FAIL.
- timing_regex extrae el número correcto.

Criterios: pytest verde; NO importa llm/state; NO_ORACLE cuando mode=none; usa parity (no reimplementa comparación).
Al terminar: COMMIT ("feat(phases): verify — run + paridad + timing (§7) + tests"). Respuesta CORTA. Bloqueo: 'BLOCKED |...'.
ENTORNO: venv en /Volumes/MacMiniExt/dev/ZedProjects/hipnosis-venv/bin/python. El contrato base ya existe en main.
