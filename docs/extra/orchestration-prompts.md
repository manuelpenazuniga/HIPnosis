# Prompts de inicio — workflows v2 y v3 (guía de uso)

> **Qué es este archivo:** la llave de arranque de los workflows. Los playbooks completos viven en
> `orchestration-workflow-v2.md` (orquestador puro) y `orchestration-workflow-v3.md` (arquitecto
> activo); acá están los **prompts listos para pegar** y las instrucciones exactas para usarlos:
> cuándo usar cada uno, qué preparar antes, qué va a pasar después, y cómo ajustar modelo y esfuerzo.
> Reemplazá siempre `<OBJETIVO>` por tu objetivo real, en una o dos frases concretas.

---

## 0. Arranque rápido — la ruta recomendada (v3 dividido: orquestador barato + arquitecto Fable)

Si no querés leer más, esta es la receta completa:

```bash
# PASO 1 (una sola vez): verificá que tu plan permite Fable en headless
claude -p --model claude-fable-5 --effort low "Respondé solo: OK"
#   → si imprime OK, listo. Si falla, probá: claude -p --model fable --effort low "Respondé solo: OK"

# PASO 2: abrí la sesión del ORQUESTADOR (modelo barato, esfuerzo medio)
cd /ruta/a/tu/proyecto
claude --model sonnet --effort medium

# PASO 3: pegá el prompt de la sección §4 de este archivo, con tu objetivo al final.
```

Qué va a pasar: la sesión Sonnet lee los dos playbooks, corre el checklist de estado del repo,
hace su **primera consulta obligatoria al arquitecto** (Fable diseña el mapa de arquitectura,
invariantes y revisa el plan de tareas), te presenta todo, y espera tu OK antes de tocar nada.
Desde ahí, Sonnet orquesta (lanza workers, verifica, mergea) y consulta a Fable solo en 4 casos
definidos. Vos aprobás el plan y decidís en los puntos que el workflow te trae.

---

## 1. ¿Qué versión uso? (decidí esto primero)

| Tu situación | Usá | Sección |
|---|---|---|
| Proyecto corto/simple, pocas tareas, sin diseño delicado | **v2** — orquestador puro | §2 |
| Proyecto con arquitectura real (módulos, invariantes, varias fases) y no te preocupa gastar modelo premium todo el día | **v3** — un solo modelo con los 3 sombreros | §3 |
| Ídem anterior, pero querés cuidar el cupo premium (recomendado por defecto) | **v3 dividido** — Sonnet orquesta, Fable decide | §4 |
| Ya hay trabajo empezado de una sesión anterior | **Reanudación** | §5 |
| El repo ya tiene ai-dev-workflow instalado (`orchestrate.sh`) | Conducí el orquestador formal — manda `docs/ESTRATEGIA-FOREMAN.md` | — |

Regla simple: **si el proyecto tiene decisiones que vas a lamentar en un mes, necesitás v3** (en
cualquiera de sus dos formas). v2 ejecuta bien un plan; v3 además se da cuenta a tiempo si el plan
es el equivocado.

---

## 2. Inicio v2 — Orquestador puro

**Cuándo:** proyecto acotado, tareas claras, sin arquitectura delicada.
**Modelo de la sesión:** cualquiera capaz (Sonnet alcanza y sobra; Opus si el proyecto lo amerita).
**Antes de pegar:** estar en la raíz del repo (`git init` si hace falta); tener instalados los CLI
workers que vayas a usar (`opencode`, `agy`, `codex`).

**Lanzá la sesión así:** `claude --model sonnet --effort medium`

**El prompt (pegalo como primer mensaje):**

```
Lee ENTERO ai-dev-workflow/docs/extra/orchestration-workflow-v2.md y actuá como el agente
orquestador que describe. Resumen de tu rol (el doc manda si algo difiere):

- Vos diseñás, brifeás, verificás e integrás; los agentes CLI (opencode/agy/codex) implementan.
- Tu token es el caro: lo mecánico se hace con bash, no "pensándolo". Nunca confíes en el claim
  de un agente: gate + git deciden.
- Auditoría según riesgo (v2 §5.1): Gemini vía agy para el volumen; GPT-5.5 vía codex SOLO para
  el cierre adversarial y lo que toca fondos — y antes de gastar cupo de codex, preguntame.
- Workers en worktrees aislados, uno por tarea, lanzados en background con watchdog (v2 §7).
- Estado en el repo (líneas parseables, IDs estables): cualquier sesión debe poder retomar.

Arrancá AHORA por el checklist de inicio de sesión (v2 §1) y reportame qué encontraste antes de
lanzar nada. Después proponeme el plan de tareas (T1..Tn, con archivos, riesgo y modelo por tarea)
y esperá mi OK antes de ejecutar.

Mi objetivo: <OBJETIVO>
```

