# HIPnosis — Blueprint de implementación

> **Audiencia de este documento:** agentes ejecutores (Claude Opus o similar) que construirán
> el sistema. Está escrito para ser seguido sin necesidad de re-derivar decisiones. Cuando una
> decisión parezca discutible, ya fue discutida: **sigue el blueprint**. Las desviaciones se
> anotan en `DEVIATIONS.md` con una línea de justificación, nunca se improvisan en silencio.
>
> **Qué es HIPnosis:** pipeline agéntico que toma un repo CUDA, lo porta a ROCm/HIP, lo
> compila/testea/verifica numéricamente en una GPU AMD MI300X real, y entrega un PR + un
> certificado de verificación. Producto para el Track 3 del AMD Hackathon ACT II.

---

## 0. Principios de diseño (leer primero, gobiernan todo lo demás)

1. **El LLM decide contenido; el orquestador decide control.** Ningún LLM elige qué fase
   sigue, cuándo parar, ni qué archivo tocar fuera del parche propuesto. El pipeline es una
   máquina de estados determinista; los LLMs son funciones puras dentro de ella:
   `clasificar(error) → clase` y `proponer_fix(error, contexto) → parche`.
2. **Los oráculos no se negocian.** Compilador, tests y comparador numérico deciden éxito.
   Nunca se le pregunta a un LLM "¿quedó bien?".
3. **Todo cambio al repo objetivo es un commit git atómico y reversible.** Nada de
   reescrituras de archivos completos. Si algo empeora, se revierte con git, no se "arregla
   arreglando".
4. **Todo evento significativo se persiste en el trace JSONL antes de actuar.** El trace es
   la fuente de verdad del dashboard, del debugging y del dataset futuro. Si no está en el
   trace, no pasó.
5. **Degradación honesta.** Un error que no se pudo arreglar no es un fracaso del demo: va al
   reporte como `NEEDS_HUMAN` con su análisis. El reporte honesto ES el producto.
6. **Desarrollable sin GPU.** Todo el pipeline debe poder ejecutarse en modo mock (fixtures de
   salidas de compilador) en cualquier laptop. La GPU solo es necesaria para el oráculo real.
   Esto desacopla el desarrollo del acceso al droplet (ver §9, modo `mock`).

---

## 1. Topología: qué corre dónde

```
┌────────────────────────── Droplet MI300X (AMD Developer Cloud) ──────────────────────────┐
│                                                                                          │
│  docker compose:                                                                         │
│  ┌─────────────────────┐  ┌──────────────────────┐  ┌─────────────────────────────────┐  │
│  │ svc: orchestrator   │  │ svc: vllm            │  │ workspaces/ (bind mount)        │  │
│  │ FastAPI :8080       │──│ Gemma 3 27B IT       │  │ un dir git por run:             │  │
│  │ + dashboard estático│  │ OpenAI-compat :8000  │  │ workspaces/<run_id>/repo/       │  │
│  │ + pipeline + SQLite │  └──────────────────────┘  │ workspaces/<run_id>/trace.jsonl │  │
│  └─────────┬───────────┘                            └─────────────────────────────────┘  │
│            │ subprocess (hipify-perl, make/cmake+hipcc, binarios de test)                 │
│            ▼                                                                              │
│      ROCm 6.x en el host del contenedor (imagen base rocm/dev-ubuntu-22.04)               │
└──────────────────────────────────────────┬───────────────────────────────────────────────┘
                                           │ HTTPS
                              ┌────────────▼────────────┐        ┌──────────────────────┐
                              │ Browser del usuario     │        │ Fireworks AI API     │
                              │ (dashboard)             │        │ (fixer remoto)       │
                              └─────────────────────────┘        └──────────────────────┘
```

**Decisiones y porqués:**
- El orquestador corre **en el droplet**, no en la laptop. Elimina toda una clase de fallas
  (ejecución remota, sincronización de archivos, latencia). La laptop solo abre el browser.
- Los builds corren **dentro del contenedor del orquestador** (que ES la imagen ROCm con
  Python encima). No hay docker-in-docker: un run = un subdirectorio git aislado. Aislamiento
  suficiente para repos curados; DinD es sobreingeniería aquí.
- vLLM usa la **imagen oficial `rocm/vllm`** sin modificar. No compilar vLLM jamás (ver F-01).
- El dashboard es **HTML estático + Tailwind (CDN) + JS vanilla con polling**. Sin build de
  frontend, sin Node en producción, sin SSE (ver F-15). Servido por el propio FastAPI.

---

## 2. Estructura del repositorio

