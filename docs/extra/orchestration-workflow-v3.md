# Orchestration Workflow v3 — el Arquitecto activo

> **Qué cambia respecto de v2:** en v2 Claude es un *despachador disciplinado* (diseña el brief,
> lanza, verifica, delega la auditoría al panel, mergea). En v3 Claude ejerce de **ARQUITECTO**:
> custodia el diseño y sus invariantes, **audita él mismo la estructura** de cada cambio, y en
> **checkpoints periódicos se detiene a pensar** si el rumbo es correcto y qué se puede mejorar.
> **Base operativa:** TODO lo de v2 sigue vigente y NO se repite acá — contratos de CLI (v2 §9),
> watchdog (v2 §7), routing de modelos (v2 §4), tabla de síntomas (v2 §10), plantillas base (v2 §6).
> Este doc define solo el delta: el rol activo. Leé v2 PRIMERO, después esto.
> **Quién ejecuta esto:** un modelo capaz de juicio arquitectónico real (Fable/Opus). Si el
> presupuesto manda, ver la variante de dos cerebros en `orchestration-prompts.md` (orquestador
> barato + arquitecto premium a demanda).

---

## 0. Los tres sombreros (y cuándo llevás cada uno)

| Sombrero | Cuándo | Qué hacés |
|---|---|---|
| **ARQUITECTO** | Al iniciar, al brifear cada tarea, en cada checkpoint, ante cada hallazgo de diseño | Custodiás `ARCHITECTURE.md` + invariantes; decidís trade-offs; replanificás PROACTIVAMENTE (no solo cuando algo explota) |
| **ORQUESTADOR** | Durante el ciclo por tarea | Todo v2 §2: aislar, lanzar, watchdog, verificar, integrar |
| **AUDITOR DE ESTRUCTURA** | Antes de CADA merge + notas previas a auditorías externas | Tu lente propia (conservación/estructura/contratos) — complementa al panel, NUNCA lo reemplaza en riesgo alto |

La ley 1 de v2 se enmienda así: *vos diseñás, brifeás, **auditás estructura**, integrás y
**reflexionás en checkpoints**; los agentes implementan; el panel externo audita con lentes que vos
no tenés.*

---

## 0.bis Chuleta operativa (resumen deliberadamente redundante de v2 — ante cualquier conflicto, v2 §4/§9 manda)

Esto se duplica acá a propósito: son las reglas que NO podés permitirte olvidar a mitad de sesión.

| Necesidad | CLI → modelo | Comando base |
|---|---|---|
| Implementación pesada (lógica difícil, fondos) | opencode → **DeepSeek V4 Pro** | `opencode run --dir <worktree> -m opencode-go/<modelo> "$MSG"` |
| Default capaz / multi-paso | opencode → **MiniMax M3** | ídem |
| Frontend / UI | opencode → **Qwen3.7 Plus** | ídem |
| Runs largos autónomos | opencode → **Kimi K2.6** | ídem |
| Tareas simples / docs / chores | agy → **Gemini 3.5 Flash (High\|Medium)** | `agy --model "<STRING EXACTO>" --add-dir <ruta ABS> --dangerously-skip-permissions --print-timeout 900s -p "$MSG"` |
| **Auditor continuo** (per-task, lotes) | agy → **Gemini 3.2 Pro (High)** | ídem pero **SIN** `--dangerously-skip-permissions` (read-only por capacidad) |
| **Auditor adversarial de cierre** / fondos | codex → **GPT-5.5** | `codex exec -s read-only -m gpt-5.5 --skip-git-repo-check -o <out.md> "$MSG"` — cupo escaso: **pedí OK al humano antes** |

**⛔ VETADOS (no negociable):**
- **Qwen 3.7 Max** y **GLM 5.2** — queman la cuota (verificado: una cuenta en 1 día).
- **Gemini 3.5 Flash (Low)** — no confiable para nada real.
- Namespace **`opencode/<id>` (Zen)** — usar SIEMPRE `opencode-go/<id>`.
- Lógica sofisticada en cualquier Flash — Flash es worker de tareas claras, no cerebro.

**⛔ Recordatorios que rompen runs:** strings de modelo de agy EXACTOS de `agy models` (con
paréntesis y mayúsculas); `--print-timeout 900s` en agy; prompt inline (no `-f`); `--add-dir`
acotado (un dir con `target/`/`node_modules/` cuelga a agy); a Gemini auditor NO le digas
"security audit" (rechaza) sino "revisá mi código pre-merge por correctness".

Detalles completos, watchdog, plantillas de brief y tabla de síntomas: **v2 §4, §5, §6, §7, §9, §10**.

---

## 1. Artefactos del arquitecto (crealos si no existen, mantenelos SIEMPRE)

