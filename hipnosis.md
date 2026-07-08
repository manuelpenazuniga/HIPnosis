# HIPnosis — Especificación ultradetallada

> **One-liner:** El port CUDA→ROCm CON pruebas. Pégale la URL de tu repo CUDA y recibe un PR
> verificado: paridad numérica, auditoría de bugs de wavefront y benchmarks en silicio AMD real
> — construido 100% con modelos abiertos.
>
> **Target:** Track 3 (Unicorn) del AMD Developer Hackathon ACT II + premio Gemma
> "mejor proyecto alojado en AMD". Deadline: 11 jul 2026.

---

## PARTE I — Etapa de abstracción profunda

### 1.1 El mapa de capas: dónde ataca cada jugador el moat de CUDA

Todo intento de romper el lock-in de CUDA elige una capa del stack, y **la capa elegida
determina el destino estratégico del proyecto**:

```
        CAPA                  JUGADOR      PROMESA                        DEFECTO ESTRUCTURAL
┌─────────────────────┐
│ Binario / runtime   │  ZLUDA        "tu binario cree que          Emulación perpetua. Persigue
│ (interceptar PTX/   │               sigue en NVIDIA"              para siempre la API de CUDA.
│  driver API)        │                                             El código SIGUE siendo CUDA.
├─────────────────────┤
│ Compilador          │  SCALE        "tu fuente sigue en CUDA,     Cambia lock-in de NVIDIA por
│ (recompilar CUDA    │  (Spectral)   te doy otro compilador"       lock-in de un compilador
│  para AMD)          │                                             cerrado. Código SIGUE en CUDA.
├─────────────────────┤
│ Fuente, sintáctico  │  HIPIFY       "traduzco el 85%              Sin semántica, sin loop, sin
│ (transpilación      │  (AMD)        mecánico"                     verificación. Se detiene donde
│  one-shot)          │                                             empieza el problema.
├─────────────────────┤
│ Generación          │  GEAK         "escribo kernels Triton       No toca codebases existentes.
│ greenfield          │  (AMD)        nuevos desde la intención"    El lock-in vive en el pasado,
│                     │                                             no en el futuro.
├─────────────────────┤
│ ★ MIGRACIÓN DEL     │  HIPnosis     "cruzas la frontera UNA vez,  (el nuestro: ver riesgos §4)
│   ACTIVO, VERIFICADA│               con papeles; el resultado
│   (fuente+semántica │               es ROCm nativo que TÚ posees"
│   +prueba)          │
└─────────────────────┘
```

**El teorema de las capas de compatibilidad:** tratan el síntoma ("mi código no corre en AMD")
preservando la enfermedad ("mi codebase está escrito en el idioma del monopolio"). La historia
es brutal con la categoría: Wine nunca mató a Windows; la compatibilidad Windows de OS/2 mató a
OS/2 (compatibilidad perfecta → nadie porta; imperfecta → nadie confía; en ambos casos la
plataforma anfitriona queda de segunda). El mercado ya votó: ZLUDA perdió su funding (AMD lo
retiró) y es hoy el hobby de una persona; SCALE lleva 7+ años sin respaldo de AMD.

**Framing de pitch en tres palabras:** ZLUDA te deja **correr**. SCALE te deja **recompilar**.
HIPnosis te hace **ciudadano**.

### 1.2 El teorema central: el producto es la confianza, no la traducción

Análisis de cuello de botella. Un CTO mira GPUs AMD ~40% más baratas y con 192 GB de VRAM.
¿Qué lo detiene?

- ❌ NO es "¿se puede convertir el código?" — hipify convierte el 85% gratis desde hace años,
  y la demo viral de Claude Code (ene 2026) probó que un agente generalista hace el resto.
  **La traducción cruda está comoditizada.**
- ✅ ES: *"¿cómo sé que el código convertido es **correcto** y **rápido**, y cuánto me cuesta
  averiguarlo?"* En cómputo científico/ML, un port que compila pero produce números sutilmente
  distintos es **peor que no portar**: es un bug silencioso en producción.

Corolario: **HIPnosis no es un traductor con verificación añadida; es una máquina de
verificación cuyo subproducto es el port.** La unidad de valor no es el diff — es el
**certificado**: paridad numérica medida, auditoría semántica wave32→wave64, benchmark en
silicio real. Esto responde de forma definitiva "¿por qué no usar Claude Code?": la generación
se comoditizó; el harness de verificación, la taxonomía de fallos y el hardware-in-the-loop
son el moat.

### 1.3 Por qué es viable como problema de agente (y un chatbot médico no)

El loop de HIPnosis está anclado por **oráculos no negociables**:

