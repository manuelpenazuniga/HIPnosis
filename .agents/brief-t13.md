Trabajás en el worktree actual (rama spike/t13-port). Implementá SOLO esta tarea.

--- TAREA T13: core/buildsys.py + core/phases/port.py — FASE 2 PORT (hipify + adaptar build) ---
Capa: buildsys.py = L2 (primitiva pura, Python determinista, SIN subprocess). port.py = L4 (phase).
port.py importa buildsys, core.gitrepo, core.schemas, core.config, core.trace. buildsys.py importa
solo stdlib (re, os). ⛔ Ninguno importa oracle/llm/state.

ARCHIVOS: orchestrator/core/buildsys.py, orchestrator/core/phases/port.py
TESTS: orchestrator/tests/test_buildsys.py (el grueso), orchestrator/tests/test_port.py (estructura)

### buildsys.py — adaptación DETERMINISTA del sistema de build (blueprint §6.0). Python puro, testeable
sin ROCm. ESTA es la parte importante y con tests reales:

    def adapt_makefile(text: str, gpu_arch: str = "gfx942") -> str:
        # Reglas EXACTAS (§6.0, caso HeCBench):
        #   - CC = nvcc            -> CC = hipcc   (y variantes: NVCC=, CXX=nvcc)
        #   - eliminar flags -arch=sm_XX  y  -gencode ...  y  --use_fast_math -> -ffast-math
        #   - agregar --offload-arch=<gpu_arch>  (si no está ya)
        # Devolvé el texto adaptado. Idempotente (correrlo 2 veces no rompe).

    def adapt_cmake(text: str, gpu_arch: str = "gfx942") -> str:
        # Reglas §6.0:
        #   - find_package(CUDA) / enable_language(CUDA) -> enable_language(HIP)
        #   - agregar set(CMAKE_HIP_ARCHITECTURES <gpu_arch>)
        # (CMake exótico se maneja como error E13 en el loop; acá cubrí lo básico. Los repos DEMO
        #  son Makefile — CMake es best-effort.)

    def adapt_build(repo_dir: str, build_system: str, gpu_arch: str = "gfx942") -> list[str]:
        # Aplica adapt_makefile/adapt_cmake al/los archivo(s) de build EN DISCO (lee, adapta,
        # reescribe). Devuelve la lista de archivos modificados. build_system: "make"|"cmake".

### port.py — orquesta la FASE 2 (blueprint §6.0). port.py NO se testea contra hipify real (hipify-perl
es ROCm-only, no está en dev). Diseñá con un SEAM para que sea mock-aware:

    def port(repo, repo_dir: str, scan_result, config, trace=None) -> PortResult:
        # `repo` = core.gitrepo.GitRepo. Pasos:
        # 1. repo.checkout_branch("hipnosis/rocm-port")
        # 2. HIPIFY: por cada .cu/.cuh de scan_result.files_cuda, correr hipify-perl -inplace VÍA
        #    subprocess. PERO: encapsulá la invocación en una función `run_hipify(paths) -> None`
        #    que sea reemplazable/mockeable, y que en modo mock (config.oracle_mode != "real")
        #    NO ejecute hipify (los fixtures ya representan el estado post-hipify). Emití al trace
        #    (INV-4) qué archivos se hipificaron (o que se saltó en mock).
        # 3. Adaptar build con buildsys.adapt_build(repo_dir, scan_result.build_system, config.gpu_arch).
        # 4. repo.commit_all("port: hipify-perl + build adaptation") -> sha.
        # Devolvé PortResult(dataclass: branch, hipified_files:list, build_files:list, commit_sha, mode).
    # ⚠️ F-02: hipify-PERL, jamás hipify-clang. NO renombrar archivos .cu (hipcc los acepta).

### Tests:
test_buildsys.py (el importante, determinista):
- adapt_makefile: "CC = nvcc" -> "CC = hipcc"; elimina "-arch=sm_70" y "-gencode arch=..."; agrega
  "--offload-arch=gfx942"; "--use_fast_math" -> "-ffast-math". Idempotencia (2x = 1x).
- adapt_cmake: enable_language(CUDA) -> enable_language(HIP); agrega CMAKE_HIP_ARCHITECTURES.
- adapt_build sobre un Makefile temporal en tmp_path: lo reescribe y devuelve [ruta].
  Usá un Makefile realista tipo HeCBench (CC=nvcc, -arch=sm_60, etc.) — podés basarte en
  fixtures/scan_repo/Makefile si existe, o creá uno.
test_port.py (estructura, sin hipify real):
- port() en modo mock (config.oracle_mode="mock"): NO llama hipify (mockealo/verificá que run_hipify
  no ejecuta subprocess), pero SÍ crea la rama, adapta el build y commitea. Verificá PortResult.
- Usá un repo git temporal (GitRepo) + un Makefile.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_buildsys.py tests/test_port.py -q` verde.
2. buildsys.py Python puro (sin subprocess), adapt_makefile idempotente y con las reglas §6.0 exactas.
3. port.py en modo mock NO ejecuta hipify-perl (seam mockeable); sí adapta build + commitea (gitrepo, INV-3/INV-4).
4. buildsys/port NO importan oracle/llm/state.

Reglas duras:
- F-02: hipify-PERL, NUNCA hipify-clang. No renombrar .cu.
- INV-3/INV-4: cambios al repo objetivo vía gitrepo (commit atómico) + evento al trace antes.
- Umbrales/arch desde config (INV-9). gpu_arch default gfx942.
- Al terminar: pytest verde + COMMIT ("feat(phases): port hipify-seam + buildsys adaptación Makefile/CMake + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