**Qué va a pasar después:** (1) te reporta el estado real del repo; (2) te propone el plan T1..Tn;
(3) con tu OK, entra al ciclo: worktree → brief → worker en background → verificación dura → 
auditoría según riesgo → merge → siguiente. **Tu rol:** aprobar el plan, responder cuando pida OK
para gastar codex, y decidir en los BLOCKED de tipo SPEC (ambigüedad de producto).

---

## 3. Inicio v3 — Arquitecto activo (un solo modelo premium)

**Cuándo:** proyecto con arquitectura real y presupuesto para que un modelo premium lleve los tres
sombreros (arquitecto + orquestador + auditor de estructura) toda la sesión.
**Modelo de la sesión:** Fable u Opus. **Lanzala así:** `claude --model claude-fable-5 --effort high`
(el esfuerzo alto acá SÍ se justifica: este modelo hace también el trabajo de juicio).

**El prompt:**

```
Lee ENTERO ai-dev-workflow/docs/extra/orchestration-workflow-v2.md (base operativa) y DESPUÉS
ai-dev-workflow/docs/extra/orchestration-workflow-v3.md (tu rol). Actuá como el Arquitecto activo
de v3, con sus tres sombreros:

1. ARQUITECTO: creá/mantené ARCHITECTURE.md (mapa de módulos, decisiones AD-<n> append-only,
   invariantes INV-<n>) y BITACORA.md (checkpoints CP-<n>). Si no existen, crealos ANTES de la
   primera tarea. Replanificá proactivo (v3 §5), no solo cuando algo falle.
2. ORQUESTADOR: el ciclo v2 completo (worktrees, briefs con AD/INV inline, watchdog, verificación
   dura, panel de auditoría externa según riesgo).
3. AUDITOR DE ESTRUCTURA: pase propio (v3 §3) antes de CADA merge, con veredicto registrado
   (ESTRUCTURA: OK|AJUSTE|RECHAZO). Tu pase NUNCA sustituye al panel externo en riesgo alto.

Checkpoints (v3 §4): cada 3 tareas mergeadas, al cerrar fase, tras 2 BLOCKED seguidos o hallazgo
Crítico — contestá las 6 preguntas por escrito en BITACORA.md y ejecutá lo que salga antes de
seguir. Máximo UNA mejora de proceso por checkpoint.

Economía (v3 §6): tu pase de estructura son minutos sobre diff-stat + archivos clave; delegá
lecturas masivas a Gemini; el cupo de codex se gasta solo con mi OK.

Routing y CLIs: los workers se llaman por CLI según v2 §4/§9 y la chuleta de v3 §0.bis —
implementación vía opencode (namespace opencode-go/, NUNCA opencode/ que es Zen), tareas simples y
auditoría continua vía agy (string de modelo EXACTO de `agy models`), cierre adversarial vía codex.
VETADOS: Qwen 3.7 Max, GLM 5.2, Gemini Flash (Low), y lógica sofisticada en cualquier Flash.

Arrancá por el checklist de inicio (v2 §1) + revisión/creación de ARCHITECTURE.md, y presentame:
(a) el mapa y las decisiones AD iniciales, (b) los invariantes que proponés, (c) el plan T1..Tn.
Esperá mi OK antes de ejecutar.

Mi objetivo: <OBJETIVO>
```

**Qué va a pasar después:** igual que v2 más: mantiene ARCHITECTURE.md/BITACORA.md, pasa su propia
auditoría de estructura antes de cada merge, y cada ~3 tareas se detiene a un checkpoint (te
conviene leer esas entradas CP-<n>: son el pulso del proyecto). **Costo a vigilar:** todo corre en
tu modelo premium; si ves en `/usage` que se dispara, migra al esquema dividido (§4).

---

## 4. Inicio v3 DIVIDIDO — dos cerebros (RECOMENDADO)

### 4.1 La idea, en 30 segundos