| Oráculo | Pregunta que responde | Negociable con un LLM |
|---|---|---|
| Compilador (hipcc/clang) | ¿Es código válido? | No |
| Tests del repo | ¿Hace lo que hacía? | No |
| Diff numérico (atol/rtol) | ¿Los números son los mismos? | No |
| Profiler (rocprof) en MI300X | ¿Rinde? | No |

Esto convierte un problema abierto de LLM en **búsqueda de lazo cerrado con función objetivo
verificable** — la clase exacta de problema donde los agentes funcionan en 2026 (misma razón
por la que GEAK funciona y los papers UniPar/LASSI reportan tasas altas). La alucinación no se
"mitiga": queda **estructuralmente contenida** porque nada se entrega sin pasar los oráculos.

### 1.4 El activo que se compone: la taxonomía de fallos

Un agente generalista redescubre en cada sesión que `__ballot(0xffffffff)` asume 32 lanes.
HIPnosis lo codifica **una vez** como detector + plantilla de fix, versionado. La taxonomía
inicial (se detalla en §2.4):

1. **Sintáctico/API** — lo cubre hipify (nuestro paso 2, no nuestro valor).
2. **Build system** — CMake con `find_package(CUDA)`, flags nvcc, arquitecturas.
3. **Semántico** ← *aquí vive el valor*: warp 32→wavefront 64, máscaras de ballot/shuffle,
   cooperative groups, semántica de atomics, PTX inline, memoria constante/texturas.
4. **Gaps de librería** — cuDNN→MIOpen, cuBLAS→hipBLAS/rocBLAS, CUB→hipCUB, NCCL→RCCL
   (mapeos con agujeros conocidos y documentables).
5. **Idiomas de rendimiento** — occupancy, LDS banking, tamaños de bloque óptimos difieren.

**El flywheel:** cada repo portado enriquece la taxonomía → cada port siguiente es más barato
y confiable. Y cada trace del loop (error → parche → ¿compiló? → ¿pasó paridad?) es un dato de
entrenamiento con **recompensa verificable** → roadmap natural: entrenar por RL (GRPO estilo
OpenPipe/ART, pero con rewards duros, sin necesidad de RULER) un "Gemma porter" especializado.
*Cada port entrena al porter del siguiente.*

### 1.5 La jugada meta con GEAK

GEAK (el agente de kernels de AMD) no es competencia: es **componente**. Fase de optimización
post-port: los kernels calientes identificados por rocprof se pueden regenerar/optimizar con
GEAK. Frase para el pitch ante el juez de AMD: *"integramos su agente como subrutina del
nuestro"*.

---

## PARTE II — Diseño de implementación

### 2.1 Arquitectura del sistema

```
                    ┌──────────────────────────────────────────────────┐
                    │                  DASHBOARD (Next.js)             │
                    │   URL del repo → timeline en vivo → PR + reporte │
                    └───────────────────────┬──────────────────────────┘
                                            │ REST/SSE
                    ┌───────────────────────▼──────────────────────────┐
                    │            ORCHESTRATOR (FastAPI, Python)        │
                    │  máquina de estados: SCAN→PORT→LOOP→VERIFY→SHIP  │
                    │  emite trace JSONL de cada transición            │
                    └──┬──────────┬──────────┬──────────┬─────────┬────┘
                       │          │          │          │         │
              ┌────────▼───┐ ┌────▼─────┐ ┌──▼───────┐ ┌▼───────┐ ┌▼────────┐
              │ 1. SCANNER │ │ 2. PORTER│ │ 3. FIXER │ │4.VERIFY│ │ 5. SHIP │
              │ inventario │ │ hipify-  │ │ loop     │ │ tests+ │ │ PR +    │
              │ + wave64   │ │ clang +  │ │ err→patch│ │ parity+│ │ reporte │
              │ linter +   │ │ build    │ │ →rebuild │ │ bench  │ │ HTML/MD │
              │ Portability│ │ adapt    │ │          │ │        │ │         │
              │ Report     │ │          │ │          │ │        │ │         │
              └─────┬──────┘ └──────────┘ └────┬─────┘ └───┬────┘ └─────────┘
                    │                          │           │
        ┌───────────▼──────────┐   ┌───────────▼───────────▼───────────────┐
        │  Gemma 3 27B local   │   │      MI300X (AMD Developer Cloud)     │
        │  (vLLM-ROCm en la    │   │  hipcc / ctest / harness paridad /    │
        │   misma MI300X)      │   │  rocprof — LOS ORÁCULOS               │
        │  triage + fixes      │   └───────────────────────────────────────┘
        │  triviales + reports │
        └──────────┬───────────┘
                   │ escala si duda (router token-eficiente)
        ┌──────────▼───────────┐
        │  Fireworks AI API    │
        │  Qwen3-Coder / GLM / │
        │  DeepSeek → fixes    │
        │  semánticos duros    │
        └──────────────────────┘
```