### 1.1 `ARCHITECTURE.md` — el diseño vivo
```markdown
# Arquitectura — <proyecto>
## Mapa de módulos
<módulo> → <responsabilidad> → <depende de>       # la DIRECCIÓN de las dependencias es ley

## Decisiones (ADR-lite, append-only, NUNCA borrar — se supersede con una nueva)
AD-1 [2026-07-07] <decisión en una frase> — por qué: <...> — descartado: <alternativa y por qué>
AD-2 ...

## Invariantes (lo que NINGÚN cambio puede romper)
INV-1: <p.ej. "todo mote que entra sale o queda contabilizado: conservación">
INV-2: <p.ej. "capa API nunca importa de capa storage directamente">
```
- Cada tarea que fuerce una decisión nueva → agregás el `AD-<n>` ANTES de escribir el brief.
- Los `INV-<n>` aplicables van INLINE en cada brief (los workers no leen ARCHITECTURE.md entero).

### 1.2 `BITACORA.md` — el registro de reflexión (checkpoints)
```markdown
CP-1 [2026-07-07] tareas: T1-T3 | plan: OK | deuda: 2 TODO(audit) en auth | modelos: M3 rindió, Flash falló 1 gate | mejora: briefs ahora incluyen firma exacta | riesgo próximo: migración de esquema en T5
```
Una entrada por checkpoint, formato de UNA línea larga o bloque corto. Es lo que otra sesión (u otro
modelo) lee para heredar tu juicio, no solo tu estado.

---

## 2. El ciclo por tarea v3 (delta sobre v2 §2)

```
2.0  [ARQUITECTO] Pre-brief:
     - ¿La tarea encaja en ARCHITECTURE.md? ¿Fuerza una decisión nueva? → escribí el AD-<n> AHORA.
     - ¿Toca algún INV-<n>? → el brief lo declara explícito + el nivel de auditoría sube un escalón.
2.1-2.3  igual que v2 (diseñar brief con AD/INV inline, aislar en worktree, lanzar con watchdog).
2.4  igual que v2 (verificar: commit real, gate, alcance del diff) MÁS:
     [AUDITOR-ESTRUCTURA] mirada al diff-stat (2 min): si algo huele (archivo inesperado, tamaño
     desproporcionado), anotalo para el auditor externo: "atención especial a <X>".
2.5  Auditoría externa según riesgo (v2 §5.1) — tus notas de 2.4 van en el brief del auditor.
2.6  [AUDITOR-ESTRUCTURA] PASE DE ESTRUCTURA antes del merge (§3 de este doc). Veredicto propio.
2.7  Merge solo con: gate verde + panel externo APPROVED + tu ESTRUCTURA: OK.
2.8  ¿Tocan checkpoint? (§4) → hacelo ANTES de arrancar la siguiente tarea.
```

---

## 3. El pase de estructura (tu auditoría propia — checklist ejecutable)

Antes de CADA merge, con el diff delante (`git diff main...spike/tN --stat` + los archivos clave):

1. **Contratos:** ¿las firmas/interfaces nuevas respetan el mapa de módulos? ¿Alguna dependencia va
   en la dirección PROHIBIDA? (esto los auditores externos casi nunca lo ven: no conocen tu mapa)
2. **Invariantes:** por cada INV-<n> que el diff roza: razoná POR QUÉ se preserva. "Parece que sí"
   no es un porqué. Si no podés razonarlo, el veredicto es AJUSTE.
3. **Deuda:** ¿TODO(audit) nuevos? ¿duplicación? ¿un acoplamiento que vas a lamentar en 5 tareas?
   → no bloquees por esto, pero ANOTALO en BITACORA (es insumo del checkpoint).
4. **Casos borde del diseño:** el worker implementó el happy path del brief; ¿los estados de error
   que VOS diseñaste están? (los diseñaste vos: sos el único que sabe si faltan)
5. **Veredicto propio, registrado en el log de avance:**
   ```
   T<n>: ESTRUCTURA: OK | <1 línea>
   T<n>: ESTRUCTURA: AJUSTE | <qué> → tarea T<n+k> nueva
   T<n>: ESTRUCTURA: RECHAZO | <viola AD/INV-<n>> → NO merge, re-diseño
   ```

**Reglas duras del pase:**
- ⛔ **Presupuesto:** diff-stat + archivos clave, NO el repo entero. Si el diff es enorme, pedile a
  Gemini un resumen estructurado primero y auditá SOBRE el resumen + los 2-3 archivos críticos.
- ⛔ **Tu pase NUNCA reemplaza al panel en riesgo alto/fondos.** Evidencia (Ohu W2-3): GPT cazó un
  bug introducido por el PROPIO fix del arquitecto, que el arquitecto y Gemini dieron por PASA. Sos
  una lente más, con puntos ciegos sistemáticos sobre tu propio diseño.
- SÍ podés reemplazar a Gemini en: lotes de riesgo bajo (cuando el cupo de agy esté justo) y cambios
  de docs/config. Sos el techo de calidad ahí, y el gate ya cubrió lo mecánico.

---

## 4. Los checkpoints de reflexión (el corazón de v3)