```
hipnosis/
├── README.md                  # pitch + quickstart + GIF (se escribe el día 5)
├── DEVIATIONS.md              # desviaciones del blueprint, una línea c/u
├── docker-compose.yml         # perfiles: gpu (droplet) | replay (cualquier máquina)
├── .env.example               # todas las vars de §10, comentadas
├── docker/
│   └── Dockerfile             # rocm/dev-ubuntu-22.04:6.4 + python3.11 + git + gh + jq
├── orchestrator/
│   ├── pyproject.toml         # deps: fastapi uvicorn pydantic httpx jinja2 pyyaml gitpython pytest
│   ├── app/
│   │   ├── main.py            # FastAPI: monta api + estáticos del dashboard
│   │   └── api.py             # POST /runs, GET /runs/{id}, GET /runs/{id}/events?after=N
│   ├── core/
│   │   ├── config.py          # lee env vars (§10), single source of truth
│   │   ├── state.py           # máquina de estados + persistencia SQLite
│   │   ├── schemas.py         # TODOS los modelos Pydantic (§4)
│   │   ├── trace.py           # append-only JSONL writer/reader
│   │   ├── gitrepo.py         # clone, branch, commit, revert (wrapper de gitpython)
│   │   ├── phases/
│   │   │   ├── scan.py        # FASE 1: inventario + linter wave64 + Portability Report
│   │   │   ├── port.py        # FASE 2: hipify + adaptación de build
│   │   │   ├── loop.py        # FASE 3: build-fix loop
│   │   │   ├── verify.py      # FASE 4: run + parity + timing
│   │   │   └── ship.py        # FASE 5: reporte + branch/PR
│   │   ├── oracle/
│   │   │   ├── base.py        # interfaz: build() run() — y sus resultados tipados
│   │   │   ├── real.py        # subprocess sobre make/hipcc en el workspace
│   │   │   └── mock.py        # replay de fixtures (§9) — mismo contrato
│   │   ├── llm/
│   │   │   ├── client.py      # UN cliente OpenAI-compatible; base_url decide local/remoto
│   │   │   ├── router.py      # política local-vs-remoto (§6.4)
│   │   │   └── prompts.py     # plantillas exactas (§6.5) — NO improvisar prompts en línea
│   │   ├── taxonomy.py        # carga rules.yaml, matching de clases (§6.2)
│   │   ├── rules.yaml         # la taxonomía: clase → patrones → estrategia → tier
│   │   ├── errparse.py        # parser de salida de hipcc/clang (§6.1)
│   │   ├── patcher.py         # bloques SEARCH/REPLACE: validar + aplicar (§6.3)
│   │   ├── wave64.py          # linter estático (§5.2)
│   │   ├── manifest.py        # hipnosis.yaml por repo: cómo correr/verificar (§7.1)
│   │   └── report.py          # Jinja2 → report.md + report.html
│   ├── templates/             # jinja2: portability.md, certificate.md, pr_body.md
│   └── tests/
│       ├── fixtures/          # salidas reales de compilador, repos mini, traces grabados
│       └── test_*.py          # errparse, patcher, wave64, taxonomy, loop-con-mock
├── dashboard/
│   ├── index.html             # timeline + contadores + estado de fases
│   └── app.js                 # polling GET /events?after=N cada 1s, render incremental
├── fixtures/
│   └── demo-run.jsonl         # trace grabado de un run real → modo replay para jueces
└── scripts/
    ├── smoke_test.sh          # §11.1 — SE CORRE ANTES QUE NADA en el droplet
    ├── pick_benchmarks.py     # filtra HeCBench según criterios §7.2
    └── record_fixture.sh      # convierte un run real en fixture de replay
```

---

## 3. La máquina de estados

```
QUEUED → CLONING → SCANNING → PORTING → BUILD_LOOP → RUNNING → PARITY → REPORTING → DONE
                                              │
                                              └→ (presupuesto agotado) → REPORTING → DONE_PARTIAL
   cualquier estado ──(excepción no manejada)──────────────────────────→ FAILED(reason)
```

- Estado persistido en SQLite (`runs` table: id, url, state, started_at, counters JSON).
- Cada transición emite un evento al trace (§4.3) ANTES de ejecutar la fase.
- `DONE_PARTIAL` es un final legítimo y demo-able: el reporte lista lo logrado y lo
  `NEEDS_HUMAN`. No tratar como error.
- Reanudación: si el proceso muere, `state.py` permite retomar desde el último estado
  completado (el workspace git + trace lo hacen posible). No construir reanudación fina
  intra-fase (sobreingeniería); re-ejecutar la fase entera es aceptable.

---

## 4. Esquemas de datos (contratos — `schemas.py`)

Definiciones exactas; los agentes NO cambian nombres de campos (el dashboard y los templates
dependen de ellos).

