# CLAUDE.md

## Qué es este repo

**HIPnosis** — agente autónomo que porta código CUDA a ROCm/AMD: recibe la URL de un repo,
lo convierte con `hipify-perl`, y un loop determinista compila, parchea (vía LLM), testea y
verifica paridad numérica en una MI300X real hasta dejarlo verde. Entrega branch/PR +
certificado de port con métricas.

Proyecto para el **AMD Developer Hackathon: ACT II** (lablab.ai) — **Track 3 (Unicorn)** +
premio especial Gemma. **Deadline: 11 de julio de 2026, 12:00 PM (Chile).**
Requisito duro del hackathon: envío contenedorizado y ejecutable.

## Jerarquía de documentos (dónde vive la verdad)

1. **`hipnosis-blueprint.md`** — LA fuente de verdad de implementación. Antes de escribir
   código: leer **§0 (principios)**, **§11 (catálogo de puntos de falla)** y **§13 (reglas
   para agentes ejecutores)**. La estructura de código sigue §2 al pie de la letra.
2. **`hipnosis.md`** — spec estratégica (por qué existe el producto, pitch, roadmap, video).
   Contexto, no instrucciones de código.
3. **`docs/ideas.md`** y **`docs/des.md`** — brainstorm original y bases del hackathon.
   Solo referencia histórica/reglas del evento.
4. **`docs/extra/`** — workflow de orquestación del equipo. **No leerlo ni usarlo como
   contexto del producto.**

Si este archivo y el blueprint difieren, **gana el blueprint**.

## Principios innegociables (resumen de blueprint §0)

- **El LLM decide contenido; el orquestador decide control.** Máquina de estados determinista;
  los LLMs son funciones puras: `clasificar(error) → clase`, `proponer_fix(...) → parche`.
- **Los oráculos no se negocian.** Compilador + tests + comparador numérico deciden éxito.
  Jamás se le pregunta a un LLM "¿quedó bien?".
- **Todo cambio al repo objetivo = commit git atómico y reversible.** Nada de reescrituras
  de archivos completos.
- **Trace JSONL append-only antes de actuar.** Si no está en el trace, no pasó.
- **Degradación honesta:** lo que no se pudo arreglar va al reporte como `NEEDS_HUMAN`.
- **Desarrollable sin GPU:** modo `mock` (fixtures) se construye el DÍA 1 junto al real.

## Decisiones firmes (no re-litigar; detalle en blueprint)

- **`hipify-perl`, NUNCA `hipify-clang`** (requiere headers CUDA que no existen en la máquina
  AMD — F-02). Lo que perl traduzca mal lo arregla el loop.
- Parches en **bloques SEARCH/REPLACE con validación de unicidad** (§6.3) — nunca diffs
  unificados ni archivos completos (F-05).
- Routing híbrido: **Gemma 3 27B IT local** (imagen oficial `rocm/vllm`, sin compilar nada)
  para fixes triviales; **Fireworks** para los duros (§6.4). Cadena de fallbacks de F-01.
- Dashboard: **HTML estático + JS vanilla + polling cada 1s** (`?after=N`). Sin SSE, sin
  build de frontend (F-15).
- Modos `real` / `mock` / `replay` (§9). El perfil `replay` de compose es cómo los jueces
  ejecutan el proyecto sin MI300X (F-16).
- Los números de reportes/certificados **solo salen de código**, nunca del LLM (F-17).
- Paridad numérica siempre por `rtol/atol`, nunca comparación exacta de floats (F-09).
- Repos demo: **Makefile (HeCBench), con self-check interno**; nada de CMake en el demo
  (F-03, F-07, §7.2).

## NO-HACER (blueprint §13)

Multi-GPU · repos CMake en el demo · frontend con build step · auth · DB que no sea SQLite ·
fine-tuning · rocprof antes del día 4 · hipify-clang · SSE · reintentos infinitos.
Cualquier desviación del blueprint se anota en **`DEVIATIONS.md`** (una línea) ANTES de
implementarla. Bloqueado >30 min en infra → modo mock y seguir (§13.2).

## Stack y topología (blueprint §1)

Todo corre en el droplet MI300X vía `docker compose`: orquestador FastAPI (:8080, sirve
dashboard + pipeline + SQLite) + vLLM con Gemma (:8000, OpenAI-compat) + workspaces git por
run. Builds por subprocess dentro del contenedor del orquestador (imagen base
`rocm/dev-ubuntu-22.04`); sin docker-in-docker. La laptop solo abre el browser.

## Estado y convenciones

- Aún no hay código: al crearlo, seguir la estructura de blueprint §2 y el plan por hitos §12
  (M0 = smoke test del droplet, bloqueante).
- Tests con fixtures reales ANTES de integrar cada pieza al loop (errparse, patcher, wave64,
  taxonomy) — §13.3. Prompts solo en `prompts.py`; umbrales solo en `config.py`.
- Commits del producto: convencionales y frecuentes. Los commits del workspace objetivo los
  hace solo el pipeline.
- Este repo aún no tiene `git init` ni remote — la submission exige repo público de GitHub
  con README.
