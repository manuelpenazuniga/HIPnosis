# Prompt de inicio — HIPnosis, v3 DIVIDIDO (dos cerebros)

> Adaptación de `orchestration-prompts.md` §4.3 para este proyecto. Cambios respecto del
> original: rutas de los playbooks (en este repo viven en `docs/extra/`, sin prefijo
> `ai-dev-workflow/`) y el bloque de objetivo, ahora específico de HIPnosis. Todo lo demás
> es idéntico.
>
> **Cómo usarlo:** desde la raíz del repo, lanzá la sesión orquestadora con
> `claude --model sonnet --effort medium` y pegá el prompt de abajo como primer mensaje.
> (Prerequisito §4.2 ya verificado: Fable responde en headless.)

---

```
Lee ENTERO docs/extra/orchestration-workflow-v2.md y DESPUÉS
docs/extra/orchestration-workflow-v3.md. Vas a ejecutar v3 en modo DOS CEREBROS:

- VOS (esta sesión) llevás el sombrero ORQUESTADOR: todo el ciclo v2 (worktrees, briefs, lanzar,
  watchdog, verificar, panel externo, merge, estado). Lo mecánico es 100% tuyo.
- El sombrero ARQUITECTO y el pase de ESTRUCTURA los ejerce un modelo superior por consulta
  headless. Protocolo de consulta (bus de archivos):
  1. Escribí el contexto MÍNIMO en .agents/ARCHITECT_INPUT.md: qué necesitás (diseño de tarea /
     pase de estructura / checkpoint), el bloque de tarea o el diff-stat + archivos clave, y las
     secciones relevantes de ARCHITECTURE.md (no el repo entero).
  2. Ejecutá (esfuerzo: diseño y pase de estructura = high; checkpoint = xhigh):
     claude -p --model claude-fable-5 --effort high "Sos el Arquitecto de v3 (lee
     docs/extra/orchestration-workflow-v3.md, secciones 1, 3 y 4). Lee
     .agents/ARCHITECT_INPUT.md y respondé SOLO lo pedido. Si es pase de estructura, terminá con
     una línea exacta 'ESTRUCTURA: OK|AJUSTE|RECHAZO | <motivo>'. Si es checkpoint, respondé las
     6 preguntas de v3 §4.2 en formato CP-<n>. Sé conciso." > .agents/ARCHITECT_ANSWER.md
  3. Parseá la última línea / el bloque CP y APLICÁ lo que diga. Copiá los AD/INV/CP nuevos a
     ARCHITECTURE.md / BITACORA.md.
- CUÁNDO consultás al arquitecto (y SOLO entonces):
  (a) diseño de una tarea nueva no trivial o que fuerza una decisión AD,
  (b) pase de estructura pre-merge de tareas riesgo medio/alto (las bajas las pasás vos con el
      checklist de v3 §3),
  (c) cada checkpoint (v3 §4.1),
  (d) BLOCKED de diseño o audit CHANGES con hallazgo de arquitectura.
  Para TODO lo demás no lo molestás: es el recurso más caro del sistema.
- Cupo: codex solo con mi OK; cada consulta al arquitecto anunciámela en una línea ("consulto al
  arquitecto por X") para que yo vea el gasto.
- Routing de workers: por CLI según v2 §4/§9 y la chuleta de v3 §0.bis — implementación vía
  opencode (namespace opencode-go/, NUNCA opencode/ que es Zen), tareas simples y auditoría
  continua vía agy (string EXACTO de `agy models`, auditor SIN --dangerously-skip-permissions),
  cierre adversarial vía codex. VETADOS: Qwen 3.7 Max, GLM 5.2, Gemini Flash (Low), y lógica
  sofisticada en cualquier Flash.

Arrancá por el checklist v2 §1. La PRIMERA consulta al arquitecto es obligatoria: pedile el mapa
inicial de ARCHITECTURE.md + invariantes + revisión de tu borrador de plan T1..Tn. Presentame el
resultado y esperá mi OK.

Mi objetivo: construir HIPnosis — el pipeline agéntico que porta repos CUDA a ROCm/HIP, los
compila/testea/verifica numéricamente en una MI300X real y entrega branch/PR + certificado —
para el AMD Developer Hackathon ACT II, con submission contenedorizada y ejecutable (perfil
replay de compose para los jueces). Deadline DURO: 11 de julio de 2026, 12:00 (Chile); hoy es
8 de julio — quedan ~3 días, así que el plan debe comprimir hitos sin saltarse lo bloqueante.

La fuente de verdad de implementación es hipnosis-blueprint.md (CLAUDE.md es su resumen; ante
cualquier conflicto entre documentos gana el blueprint). ANTES de borradorear el plan T1..Tn,
leé CLAUDE.md entero y del blueprint como mínimo: §0 (principios), §2 (estructura de repo
obligatoria), §11 (catálogo de puntos de falla), §12 (hitos) y §13 (reglas para ejecutores).
El plan debe mapear a los hitos de §12: M0 smoke test del droplet (BLOQUEANTE para código que
toque GPU; en paralelo legítimo: esqueleto del repo + schemas.py + trace.py + oracle mock),
M1 harness, M2 loop, M3 verify + certificado, M4 producto, M5 submission. Si el droplet MI300X
no está accesible desde esta máquina, M0 queda como tarea del humano y TODO lo demás avanza en
modo mock (§9, §13.2) — el modo mock se construye el día 1 junto al real, no después.

Reglas duras que cada brief debe propagar inline a los workers (además de los INV que defina el
arquitecto): hipify-perl NUNCA hipify-clang; parches solo en bloques SEARCH/REPLACE con
validación de unicidad; los números de reportes salen solo de código, jamás del LLM; prompts
solo en prompts.py y umbrales solo en config.py; tests con fixtures reales antes de integrar
cada pieza al loop; la lista NO-HACER de §13 completa. Toda desviación del blueprint se anota
en DEVIATIONS.md (una línea) ANTES de implementarla. El repo aún no tiene git init: hacelo en
el checklist inicial (la submission exige repo público de GitHub con README). Los commits del
producto son convencionales y frecuentes; los del workspace objetivo los hace solo el pipeline.
```