```python
class Run(BaseModel):
    id: str                    # "run_" + 8 hex
    repo_url: str
    state: str                 # los de §3
    budgets: Budgets
    counters: Counters         # errors_initial, errors_current, fixes_local, fixes_remote,
                               # fixes_deterministic, tokens_local, tokens_remote, iterations

class ScanResult(BaseModel):
    files_cuda: list[str]; loc_kernels: int
    api_calls: dict[str, int]          # "cudaMemcpy": 12, ...
    libs: list[str]                    # ["cublas", "curand"]
    build_system: str                  # "make" | "cmake"
    wave64_findings: list[Wave64Finding]
    difficulty: str                    # "easy" | "medium" | "hard" (heurística §5.3)

class Wave64Finding(BaseModel):
    file: str; line: int; pattern_id: str    # W01..W07 (§5.2)
    snippet: str; severity: str              # "correctness" | "suspicious"
    explanation: str                         # texto fijo del catálogo, NO generado por LLM

class BuildError(BaseModel):
    file: str; line: int; col: int; message: str
    signature: str             # §6.1 — clave de dedupe/historial

class ErrorGroup(BaseModel):
    signature: str; errors: list[BuildError]
    klass: str | None          # id de taxonomía E01.. (None hasta clasificar)
    attempts: int; status: str # "open" | "fixed" | "needs_human"

class FixAttempt(BaseModel):
    group_signature: str; tier: str        # "deterministic" | "local" | "remote"
    patch: str                             # bloques SEARCH/REPLACE crudos
    applied: bool; build_delta: int        # errores_después - errores_antes
    commit_sha: str | None; tokens: int

class VerifyResult(BaseModel):
    ran: bool; exit_code: int
    verdict: str               # "PASS" | "FAIL" | "NO_ORACLE"
    parity_details: str        # qué se comparó y con qué tolerancia
    timing: dict | None        # lo que reporte el benchmark + wall clock
```

### 4.3 Trace JSONL (una línea por evento)

```json
{"ts": "...", "run": "run_ab12cd34", "ev": "phase", "phase": "BUILD_LOOP"}
{"ts": "...", "run": "...", "ev": "build", "iteration": 3, "errors": 17, "delta": -9}
{"ts": "...", "run": "...", "ev": "classify", "sig": "...", "klass": "E05", "tier": "local", "confidence": 0.91}
{"ts": "...", "run": "...", "ev": "fix", "sig": "...", "tier": "local", "applied": true, "delta": -3, "commit": "a1b2c3", "tokens": 412}
{"ts": "...", "run": "...", "ev": "wave64", "file": "reduce.cu", "line": 141, "pattern": "W02"}
{"ts": "...", "run": "...", "ev": "verify", "verdict": "PASS", "detail": "benchmark self-check"}
```

El dashboard consume esto tal cual vía `GET /runs/{id}/events?after=<n>` (n = índice de línea).

---

## 5. FASE 1 — SCAN

### 5.1 Inventario (sin LLM, puro parsing)

- Walk del workspace: archivos `.cu .cuh .h .hpp .cpp` + `Makefile`/`CMakeLists.txt`.
- Conteo de llamadas API CUDA por regex sobre lista blanca (`cuda[A-Z]\w+`, `cu(BLAS|RAND|FFT|DNN)`
  → normalizar a librería). Detección de PTX: `asm\s*(volatile)?\s*\(`.
- `difficulty`: heurística fija — `easy` si (0 PTX ∧ 0 libs ∧ <2k LOC kernels), `hard` si
  (PTX ∨ cuDNN ∨ >10k LOC), si no `medium`. No usar LLM para esto.

### 5.2 Linter wave64 (el arma diferencial — determinista, catálogo cerrado)

| ID | Patrón (regex sobre líneas de código, comentarios ya despojados) | Severidad | Explicación fija (va al reporte) |
|---|---|---|---|
| W01 | `__ballot(_sync)?\s*\(\s*0xffffffff` | correctness | Máscara de 32 bits; en wave64 la máscara/resultado son de 64 bits |
| W02 | `(unsigned|uint32_t|int)\s+\w+\s*=\s*__ballot` | correctness | Resultado de ballot truncado a 32 bits en wave64 |
| W03 | `__popc\s*\(\s*__ballot` | correctness | Debe ser `__popcll` sobre máscara de 64 bits |
| W04 | `__shfl(_up|_down|_xor)?(_sync)?\s*\([^)]*\b32\b` | suspicious | Ancho 32 hardcodeado; wavefront AMD = 64 |
| W05 | `(%|&|/|>>)\s*(32|31|5)\b` en líneas que contengan `threadIdx\|laneId\|lane_id` | suspicious | Aritmética de lane asumiendo warp de 32 (`&31`, `>>5`) |
| W06 | `tiled_partition\s*<\s*32\s*>` | suspicious | Partición cooperative-groups de tamaño warp NVIDIA |
| W07 | `#define\s+WARP_SIZE\s+32` o `constexpr\s+\w*\s*=\s*32.*warp` (case-insens.) | suspicious | warpSize debe consultarse en runtime en HIP, no fijarse en 32 |

Reglas de implementación: despojar comentarios/strings antes de matchear (parser de estados
simple, 30 líneas); cada hallazgo lleva `snippet` = línea ± 2. Los `suspicious` NO se
auto-corrigen (riesgo de romper código correcto); van al reporte y, si generan error o FAIL de
paridad, la clase E12 los referencia. Los `correctness` (W01–W03) sí tienen plantilla de fix.

### 5.3 Portability Report

