Revisá MI código pre-merge por bugs de correctness/contrato. NO modifiques nada: solo LEÉ y REPORTÁ.

Contexto: esto es el CONTRATO base de un pipeline (schemas Pydantic + config de env vars). Todo el
resto del proyecto depende de estos nombres de campo EXACTOS; un rename silencioso rompe el sistema.

Archivos a revisar (en el dir que te pasé):
- orchestrator/core/schemas.py
- orchestrator/core/config.py
- orchestrator/.env.example

Criterios (verificá punto por punto):
1. CORRECTITUD Pydantic v2: ¿los modelos son válidos? ¿defaults sanos? ¿algún tipo mal puesto
   (p.ej. `dict` sin parametrizar donde debería, Optional mal expresado)?
2. FIDELIDAD DE CONTRATO: estos son los campos esperados (nombres EXACTOS, snake_case). Reportá
   CUALQUIER campo faltante, sobrante o renombrado:
   - Budgets: max_iterations, max_attempts_per_group, max_errors_parsed
   - Counters: errors_initial, errors_current, fixes_local, fixes_remote, fixes_deterministic, tokens_local, tokens_remote, iterations
   - Run: id, repo_url, state, budgets, counters
   - Wave64Finding: file, line, pattern_id, snippet, severity, explanation
   - ScanResult: files_cuda, loc_kernels, api_calls, libs, build_system, wave64_findings, difficulty
   - BuildError: file, line, col, message, signature
   - ErrorGroup: signature, errors, klass, attempts, status
   - FixAttempt: group_signature, tier, patch, applied, build_delta, commit_sha, tokens
   - VerifyResult: ran, exit_code, verdict, parity_details, timing
   - BuildResult: ok, count, raw_output, returncode
   - RunResult: ran, exit_code, stdout, timing
   - RunState: constantes QUEUED, CLONING, SCANNING, PORTING, BUILD_LOOP, RUNNING, PARITY, REPORTING, DONE, DONE_PARTIAL, FAILED (+ lista ALL con las 11)
3. CONFIG: ¿get_config() lee las 15 env vars con estos defaults? oracle_mode="mock", max_iterations=25,
   max_attempts_per_group=3, max_errors_parsed=30, confidence_threshold=0.6, gpu_arch="gfx942".
   ¿_getenv_int/_getenv_float rompen con string vacío? ¿int("") explota? (verificá el guard).
4. DIRECCIÓN DE DEPENDENCIAS (invariante del proyecto): schemas.py NO debe importar NADA interno
   (es hoja); config.py solo puede importar core.schemas, NUNCA phases/oracle/llm/state. Reportá violación.
5. .env.example: ¿están las 15 vars comentadas? ¿los secretos (FIREWORKS_API_KEY, HF_TOKEN, GITHUB_TOKEN) van VACÍOS?
6. Casos borde: ¿algo que rompa al importar o al instanciar con defaults?

Formato de salida OBLIGATORIO:
- PRIMERA línea: exactamente `VERDICT: APPROVED` o `VERDICT: CHANGES`
- Por hallazgo: severidad (Crítico/Mayor/Menor) + archivo:línea + fix sugerido en una frase
- ÚLTIMA línea: exactamente `END_AUDIT`