**Decisiones de diseño clave:**

- **Máquina de estados explícita, no "agente libre".** El LLM decide *contenido* (qué parche),
  el orquestador decide *control* (qué fase sigue). Esto hace el sistema debuggeable,
  reanudable y demo-able. Presupuestos duros: máx N iteraciones por error, máx M por repo.
- **Router de dos niveles (la filosofía del Track 1 dentro del producto):** cada error de
  compilación pasa por Gemma local (0 tokens remotos) que lo clasifica contra la taxonomía;
  si matchea plantilla conocida → fix determinista o fix de Gemma; si es novel/duro → escala
  a Fireworks. Métrica exhibible en el dashboard: "% de fixes resueltos localmente".
- **Trace JSONL como ciudadano de primera:** cada transición (error visto, clase asignada,
  parche propuesto, resultado de build) se persiste. Es a la vez: la visualización del
  dashboard, el material de debugging, y el futuro dataset de RL.
- **Parches como diffs unificados**, aplicados con `git apply` — nunca "reescribe el archivo".
  Reversible, inspeccionable, y el PR final es la suma de commits atómicos etiquetados por
  clase de fix.

### 2.2 El pipeline, fase por fase

**FASE 1 — SCAN (sin GPU, corre en cualquier lado → es el freemium):**
- Inventario estático: archivos `.cu/.cuh`, llamadas a librerías CUDA (regex + clang AST),
  build system, LOC de kernels, uso de PTX inline.
- **Linter wave64** (nuestra arma secreta, detección estática por patrones):
  - literales `32` en contexto de lane/warp (`% 32`, `/ 32`, `& 31`, `warpSize` hardcodeado)
  - máscaras de 32 bits: `0xffffffff` en `__ballot_sync`, `__shfl_*_sync`, `__activemask`
  - `__popc` sobre resultados de ballot (debe ser `__popcll` en wave64)
  - tipos `unsigned`/`uint32_t` almacenando resultados de ballot (deben ser 64-bit)
  - cooperative groups con `tiled_partition<32>`
- Salida: **Portability Report** (Markdown/HTML): dificultad estimada por categoría, horas-ing
  ahorradas, y proyección de ahorro en USD (precio/hora MI300X vs H100 × workload del usuario).
- Modelo: Gemma local redacta el reporte a partir del inventario estructurado (JSON → prosa).

**FASE 2 — PORT (mecánico):**
- `hipify-clang` (AST-based, preciso) con fallback a `hipify-perl` para headers problemáticos.
- Adaptación de build: `find_package(CUDA)` → `find_package(hip)`, `enable_language(HIP)`,
  nvcc flags → equivalentes hipcc, `-arch=sm_*` → `--offload-arch=gfx942` (MI300X).
- Mapeo de librerías: cuBLAS→hipBLAS, cuFFT→hipFFT, cuRAND→hipRAND, CUB→hipCUB,
  Thrust→rocThrust, NCCL→RCCL, cuDNN→MIOpen (este último con tabla de gaps conocidos).

**FASE 3 — LOOP (el corazón agéntico):**
```
while build falla y presupuesto > 0:
    errores = parsear salida de hipcc (estructurado: archivo, línea, mensaje)
    agrupar errores por causa raíz (mismo header roto → 1 fix, no 40)
    for grupo in grupos:
        clase = Gemma_local.clasificar(grupo, taxonomía)      # barato
        if clase in plantillas_deterministas: parche = plantilla(grupo)
        elif Gemma_local.confianza > umbral:  parche = Gemma_local.fix(grupo)
        else:                                  parche = Fireworks.fix(grupo + contexto_amplio)
        git apply + rebuild incremental
        registrar (error, clase, parche, resultado) en trace JSONL
```

**FASE 4 — VERIFY (el certificado):**
- **Tests:** ejecutar la suite del repo (ctest/pytest/make test) en la MI300X.
- **Paridad numérica:** comparación **por tolerancia** (`atol/rtol` configurables, default
  1e-5 relativo para FP32) — *nunca* bit a bit: el orden de reducción y los FMA difieren
  legítimamente entre arquitecturas. Baseline (en orden de preferencia):
  1. Golden outputs incluidos en los tests del repo (criterio de selección de repos demo),
  2. implementación CPU de referencia si existe,
  3. (roadmap) runner dual-cloud que ejecuta el original en una instancia NVIDIA.