```
┌─────────────────────────────────────────────────────────────┐
│  SESIÓN ORQUESTADORA (Sonnet, --effort medium, todo el día) │
│  lanza workers · verifica · watchdog · mergea · lleva estado │
│            │ solo en 4 casos ▼            ▲ respuesta        │
│   .agents/ARCHITECT_INPUT.md      .agents/ARCHITECT_ANSWER.md│
│            ▼                              │                  │
│  CONSULTA HEADLESS (Fable, --effort high/xhigh, a demanda)  │
│  diseña · decide AD/INV · pase de estructura · checkpoints   │
└─────────────────────────────────────────────────────────────┘
   Memoria durable de AMBOS: ARCHITECTURE.md + BITACORA.md (en git)
```

El gasto premium queda proporcional a las **decisiones** (3–6 consultas por objetivo), no a los
pasos (docenas). El orquestador nunca "piensa profundo": cuando algo lo exige, esa es la señal de
consultar, no de rumiar.

### 4.2 Preparación (una sola vez)

```bash
claude -p --model claude-fable-5 --effort low "Respondé solo: OK"
```
Si falla: probá `--model fable`; si tampoco, tu plan no expone Fable en headless → usá
`--model opus` como arquitecto (el esquema funciona igual, con techo Opus).

### 4.3 El prompt (pegalo en la sesión del ORQUESTADOR, lanzada con `claude --model sonnet --effort medium`)

```
Lee ENTERO ai-dev-workflow/docs/extra/orchestration-workflow-v2.md y DESPUÉS
ai-dev-workflow/docs/extra/orchestration-workflow-v3.md. Vas a ejecutar v3 en modo DOS CEREBROS:

- VOS (esta sesión) llevás el sombrero ORQUESTADOR: todo el ciclo v2 (worktrees, briefs, lanzar,
  watchdog, verificar, panel externo, merge, estado). Lo mecánico es 100% tuyo.
- El sombrero ARQUITECTO y el pase de ESTRUCTURA los ejerce un modelo superior por consulta
  headless. Protocolo de consulta (bus de archivos):
  1. Escribí el contexto MÍNIMO en .agents/ARCHITECT_INPUT.md: qué necesitás (diseño de tarea /
     pase de estructura / checkpoint), el bloque de tarea o el diff-stat + archivos clave, y las
     secciones relevantes de ARCHITECTURE.md (no el repo entero).
  2. Ejecutá (esfuerzo: diseño y pase de estructura = high; checkpoint = xhigh):
     claude -p --model claude-fable-5 --effort high "Sos el Arquitecto de v3 (lee
     ai-dev-workflow/docs/extra/orchestration-workflow-v3.md, secciones 1, 3 y 4). Lee
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

Mi objetivo: <OBJETIVO>
```

### 4.4 Qué va a pasar después, y cómo supervisás el gasto

1. Sonnet reporta el estado del repo, borradorea un plan, y hace la consulta inicial a Fable.
2. Te presenta: mapa de arquitectura + invariantes + plan revisado. **Aprobás vos.**
3. Ciclo normal v2, con las consultas anunciadas en una línea cada vez.
4. **Medí el costo por consulta una vez:** mirá `/usage`, dejá que haga una consulta, volvé a
   mirar. Ese delta × 3–6 consultas es el costo de arquitecto por objetivo. Si el orquestador
   consulta mucho más que eso, el problema es otro: los briefs necesitan más diseño inicial
   (decilo en el próximo checkpoint — pregunta 6).

**Variante con subagentes** (si preferís no usar headless): creá `.claude/agents/architect.md` con
`model: fable` (y opcionalmente `effort: high`) en el frontmatter y el rol de v3 §1/§3/§4 como
system prompt. La sesión Sonnet lo invoca como subagente en los mismos 4 casos, pasándole el mismo
ARCHITECT_INPUT. Ventaja: conserva contexto entre consultas dentro de la sesión. Contra: ese
contexto muere con la sesión — ARCHITECTURE.md/BITACORA.md siguen siendo la memoria durable.

---

## 5. Prompt de REANUDACIÓN (sirve para v2 y v3, cualquier variante)

**Cuándo:** hay trabajo empezado de una sesión anterior (propia o de otro modelo).