Generación: datos estructurados → template Jinja2 → Gemma SOLO redacta el párrafo ejecutivo
(3-4 frases) a partir del JSON. Los números nunca los escribe el LLM (F-17). Incluye:
inventario, hallazgos wave64, dificultad, y proyección de ahorro:
`ahorro/año = horas_gpu_año × (precio_h100 − precio_mi300x)` con precios en `config.py`
(constantes editables, citadas en el reporte con fecha).

---

## 6. FASES 2–3 — PORT y BUILD_LOOP (el corazón)

### 6.0 FASE 2: port mecánico

1. `git checkout -b hipnosis/rocm-port` en el workspace.
2. **`hipify-perl -inplace` sobre cada `.cu/.cuh`** (mantener extensión `.cu`: hipcc la
   acepta; NO renombrar archivos — minimiza el diff y evita romper includes). ⚠️ Ver F-02:
   hipify-perl, NO hipify-clang.
3. Adaptación de build (`buildsys.py`), reglas deterministas:
   - **Makefile** (caso HeCBench): `CC = nvcc` → `CC = hipcc`; eliminar `-arch=sm_\d+`,
     `-gencode\S*`, `--use_fast_math`→`-ffast-math`; agregar `--offload-arch=gfx942`.
   - **CMake**: reemplazar `find_package(CUDA)`/`enable_language(CUDA)` por
     `enable_language(HIP)` + `set(CMAKE_HIP_ARCHITECTURES gfx942)`; propiedad
     `LANGUAGE HIP` sobre los `.cu`. Si el CMake es exótico → tratar los errores en el loop
     como clase E13 (tier remoto). No intentar cubrir todo CMake determinísticamente.
4. Commit: `port: hipify-perl + build adaptation`.

### 6.1 Parser de errores (`errparse.py`)

- Regex principal (clang/hipcc): `^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+):\s+(?P<sev>error|fatal error):\s+(?P<msg>.*)$`
  - más líneas de linker: `undefined reference to .*` (file="<link>").
- Tomar **máximo 30 errores** por build (el resto es casi siempre cascada del primero).
- **`signature`** = sha1 de `(basename(file), normalizar(msg))` donde normalizar: reemplaza
  números por `#`, direcciones hex por `@`, contenido entre comillas simples se CONSERVA
  (distingue identificadores). La signature es la clave del historial anti-loop (F-06).
- **Agrupación por causa raíz:** errores con el mismo `msg` normalizado en ≠ archivos → un
  solo grupo (típico: un header roto genera 40 errores). El fix se pide UNA vez sobre el
  archivo del primer error.

### 6.2 Taxonomía (`rules.yaml`) — formato y entradas iniciales

```yaml
- id: E01
  name: leftover_cuda_include
  match: { msg_regex: "cuda_runtime.h|cuda.h.*(not found|no such)" }
  strategy: deterministic          # sustitución fija
  fix_template: 's|#include\s*[<"]cuda_runtime.h[>"]|#include <hip/hip_runtime.h>|'
- id: E02
  name: unconverted_api_call
  match: { msg_regex: "use of undeclared identifier 'cu(da)?[A-Z]" }
  strategy: deterministic          # tabla cuX→hipX (embebida, ~200 entradas del map de hipify)
- id: E05
  name: warp_intrinsic_mismatch
  match: { msg_regex: "__(ballot|shfl|any|all|activemask)" }
  strategy: llm ; tier: local      # con plantillas W01-W03 en el prompt
- id: E04
  name: inline_ptx
  match: { msg_regex: "asm|invalid instruction|ptx" }
  strategy: llm ; tier: remote     # reescritura semántica, siempre remoto
- id: E10
  name: symbol_memcpy
  match: { msg_regex: "hipMemcpyToSymbol|hipGetSymbolAddress" }
  strategy: llm ; tier: local      # regla conocida: envolver símbolo en HIP_SYMBOL(x)
- id: E13
  name: build_system
  match: { file_regex: "CMakeLists|Makefile|<link>" }
  strategy: llm ; tier: remote
- id: E99
  name: unknown
  match: {}                        # catch-all, SIEMPRE al final
  strategy: llm ; tier: local_then_remote
```

(Los agentes completan E03, E06–E09, E11–E12 siguiendo el mismo formato; la lista definitiva
de ~15 clases se calibra el día 2 con los errores reales de los repos demo.)

### 6.3 Formato de parche: bloques SEARCH/REPLACE (decisión firme — ver F-05)

Los LLMs producen diffs unificados inválidos con frecuencia (números de línea, contexto
desalineado). **Prohibido pedir diffs.** El formato es:

```
FILE: src/reduce.cu
<<<<<<< SEARCH
    unsigned mask = __ballot(pred);
    int count = __popc(mask);
=======
    unsigned long long mask = __ballot(pred);
    int count = __popcll(mask);
>>>>>>> REPLACE
```

Contrato del `patcher.py`:
- El texto SEARCH debe aparecer **exactamente una vez** en el archivo (comparación literal,
  con whitespace). 0 apariciones → rechazo `search_not_found`; >1 → rechazo `ambiguous`.