- **Benchmark:** rocprof sobre los kernels principales → TFLOPs/latencia en el reporte.
- **Auditoría wave64 dinámica:** para cada sitio marcado por el linter en FASE 1, generar un
  micro-test si es posible (valores conocidos a través del shuffle/ballot).

**FASE 5 — SHIP:**
- Rama `hipnosis/rocm-port`, commits atómicos por clase de fix, PR con:
  el Portability Report inicial, tabla de fixes aplicados (clase → cantidad → local/remoto),
  resultado de tests, tabla de paridad numérica, benchmark, y **limitaciones explícitas**
  (qué no se pudo verificar). La honestidad del reporte ES el producto.

### 2.3 Stack técnico

| Componente | Elección | Por qué |
|---|---|---|
| Orquestador | Python 3.11 + FastAPI + SSE | Mismo stack que ya dominas (vertigoDx) |
| Estado del pipeline | SQLite + trace JSONL | Cero infra, portable, suficiente |
| LLM local | Gemma 3 27B-it en vLLM-ROCm (misma MI300X) | Premio Gemma + 192 GB dan de sobra para modelo + builds |
| LLM remoto | Fireworks: Qwen3-Coder (o DeepSeek V3) | Mejor modelo abierto de código disponible en Fireworks |
| Ejecución builds | Docker-in-docker o venvs por repo en el droplet MI300X | Aislamiento entre repos |
| Dashboard | Next.js + Tailwind + shadcn (tu stack de vertigoDx) | Velocidad; SSE para el timeline en vivo |
| Contenedores | `rocm/dev-ubuntu-22.04` base + compose (orquestador, vLLM, dashboard) | Requisito obligatorio del hackathon |
| PR | PyGithub / gh CLI | — |

### 2.4 Selección de repos demo (crítico — hazlo el Día 1)

Criterios: CUDA puro (no PyTorch), CMake/Makefile simple, **con tests o golden outputs**,
1k–20k LOC, y que contenga al menos un patrón wave64 real.

- **Fuente ideal: HeCBench** (benchmark suite heterogénea) — cientos de mini-apps CUDA, muchas
  con versión HIP oficial de referencia. Uso doble: (a) el agente porta la versión CUDA *sin
  ver* la HIP oficial, (b) nosotros validamos nuestro resultado contra la oficial durante el
  desarrollo. Es nuestro set de desarrollo y evaluación gratis.
- Candidatos adicionales: subset de cuda-samples (reduction, scan — usan shuffles con máscaras),
  una librería de hashing/crypto GPU, un solver N-body o stencil con verificación CPU.
- Elegir 3 para la demo: uno fácil (100% automático), uno medio (fixes semánticos visibles),
  uno con **bug wave64 real** para el momento wow del video.

### 2.5 Qué NO construir (anti-sobreingeniería)

- ❌ Soporte multi-GPU / NCCL→RCCL real (solo mapeo sintáctico, documentado como limitación)
- ❌ Porting de proyectos Python/PyTorch (ese mundo ya funciona vía PyTorch-ROCm)
- ❌ Optimización de rendimiento agresiva (solo medir y reportar; GEAK es roadmap)
- ❌ Auth/usuarios/billing en el dashboard
- ❌ Fine-tuning del porter (es roadmap post-hackathon, se menciona en slides)

---

## PARTE III — Roadmap

### Fase 0: Hackathon (6–11 jul) — "el certificado existe"

| Día | Entregable | Detalle |
|---|---|---|
| **1 (mar 7)** | Infra + repos | Droplet MI300X, imagen Docker ROCm+hipify+vLLM, Gemma 27B sirviendo. Harness clone→hipify→build→parseo de errores. Elegir los 3 repos demo desde HeCBench. |
| **2 (mié 8)** | El loop | FASE 3 completa con router Gemma/Fireworks + taxonomía v1 (10-15 clases) + trace JSONL. Primer repo compilando verde end-to-end. |
| **3 (jue 9)** | El certificado | FASE 4: tests + harness de paridad por tolerancia + rocprof. Linter wave64 (FASE 1). Generación de PR + Portability Report. |
| **4 (vie 10)** | Producto | Dashboard con timeline SSE. `docker compose up` funciona limpio. Los 3 repos demo pasando. Pulido. |
| **5 (sáb 11)** | Submission | Video (guion en §3.1), README con GIF, slides, envío. Stretch: extraer router → entrada Track 1. |

### 3.1 Guion del video de demo (3 min — el activo #1)

1. (0:00) El gancho: titular de prensa de Claude Code portando CUDA en 30 min → "pero
   ¿quién garantizó que los números eran correctos? Nadie. Eso es HIPnosis."