```
Lee ai-dev-workflow/docs/extra/orchestration-workflow-v2.md (y v3 si hay ARCHITECTURE.md en el
repo: entonces el modo es v3). Hay trabajo en curso: NO arranques nada nuevo todavía.

1. Corré el checklist de inicio (v2 §1): git log/status/worktrees, agentes vivos, log de avance.
2. Si es v3: leé BITACORA.md (los CP-<n> son el juicio heredado) y ARCHITECTURE.md.
3. Reportame: estado real, qué quedó a medias, y tu propuesta de próximo paso (UNA acción).
4. Con mi OK, retomá el ciclo donde corresponda (una tarea a medias se termina o se descarta
   explícitamente antes de abrir otra).
```

---

## 6. Ajuste de esfuerzo por rol — el flag `--effort`, explicado

El CLI acepta `--effort <low|medium|high|xhigh|max>` tanto al **lanzar una sesión** (fija el
esfuerzo de toda la jornada) como en **cada `claude -p`** (fija el de esa consulta). Es un eje
independiente del modelo: definís *qué cerebro* con `--model` y *cuánto piensa* con `--effort`.

**La regla que gobierna todo: esfuerzo alto SOLO donde hay pocas llamadas.**
El esfuerzo del orquestador se multiplica por cada paso del loop (docenas por objetivo); el del
arquitecto, solo por sus 3–6 consultas. Por eso el orquestador va en `medium` aunque el instinto
pida más: su esfuerzo bajo es parte del diseño (si necesita pensar profundo → consulta), no una
concesión de presupuesto.

| Rol / momento | Comando | Por qué |
|---|---|---|
| Orquestador, toda la jornada | `claude --model sonnet --effort medium` (`low` si el proyecto es rutinario) | Su trabajo es mecánico-disciplinado; lo profundo se escala |
| Arquitecto — diseño de tarea / decisión AD | `claude -p --model claude-fable-5 --effort high ...` | Juicio real, pocas veces |
| Arquitecto — pase de estructura | `--effort high` | Checklist + razonar invariantes |
| Arquitecto — checkpoint (6 preguntas) | `--effort xhigh` | EL momento de juicio del proyecto; hay 2–4 por objetivo: pagalo |
| Arquitecto — algo mecánico | — | No debería llegarle nunca |
| Subagente architect (§4 variante) | `effort: high` en el frontmatter | Junto a `model: fable` |

**Los otros dos diales que pesan tanto como el flag:**
- **El tamaño de `ARCHITECT_INPUT.md`**: el costo real de una consulta es el contexto que le das.
  Bloque de tarea + diff-stat + secciones relevantes de ARCHITECTURE.md — nunca el repo.
- **"Respondé SOLO lo pedido / Sé conciso"** en el prompt: acota la salida (que también paga).

**Bonus nocturno:** `--fallback-model <modelos>` (solo con `--print`) hace que una consulta
headless degrade automáticamente a otro modelo si el principal está saturado, en vez de caerse —
útil para el arquitecto en runs desatendidos.

**Dónde mirás el consumo:** `/usage` dentro de la sesión (ventana de 5h + tope semanal del plan);
`npx ccusage` para el desglose local por modelo/día. Hoy `claude -p` comparte el pool de tu
suscripción (el split a crédito aparte quedó pausado en 2026-06; ver DEC-2 de ESTRATEGIA-FOREMAN.md).

---

## 7. Problemas comunes (síntoma → fix)

| Síntoma | Causa | Fix |
|---|---|---|
| `--model claude-fable-5` falla en headless | alias/entitlement del plan | probá `--model fable`; si no, `--model opus` como arquitecto (todo lo demás igual) |
| `--effort` no reconocido | CLI viejo | `claude update` y reintentá |
| El orquestador consulta al arquitecto "por las dudas" | briefs con poco diseño inicial | recordale los 4 casos taxativos; en el próximo checkpoint, mejora de proceso = "más diseño upfront en briefs" |
| El arquitecto responde ensayos larguísimos | falta el "Sé conciso" o effort de más | verificá el prompt de consulta; para pases de estructura usá `high`, no `xhigh` |
| Respuestas del arquitecto ignoran el contexto | ARCHITECT_INPUT.md muy grande o muy vago | contexto MÍNIMO pero completo: bloque de tarea + diff-stat + AD/INV relevantes |
| No sabés cuánto gastó la jornada | — | `/usage` en la sesión; `npx ccusage` para el histórico local |
| La sesión murió a mitad de una tarea | — | prompt de reanudación (§5): el estado vive en git + ARCHITECTURE/BITACORA, no en la sesión |