### 4.1 Disparadores (el que llegue primero)
- Cada **3 tareas mergeadas** (ajustá N al tamaño del proyecto; 3 es el default).
- Al **cerrar una fase** / hito del plan.
- Tras **2 BLOCKED seguidos** (algo sistémico pasa).
- Tras cualquier hallazgo **Crítico** de un auditor externo.
- Antes de cualquier **deploy/release**.

### 4.2 El ritual (pensamiento propio: CERO llamadas externas, CERO re-lecturas masivas)
Contestá estas seis preguntas POR ESCRITO en BITACORA.md, con lo que ya tenés en contexto:

1. **Plan:** ¿las tareas restantes siguen siendo las correctas, en el orden correcto? ¿Algo de lo
   aprendido implementando invalida una decisión AD-<n>? → si sí, supersedéla AHORA (AD nuevo).
2. **Deuda:** ¿cuántos TODO(audit)/AJUSTE acumulados? ¿alguno pasó de "anotado" a "urgente"?
3. **Agentes/modelos:** ¿quién rindió y quién no en estas N tareas? ¿re-ruteo? (p.ej. "Flash falló
   2 gates de lógica → esas tareas van a M3"; "V4 Pro resolvió en 1 pasada lo que M3 no pudo en 3")
4. **Arquitectura:** ¿el código real está divergiendo del mapa? (drift silencioso = el bug de dentro
   de un mes)
5. **Riesgo próximo:** ¿cuál es la tarea más peligrosa de las siguientes 3? ¿su brief necesita más
   diseño tuyo ANTES de lanzarla?
6. **Proceso:** UNA sola mejora accionable a briefs/routing/gate — o explícitamente "ninguna".
   ⛔ Máximo UNA por checkpoint: el meta-trabajo infinito es un modo de fallo real.

### 4.3 Salida del checkpoint
- La entrada `CP-<n>` en BITACORA.md (formato §1.2).
- Las acciones que salgan (AD nuevo, tarea nueva, re-ruteo) se EJECUTAN antes de la siguiente tarea,
  no quedan "para después".
- Si la respuesta a la pregunta 1 fue "el plan está mal" → pará todo y replanificá. Un checkpoint
  que detecta rumbo equivocado a tiempo paga todos los checkpoints del proyecto.

---

## 5. Replanificación proactiva (arquitecto, no bombero)

En v2 replanificás cuando algo falla (audit CHANGES, BLOCKED). En v3, además:
- **Anticipá:** en cada checkpoint, la pregunta 5 te obliga a mirar 3 tareas adelante. Si la tarea
  peligrosa necesita un spike/prototipo antes, agregalo al plan HOY.
- **Consolidá:** si 2+ tareas de AJUSTE apuntan al mismo módulo, no las parchees por separado —
  diseñá UNA tarea de consolidación.
- **Podá:** tareas del plan que el aprendizaje volvió innecesarias → cancelalas explícitamente
  (marcá, no borres). Un plan con tareas zombis miente sobre el trabajo restante.

---

## 6. Economía del rol activo (tu atención es el recurso más caro del sistema)

El sombrero de arquitecto gasta TUS tokens (los premium). Reglas para que v3 no cueste más de lo que rinde:
1. El pase de estructura es **minutos, no una re-auditoría**: diff-stat + archivos clave + checklist.
   El panel externo ya hizo el trabajo de volumen.
2. El checkpoint usa **lo que ya está en tu contexto**. Si necesitás refrescar, leé BITACORA y el
   log de avance (líneas), no el código.
3. Delegá la LECTURA masiva: "Gemini, resumime la estructura de X en 20 líneas" es más barato que
   leerlo vos, y auditás sobre el resumen.
4. Si estás gastando >20% de tu esfuerzo en meta-trabajo (bitácora, checkpoints, re-diseño), N es
   muy chico o el proyecto es muy simple para v3 → bajá a v2.
5. La variante de dos cerebros (orquestador barato + vos solo como arquitecto a demanda) está en
   `orchestration-prompts.md` §3 — es v3 con el gasto premium acotado a los sombreros 1 y 3.

---

## 7. Definición de "listo para merge" v3 (reemplaza v2 §11)

1. Gate/tests verdes corridos por el orquestador (no por el claim del agente).
2. Verificación ejecutable de aceptación (si existe) en verde.
3. Panel externo del nivel correcto (v2 §5.1) en APPROVED.
4. **Pase de estructura propio: ESTRUCTURA: OK registrado.**
5. **Ningún INV-<n> sin su "por qué se preserva" razonado.**
6. Si toca fondos/deploy: pase holístico adversarial (GPT-5.5) APPROVED — tu OK NO lo sustituye.
7. Log de avance + BITACORA al día; checkpoint hecho si tocaba.

---

## 8. Resumen en una frase

*v3 = v2 + memoria de diseño (ARCHITECTURE.md), una lente de auditoría propia que el panel no tiene
(estructura/invariantes), y la disciplina de parar cada N tareas a preguntarse si el rumbo es el
correcto — porque el orquestador ejecuta bien un plan, pero solo el arquitecto se da cuenta a tiempo
de que el plan es el equivocado.*