- Ante rechazo: reintentar UNA vez con el error de rechazo en el prompt ("incluye más líneas
  de contexto"). Segundo rechazo → el intento cuenta como fallido, sigue la escalada (§6.4).
- Parche aplicado → `git commit -m "fix(E05): <resumen 1 línea> [tier=local]"`.

### 6.4 El loop y su política de control

```
iteration = 0
while iteration < MAX_ITERATIONS (=25):
    result = oracle.build()
    emit(build, errors=result.count, delta=...)
    if result.count == 0: break                        # → RUNNING
    groups = agrupar(parsear(result.output))
    if no hay grupo "open" con attempts < 3: break     # → REPORTING (DONE_PARTIAL)
    g = grupo open con más errores asociados           # mayor impacto primero
    g.klass = clasificar(g)                            # §6.5-A (Gemma local, JSON)
    tier = decidir_tier(g)                             # ↓
    patch = proponer_fix(g, tier)                      # §6.5-B
    aplicar + commit; rebuild rápido la próxima vuelta
    if delta > 0: git revert HEAD; g.attempts += 1     # empeoró → fuera
    iteration += 1

decidir_tier(g):
    if taxonomy[g.klass].strategy == "deterministic": return "deterministic"
    if g.attempts == 0 and tier_sugerido == "local":  return "local"
    return "remote"                                    # 2º intento o clase dura → remoto
    # 3er intento fallido → status = "needs_human" (nunca >3)
```

- **Anti-oscilación (F-06):** historial de signatures por iteración. Si una signature
  desaparece y reaparece 2 veces → sus fixes se marcan sospechosos, se revierten ambos
  commits y el grupo va directo a tier remoto con el historial completo en el prompt.
- **Detección de estancamiento:** si `errors` no disminuye en 3 iteraciones consecutivas →
  forzar tier remoto global; en 5 → salir a REPORTING (DONE_PARTIAL). Presupuestos en
  `config.py`, nunca hardcodeados en el loop.

### 6.5 Prompts (en `prompts.py`, plantillas exactas)

**A. Clasificador (siempre Gemma local, salida JSON validada con Pydantic, 1 retry):**
```
Eres un experto en portar CUDA a HIP/ROCm. Clasifica este grupo de errores de compilación.
CLASES: {tabla id→nombre→descripción de rules.yaml}
ERRORES: {mensajes del grupo, máx 5}
CONTEXTO: {snippet del primer error, ±10 líneas}
Responde SOLO JSON: {"class": "E05", "confidence": 0.0-1.0, "rationale": "una frase"}
```
`confidence < 0.6` → tratar como E99.

**B. Fixer (local o remoto, mismo template — cambia el modelo):**
```
Eres un experto en portar CUDA a HIP/ROCm para GPUs AMD CDNA3 (MI300X, wavefront de 64 lanes).
Corrige el siguiente error de compilación. REGLAS:
- Cambia lo MÍNIMO necesario. No refactorices. No cambies lógica no relacionada.
- GPUs AMD: wavefront de 64 (no 32); __ballot devuelve 64 bits; usa __popcll; warpSize es
  variable runtime. {inyectar aquí las notas de la clase desde rules.yaml}
- Responde SOLO con bloques FILE/SEARCH/REPLACE (formato de ejemplo abajo). Sin explicación.
ERROR: {mensajes}
ARCHIVO {path} (líneas {a}-{b} de {total}):
{ventana de código: función completa que contiene el error, o ±40 líneas — NUNCA el archivo
entero si >300 líneas (F-11)}
{si attempts>0: HISTORIAL: el intento anterior fue: {patch}; resultado: {qué pasó}. No lo repitas.}
```

**Modelos:** local = `google/gemma-3-27b-it` (vLLM, `temperature=0.1`); remoto =
Qwen3-Coder en Fireworks (id exacto en `config.py`; verificar disponible el día 1, alternativa
DeepSeek V3). Ambos vía el MISMO cliente OpenAI-compatible — cambiar de modelo es cambiar
`base_url`+`model` (esto hace trivial el fallback F-01).

**Caché:** dict persistido `(signature, tier) → patch` — un retry de pipeline no re-paga tokens.

---

## 7. FASE 4 — VERIFY

### 7.1 El manifiesto por repo (`hipnosis.yaml`) — la clave de la generalidad

VERIFY no adivina cómo correr cada repo: lee un manifiesto. SCAN genera un borrador
(heurística: buscar `make run`, binario `main`, README) y **para los repos demo se escribe a
mano el día 1** (esto es curación legítima, no trampa: el producto real lo pediría al usuario).

```yaml
build: { cmd: "make -f Makefile", dir: "src/reduction-cuda" }   # tras adaptación §6.0
run:   { cmd: "./main 1000000 100", timeout_s: 120 }
verify:
  mode: self_check          # self_check | golden_output | none
  pass_regex: "PASS"        # para self_check (HeCBench imprime PASS/FAIL)
  # golden_output: { file: "expected.txt", numeric_rtol: 1e-5 }
timing_regex: "Average kernel execution time.*?([\\d.]+)"
```

- `self_check`: el benchmark se auto-verifica (compara con referencia CPU interna) — **el
  criterio #1 de selección de repos demo** (F-07/F-08 desaparecen por diseño).
- `golden_output`: extraer todos los floats de stdout con regex, comparar posicionalmente
  contra el archivo golden con `rtol` (default 1e-5) — NUNCA comparación exacta de texto (F-09).
- `verdict = NO_ORACLE` si mode=none: el reporte lo dice honestamente.
- Timing: capturar el propio reporte del benchmark + wall clock. **rocprof es stretch goal
  del día 4, no dependencia** (F-10).

### 7.2 Selección de repos demo (día 1, `pick_benchmarks.py`)

Corpus: **HeCBench** (`github.com/zjin-lcf/HeCBench`, `src/<bench>-cuda/`). Criterios del
filtro automático + verificación manual:
1. Existe variante `-cuda` con Makefile estándar (`CC=nvcc`).
2. El código **imprime PASS/FAIL** (grep de "PASS" en el fuente) → oráculo gratis.
3. 500–5,000 LOC.
4. Al menos uno de los 3 usa intrinsics de warp (grep `__ballot\|__shfl`) → momento wow wave64.
5. **REGLA ANTI-FUGA:** copiar SOLO el directorio `-cuda` al workspace. El agente jamás ve la
   variante `-hip` oficial. (Nosotros la usamos aparte para auditar nuestro resultado.)

Perfil buscado: 1 fácil (port 100% mecánico — demuestra velocidad), 1 medio (3-8 fixes del
loop — demuestra el agente), 1 con patrón wave64 real (demuestra el linter). Candidatos
típicos a inspeccionar primero: `reduction`, `scan`, `nbody`, `bsearch`, `atomicIntrinsics`,
`shuffle` — confirmar contra los criterios, no asumir.

---

## 8. FASE 5 — SHIP

- **Reporte** (`report.py`, Jinja2): `certificate.md` + render HTML en dashboard. Secciones:
  resumen ejecutivo, inventario, fixes aplicados (tabla: clase → n → tier → commits),
  hallazgos wave64 (con severidad y explicación fija), verificación (verdict + detalle +
  tolerancias), timing, **"Limitaciones y NEEDS_HUMAN"** (sección obligatoria aunque esté
  vacía), métricas de eficiencia (% fixes locales, tokens local vs remoto — la narrativa
  Track 1).
- **PR:** si `GITHUB_TOKEN` presente → `gh repo fork` + push branch + `gh pr create --body-file`
  contra el fork (NO contra el upstream real de HeCBench — cortesía y control). Si no hay
  token → `git format-patch` + branch local, el reporte enlaza ambos. El PR es azúcar; el
  certificado es el producto (F-13b).

---

## 9. Modos de ejecución (crítico para el desarrollo y para los jueces)

| Modo | `ORACLE_MODE` | Qué hace | Para qué |
|---|---|---|---|
| **real** | `real` | subprocess sobre hipcc/make en el droplet | Producción/demo real |
| **mock** | `mock` | `oracle/mock.py` devuelve salidas de compilador desde fixtures secuenciales (`fixtures/<repo>/build_01.txt`, `build_02.txt`…) | Desarrollar TODO el pipeline (loop, dashboard, reporte) en una laptop sin GPU, y tests de CI |
| **replay** | `replay` | El API sirve un trace JSONL grabado con timing acelerado; no ejecuta nada | `docker compose --profile replay up` — **los jueces ven el dashboard vivo sin MI300X**. Cumple "ejecutable" del reglamento con elegancia |

Regla para los agentes: **el modo mock se construye el DÍA 1 junto con el real**, no después.
Todo test de `loop.py` usa mock. Si el droplet se cae, el desarrollo no se detiene (F-14).

---

## 10. Configuración (env vars — `.env.example` las documenta todas)

```
ORACLE_MODE=real|mock|replay      LOCAL_LLM_BASE_URL=http://vllm:8000/v1
LOCAL_LLM_MODEL=google/gemma-3-27b-it
REMOTE_LLM_BASE_URL=https://api.fireworks.ai/inference/v1
REMOTE_LLM_MODEL=<verificar id exacto día 1>          FIREWORKS_API_KEY=...
HF_TOKEN=...                       # Gemma es gated en HF (F-01c)
GITHUB_TOKEN=... (opcional)        GPU_ARCH=gfx942
MAX_ITERATIONS=25  MAX_ATTEMPTS_PER_GROUP=3  MAX_ERRORS_PARSED=30
CONFIDENCE_THRESHOLD=0.6           PRICE_H100_HR=... PRICE_MI300X_HR=...
```

---

## 11. Catálogo de puntos de falla (leer COMPLETO antes de codear)

| ID | Punto de falla | Prob. | Síntoma | Solución diseñada |
|---|---|---|---|---|
| **F-01** | vLLM-ROCm no sirve Gemma 27B (build, OOM de arranque, incompatibilidad de versión) | Media | El contenedor vllm crashea o cuelga | Cadena de fallbacks EN ORDEN, máx 45 min por escalón: (a) imagen oficial `rocm/vllm` pineada, `--max-model-len 32768`; (b) Gemma 3 **12B**; (c) llama.cpp-ROCm con GGUF; (d) **Gemma vía Fireworks** — mismo cliente OpenAI-compat, cambiar 2 env vars; se pierde "0 tokens locales", el producto sobrevive. La decisión de fallback se toma con cronómetro, no con orgullo. |
| **F-01c** | Gemma gated en HuggingFace, descarga falla | Media | 401 al bajar pesos | Aceptar licencia en HF con la cuenta el DÍA 1 (paso manual del checklist §12); `HF_TOKEN` en .env. Verificado por smoke test. |
| **F-02** | **hipify-clang requiere instalación CUDA para parsear** (trampa clásica: estamos en una máquina AMD sin CUDA) | Alta si se ignora | `hipify-clang` aborta pidiendo headers CUDA | **Decisión firme: hipify-perl** (textual, sin dependencia CUDA, suficiente para repos curados). hipify-clang NI SE INSTALA. Lo que perl traduzca mal aparecerá como error de compilación → lo arregla el loop (esa es la gracia del diseño: el port mecánico imperfecto es tolerable porque hay loop detrás). |
| **F-03** | CMake con `enable_language(CUDA)` falla sin nvcc de formas crípticas | Media | Errores de configure, no de compile | Los 3 repos demo son **Makefile** (HeCBench). CMake se soporta con las reglas §6.0 + clase E13, pero NO se elige un repo CMake para el demo del video. |
| **F-04** | Cascada de errores: 1 header roto = 200 errores, contexto explota | Alta | Prompts gigantes, loop lento | Cap 30 errores parseados; agrupación por causa raíz (§6.1); fix del grupo más poblado primero; ventana de código acotada (§6.5-B). |
| **F-05** | LLM emite diffs/parches inaplicables | Alta con diffs | `git apply` falla siempre | **SEARCH/REPLACE con validación de unicidad** (§6.3) + 1 retry guiado. Nunca diffs unificados, nunca reescritura de archivo completo. |
| **F-06** | Oscilación (fix A rompe B, B rompe A) o loop infinito | Media | Signatures reaparecen, iteraciones se agotan | Historial de signatures + regla de reaparición (revert doble + escalada remota con historial); estancamiento 3→escalada, 5→salida honesta (§6.4). `MAX_ITERATIONS` duro. |
| **F-07** | Sin baseline NVIDIA para paridad (droplet es AMD) | Cierta (es el entorno) | ¿Contra qué comparo? | Diseñada fuera: repos demo con **self-check interno** (PASS/FAIL contra referencia CPU propia — criterio de selección §7.2). Fallback `golden_output`. Dual-cloud = roadmap, se declara en el reporte. |
| **F-08** | Repo sin tests ni verificación | Media en repos arbitrarios | Nada que correr en VERIFY | `verdict=NO_ORACLE` + el certificado lo dice en grande. Para el demo no ocurre (curación). El producto real pediría al usuario el comando y golden (campo del manifiesto). |
| **F-09** | Falsos FAIL de paridad por floating point legítimo (orden de reducción, FMA) | Alta si se compara exacto | "FAIL" en ports correctos | Comparación SIEMPRE por `rtol/atol` sobre floats extraídos, default rtol=1e-5, configurable por manifiesto. Documentado en el certificado ("qué significa PASS"). |
| **F-10** | rocprof: fricción de setup/parseo se come el día 3 | Media | Horas perdidas en profiling | El timing v1 = lo que imprime el benchmark + wall clock. rocprof es stretch del día 4. Está PROHIBIDO tocarlo antes de que VERIFY esté verde. |
| **F-11** | Archivos largos revientan contexto o degradan al fixer local | Media | Fixes malos de Gemma en archivos de 2k líneas | Ventana: función contenedora o ±40 líneas; mapa del archivo (firmas) como contexto adicional; si el parche necesita ver más → eso es señal de tier remoto. |
| **F-12** | Fireworks: rate limit / créditos / modelo no disponible | Baja-media | 429/404 del API | Verificar ID de modelo día 1; backoff exponencial (3 reintentos); caché de fixes (§6.5); modelo alternativo en config. Presupuesto: los $50 de créditos sobran para ~3 repos si el router local hace su trabajo — el contador de tokens del dashboard lo monitorea. |
| **F-13** | Un fix bueno se pierde entre reverts | Baja | Progreso serrucho | Commit por fix aplicado + revert quirúrgico solo del commit culpable (delta>0 identifica al último). El historial git ES el estado. |
| **F-13b** | Sin GITHUB_TOKEN o el push falla en la demo | Media | No hay PR que mostrar | El PR es opcional por diseño: branch local + format-patch + certificado son el entregable. El video muestra un PR real generado ANTES (no en vivo). |
| **F-14** | El droplet muere / créditos / cuota a mitad de semana | Media | Todo parado | Modo mock (§9) desarrollado día 1: el pipeline avanza sin GPU. Fixtures grabadas de cada run real (script `record_fixture.sh`) → el replay para el video existe desde el primer run verde. Snapshot/imagen del droplet tras el smoke test. |
| **F-15** | SSE/websockets: reconexiones, proxies, complejidad | Media | Dashboard congelado en demo | **Polling JSON cada 1s** con `?after=N`. Aburrido, imposible de romper. El video no distingue polling de SSE. |
| **F-16** | Los jueces no pueden reproducir (no tienen MI300X) | Cierta | "no pude correrlo" en evaluación | Perfil `replay` de compose: `docker compose --profile replay up` levanta dashboard + trace real grabado en cualquier laptop. README lo pone como PRIMERA instrucción. |
| **F-17** | El LLM "mejora" números en reportes (alucina métricas) | Media | Certificado con cifras falsas = muerte del producto | Los números SOLO salen de código (counters, parser de timing). El LLM redacta prosa alrededor de un JSON que no puede alterar; el template imprime los valores directamente del JSON. |
| **F-18** | Scope creep de los propios agentes ("agrego soporte X") | Alta | Día 4 sin producto | §13: lista NO-HACER + regla DEVIATIONS.md. Cualquier feature no listada en este blueprint requiere anotación previa. |

---

## 12. Plan de construcción por hitos (con criterios de aceptación)

**M0 — Smoke test del droplet (día 1 mañana, 2h, BLOQUEANTE):** `scripts/smoke_test.sh`:
`rocminfo | grep gfx942` ✓; `hipcc` compila y ejecuta un saxpy HIP de 30 líneas ✓;
`hipify-perl` presente ✓; contenedor `rocm/vllm` sirve Gemma y responde a un curl de chat ✓
(si esto último falla, arrancar cadena F-01 con cronómetro); HeCBench clonado ✓.
**Sin M0 verde no se escribe código de producto.** En paralelo (otro agente): esqueleto del
repo + schemas.py + trace.py + oracle mock.

**M1 — Harness (día 1):** `POST /runs {url}` → CLONING→SCANNING→PORTING→primer build real
con errores parseados y agrupados en el trace. Aceptación: correr contra repo demo #1 produce
un trace con evento `build` y N grupos; los tests de `errparse` y `wave64` pasan con fixtures.

**M2 — Loop (día 2):** el loop completo con router y patcher. Aceptación: **repo demo #1
llega a 0 errores end-to-end en modo real**, y el mismo flujo corre en modo mock en laptop.
Contadores local/remoto/deterministic poblados. Si a las 18:00 del día 2 no hay repo verde →
recortar a 2 repos demo y simplificar taxonomía (solo E01, E02, E05, E99).

**M3 — Verify + certificado (día 3):** manifiestos escritos, VERIFY corre y emite verdict,
certificate.md se genera con todas las secciones. Aceptación: repo #1 con `PASS` real; repo
wave64 muestra findings en el reporte; un run completo QUEUED→DONE sin intervención.

**M4 — Producto (día 4):** dashboard pulido (timeline, contador de errores descendente, badge
"% resuelto localmente"), `docker compose up` limpio en droplet, perfil replay funcionando en
laptop, fixture del mejor run grabada, los 3 repos demo verdes. Stretch (solo si todo verde):
rocprof, PR real contra fork.

**M5 — Submission (día 5):** video según guion (hipnosis.md §3.1) usando replay + tomas del
run real, README con GIF y quickstart replay-first, slides, envío antes de las 12:00.

---

## 13. Reglas para los agentes ejecutores

1. **NO-HACER** (además de lo del blueprint): soporte multi-GPU, repos CMake en el demo,
   frontend con build step, auth, base de datos que no sea SQLite, fine-tuning, rocprof antes
   del día 4, hipify-clang, streaming SSE, reintentos infinitos "porque casi funciona".
2. Bloqueado >30 min en entorno/infra → cambia a modo mock y sigue con el pipeline; anota el
   bloqueo en DEVIATIONS.md para resolverlo en batch.
3. Cada función de `core/` con lógica no trivial (errparse, patcher, wave64, agrupación,
   política de tiers) tiene test con fixture ANTES de integrarse al loop. Las fixtures se
   toman de salidas reales del día 1-2, no se inventan.
4. Commits del producto: convencionales y frecuentes. Commits del workspace objetivo: solo
   los hace el pipeline.
5. Los prompts viven en `prompts.py` y los umbrales en `config.py`. Si necesitas ajustar un
   prompt, ajustas la plantilla, no creas una variante inline.
6. Ante ambigüedad real no cubierta aquí: elige la opción más simple que preserve los
   principios de §0, anótala en DEVIATIONS.md, sigue.
```