2. (0:30) Pegar URL del repo → Portability Report instantáneo (ahorro en USD en pantalla).
3. (1:00) Timeline en vivo: hipify → 47 errores → contador bajando → verde. Mostrar el
   badge "83% resuelto localmente por Gemma, 0 tokens remotos".
4. (1:45) **El momento wow:** el linter marca `__ballot(0xffffffff)` → "esto compila
   perfecto en AMD y da resultados INCORRECTOS en silencio — warp 32 vs wavefront 64.
   Ningún tool lo detecta. HIPnosis sí." → fix → test de paridad pasa.
5. (2:20) El PR final: diff, tabla de paridad, benchmark TFLOPs en MI300X.
6. (2:45) Cierre: mercado (precio H100 vs MI300X), roadmap (CI, GEAK, Gemma porter por RL),
   "cada port entrena al siguiente".

### Fase 1: Post-hackathon, semanas 1–8 — "de demo a herramienta"

- Endurecer el harness sobre 30-50 repos de HeCBench (métricas: % auto-portado, % paridad).
- **GitHub App modo CI:** cada PR del cliente se compila también contra ROCm ("¿este cambio
  rompe tu compatibilidad AMD?") — convierte producto one-shot en suscripción.
- Runner dual-cloud para baseline de paridad contra NVIDIA real.
- Publicar el linter wave64 como herramienta OSS standalone (top-of-funnel, credibilidad).

### Fase 2: Meses 3–6 — "el flywheel"

- Taxonomía v2 alimentada por los ports reales; plantillas deterministas para el top-20 de
  clases de error.
- **Gemma porter fine-tuneado:** SFT sobre los traces acumulados (error→parche exitoso), luego
  GRPO con rewards duros (compila/testea/paridad) — la lección OpenPipe con ventaja: no
  necesitamos RULER, nuestros rewards son verificables. Meta: >95% de fixes locales.
- Integración GEAK para optimización de kernels calientes post-port.
- Design partners: 2-3 equipos de HPC/ML con codebases CUDA medianas y factura NVIDIA alta.

### Fase 3: Meses 6–12 — "la empresa"

- Enterprise: on-prem del pipeline (los codebases CUDA valiosos no salen de la empresa).
- Pricing: report gratis → port por repo (fixed fee según report) → CI por suscripción.
- La conversación con AMD: esto es developer-ecosystem tooling que a AMD le conviene
  subsidiar/adquirir (ellos financian consultores para esto hoy; GEAK muestra que compran
  la tesis de agentes).

---

## PARTE IV — Riesgos y respuestas

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Build-system hell consume los 5 días | Alta | Repos curados de HeCBench (build uniforme); imagen base pre-horneada; presupuesto duro por repo |
| "hipify ya hace casi todo" (objeción de juez) | Media | La demo muestra el contador 47→0 *después* de hipify + el bug wave64 que hipify no ve |
| "¿Por qué no Claude Code?" (objeción de juez) | Alta | §1.2: la generación está comoditizada; el certificado no. Además: modelos abiertos = requisito del hackathon y soberanía del cliente |
| Paridad sin baseline NVIDIA | Media | Repos con golden outputs; referencia CPU; dual-cloud declarado como roadmap honesto |
| vLLM-ROCm + Gemma da problemas día 1 | Baja-media | Fallback: Gemma vía Fireworks también (pierde "0 tokens" pero no el producto); segundo fallback: llama.cpp ROCm |
| El loop diverge en un error (loop infinito) | Media | Presupuesto por error (3 intentos) y por repo; errores sin fix van al reporte como "requiere humano" — honestidad = producto |

---

## PARTE V — Mapeo contra criterios del jurado

| Criterio | Argumento |
|---|---|
| **Creatividad/Originalidad** | Carril vacío verificado (§1.5 de ideas.md): cero productos, cero proyectos ACT I. El ángulo "verificación, no traducción" es contraintuitivo y defendible. |
| **Potencial de mercado** | Ahorro cuantificable: Δprecio/hora GPU × horas anuales × #empresas bloqueadas por CUDA. AMD paga consultores por esto HOY. Freemium (report) → fee (port) → suscripción (CI). |
| **Completitud** | 3 repos portados end-to-end, PR reales generados, dashboard en vivo, `docker compose up`. |
| **Uso de plataformas AMD** | Máximo estructural: ROCm es el sustrato, la MI300X es el oráculo, Gemma corre en vLLM-ROCm, Fireworks es el fixer remoto, y GEAK está en el roadmap. El proyecto no tiene sentido sin AMD. |
