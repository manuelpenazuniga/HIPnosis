# Orchestration Workflow v2 — playbook ejecutable para el agente orquestador

> **Quién ejecuta esto:** vos, el agente de la sesión principal (Claude Code, Codex u otro modelo
> capaz) actuando de **orquestador** de agentes CLI (opencode / agy / codex).
> **Cuándo:** mientras el foreman formal de ai-dev-workflow no está implementado
> (ver `docs/ESTRATEGIA-FOREMAN.md`, Fases 3–9). Este doc es el puente: la misma disciplina,
> ejecutada por vos a mano. Cuando exista `orchestrate.sh` + skill foreman en el repo donde trabajás,
> **preferí conducir eso** en vez de orquestar CLIs directo.
> **Cómo usarlo:** seguí los checklists en orden. Las reglas marcadas ⛔ son DURAS (violarlas costó
> tiempo o dinero real). Los bloques de código son copy-paste (ajustá rutas absolutas).
> La v1 (`orchestration-workflow.md`) queda como registro original del proyecto Ohu; esta v2 la
> generaliza e incorpora lo aprendido en ai-dev-workflow.

---

## 0. Las siete leyes (roles + economía)

1. **Vos diseñás, brifeás, auditás e integrás; los agentes implementan.** NO delegás: el diseño, la
   decisión de merge, y la auditoría de lo que toca fondos/seguridad. Excepción: si un agente se atasca
   en internals sutiles, resolvelo vos — "los agentes implementan" cede ante "no quedarse bloqueado".
2. **Tu token es el caro: gastalo en decisiones, no en plomería.** Correr tests, parsear salidas,
   contar archivos, reintentar — todo eso se hace con comandos bash, no "pensándolo". Si estás por
   leer un archivo grande para algo mecánico, pará: `grep`/`tail`/`wc` primero.
3. **Cada llamada a un LLM debe recibir solo lo que no sabe y producir solo lo que el sistema no
   sabe.** Contexto acotado por tarea (el bloque de SU tarea, no el plan entero); logs destilados
   (errores únicos, no 500 líneas repetidas); **nunca re-auditar un diff que no cambió** desde el
   último PASA.
4. **Los loops de fallo son el costo dominante: acortalos.** Verificación ejecutable ($0, un comando)
   ANTES de auditoría (LLM). Un fix-loop corto con el MISMO agente antes de escalar de modelo.
5. **Enforcement > prompts.** Read-only por capacidad (flags del CLI), verificación por `git diff`,
   nunca por confianza en el claim del agente. Un agente que dice "hecho, tests verdes" no probó nada.
6. **El barato no debe crear trabajo para el caro.** Modelo según dureza de la tarea; los checks
   deterministas (gate/lint/tests) atrapan lo mecánico gratis antes de que lo vea un auditor.
7. **El estado real es el repo, no tu narrativa.** Ante cualquier duda o reinicio de entorno:
   `git log`, `git status`, `git worktree list`, `ps` — re-orientate de ahí, no de tu memoria.

---

## 1. Checklist de inicio de sesión

```bash
git log --oneline -10          # ¿dónde quedó el trabajo real?
git status --porcelain         # ¿hay trabajo sin commitear? (de un agente muerto, quizás)
git worktree list              # ¿worktrees huérfanos de tareas previas?
cat ESTADO.md 2>/dev/null      # o PROGRESS.md / .agents/PROGRESS.md — el log de avance
ps aux | grep -E 'opencode|agy|codex' | grep -v grep   # ¿agentes vivos de una sesión anterior?
```

- Si hay trabajo sin commitear de un agente: revisalo y **commitealo vos** (un kill del entorno lo pierde).
- Si hay un worktree huérfano con trabajo: decidí merge o descarte ANTES de lanzar nada nuevo.
- ⛔ No arranques tareas nuevas sin este checklist: duplicar trabajo a medias es el desperdicio más caro.

---

## 2. El ciclo por tarea (imperativo, en orden)

### 2.1 Diseñar y brifear (lo hacés VOS)
1. Leé el spec y el código relevante. **Diseñá vos la solución** (máquina de estados, firmas,
   invariantes) para que el brief sea inequívoco. No dejes que el agente improvise lo económico/crítico.
2. Escribí el brief con la plantilla de §6. Guardalo en un archivo (`/tmp/brief-<tarea>.txt` o
   `.agents/brief-<tarea>.md`).

### 2.2 Aislar
```bash
git worktree add ../<repo>-t<N> -b spike/t<N>-<slug> main    # un worktree POR tarea
```

### 2.3 Lanzar (en background, SIEMPRE con log)
```bash
MSG="$(cat /tmp/brief-t<N>.txt)"
# elegí CLI+modelo con la tabla de §4; ejemplo worker opencode:
opencode run --dir ../<repo>-t<N> -m opencode-go/<modelo> "$MSG" > /tmp/t<N>.log 2>&1 &
```
Lanzá el watchdog de §7 en el mismo momento.

### 2.4 Verificar (NUNCA confiar en el claim)
Cuando el agente termina, corré VOS en el worktree:
```bash
git -C ../<repo>-t<N> log --oneline -3     # ¿commiteó? (a veces trabajan y NO commitean)
git -C ../<repo>-t<N> status --porcelain   # ¿dejó trabajo suelto? commitealo vos
./check.sh          # o el gate del stack: build + typecheck + lint + unit
git diff main...spike/t<N>-<slug> --stat   # ¿el diff toca SOLO lo declarado en el brief?
```
- Gate rojo → **un** reintento con el MISMO agente y sesión (§5.3), pasándole el log destilado (§5.2).
  Sigue rojo → escalá un peldaño de modelo (§4). Sigue rojo → BLOCKED, re-diseñás vos.
- Diff fuera del alcance declarado → no abortes: **anotalo para el auditor** ("examiná con atención
  X, Y: no estaban declarados").
- Si el brief incluía comando de verificación de aceptación, correlo AHORA (es gratis):
  falla → devolvele al worker el output, no gastes auditoría todavía.

### 2.5 Auditar (nivel según riesgo — §5.1)
Auditores en **paralelo** (background) si son más de uno. Nunca merge con un NO-PASA abierto.

### 2.6 Integrar y registrar
```bash
git merge --ff-only spike/t<N>-<slug> && git worktree remove ../<repo>-t<N> && git branch -d spike/t<N>-<slug>
```
Actualizá el log de avance (UNA línea por evento, formato §8) y el estado. Commit + push.

---

## 3. Mapa de decisión rápido (situación → acción)

| Situación | Acción |
|---|---|
| Tarea terminada, gate verde | Verificación ejecutable si la hay → auditoría según riesgo |
| Gate rojo, 1ª vez | MISMO agente, MISMA sesión (`--continue`/resume), log destilado |
| Gate rojo, 2ª vez | Escalá un peldaño de modelo (§4), sesión FRESCA (ojos nuevos) |
| Gate rojo, 3ª vez | BLOCKED — re-diseñás vos; el problema es el brief o el diseño, no el modelo |
| Audit CHANGES | Ronda de fix (volvé a 2.1 con los hallazgos). ⛔ NO mergear "con observaciones" |
| Diff idéntico ya aprobado antes | NO re-audites: mismo input → mismo veredicto. Anotá "memoizado" |
| Cupo agotado (rate limit/429/quota) | Checkpoint: commiteá TODO + anotá estado → failover a otro pool si la tarea lo permite (§4), o programá reanudar. ⛔ Nunca busy-wait |
| Agente colgado (§7) | `kill <pid>` → verificar/commitear parcial → relanzar (1 vez) → si repite, cambiar de pool |
| Worker BLOCKED \| ENV: ... | Arreglá el entorno VOS o con un chore barato; no gastes modelo caro |
| Worker BLOCKED \| SPEC: ... | Decisión tuya (o del humano): el plan era ambiguo |
| Worker BLOCKED \| DEPS: ... | Reordená tareas; la dependencia va primero |
| Duda de producto (no técnica) | Al humano SIEMPRE. No la resuelvas vos ni un modelo |

---

## 4. Routing de modelos (actualizado 2026-07) y escalada

| Tarea | Modelo / CLI | Nota |
|---|---|---|
| Implementación pesada (lógica difícil, fondos) | **DeepSeek V4 Pro** vía opencode | Techo del pool barato, no default |
| Default capaz / multi-paso | **MiniMax M3** vía opencode | Mejor throughput-capaz durante la promo |
| Infra / scripts / deploy | **MiniMax M3** o **Gemini 3.5 Flash (High)** | Terminal-heavy, acotado |
| Tareas simples / docs / smoke | **Gemini 3.5 Flash (Medium\|High)** vía agy | ⛔ NUNCA Flash (Low) para nada real |
| Frontend / UI | **Qwen3.7 Plus** vía opencode | Opt-in, no default |
| Runs largos autónomos | **Kimi K2.6** vía opencode | |
| **Auditor continuo** (per-task, lotes) | **Gemini 3.2 Pro (High)** vía agy | Plan generoso — es el auditor de volumen. String EXACTO de `agy models` |
| **Auditor adversarial de cierre** / toca fondos | **GPT-5.5** vía codex | Cupo escaso y fluctuante: ⛔ preguntá al usuario antes de gastarlo |
| Diseño, brief, merge, auditoría crítica | **VOS** | No se delega |

- **Escalada de gate-fix:** mismo modelo (misma sesión) → mismo modelo (sesión fresca) → un peldaño
  arriba (p.ej. M3 → V4 Pro) → BLOCKED. Nunca saltes directo al techo.
- ⛔ **Retirados por quemar cuota** (verificado: una cuenta en 1 día): Qwen 3.7 Max, GLM 5.2.
- **Diversidad de cupos = tu failover:** Go (opencode) y agy (Gemini) son pools independientes.
  Ventana de Go cerrada ≠ parar: chores y fixes simples pueden seguir por agy Flash High.

---

## 5. Disciplina de auditoría

### 5.1 Nivel según riesgo (la tabla que decide cuánto pagás)

| Cambio | Panel |
|---|---|
| Trivial (docs, rename, config menor) | Tu propia lectura + gate. Sin auditor externo |
| Riesgo bajo | **Lote**: acumulá 3–5 tareas bajas y UNA auditoría Gemini del diff acumulado |
| Riesgo medio | Gemini 3.2 Pro (High), inmediata |
| Riesgo alto / toca fondos / seguridad | **Panel**: vos + Gemini + GPT-5.5 (lentes distintas) |
| Cierre antes de merge a main / deploy | **Pase holístico** del diff COMPLETO con una familia DISTINTA a la que auditó continuo (normalmente GPT-5.5) |

**Por qué el panel no es redundante (evidencia real de Ohu):** cada familia caza una clase distinta
de bug — Claude = conservación/estructura; GPT = adversarial/teoría de juegos ("¿quién GANA dinero
rompiendo esto?"); Gemini = correctness/algebraico. Dos veces un pase holístico de GPT halló drenajes
que 120–176 tests verdes + auditorías por-tarea limpias no vieron. **"Compila y conserva" ≠ "no se
puede saquear".** ⛔ Nunca saltees el pase adversarial antes de tocar dinero real.

### 5.2 Regla de memoización (gratis, aplicala siempre)
Antes de re-auditar, preguntate: **¿cambió el diff o el plan desde el último PASA?**
`git diff <base>..HEAD | shasum` — si el hash es el mismo que ya aprobó un auditor, NO llames de
nuevo: registrá "audit memoizado (diff idéntico al aprobado)". Caso típico: auditaste un lote y el
"cierre" auditaría el mismo acumulado.

### 5.3 Sesiones: reusar vs fresca
- **Reintento del MISMO agente sobre el MISMO problema** (gate-fix, verificación fallida): CONTINUÁ
  la sesión (`opencode run --continue` / `codex exec resume --last` / `agy -c`). Triple ganancia: no
  re-lee el repo, el prefijo cachea, y recuerda qué ya intentó.
- **Escalada de modelo o re-audit tras fixes:** sesión FRESCA. Los ojos nuevos son el punto; un agente
  confundido no debe contaminar al de arriba.

### 5.4 Higiene de cache (suscripción también la paga)
- **Prompts-puntero:** pasá RUTAS (`lee .agents/AUDIT_SCOPE.md`), no contenido inline. El material
  volátil entra por tool-calls, tarde; el prefijo estable cachea.
- Nada de timestamps/contadores al INICIO de un prompt. Los docs de rol byte-estables.
- Agrupá llamadas relacionadas en el tiempo (TTL de cache: ~5 min Anthropic/OpenAI, horas DeepSeek).

---

## 6. Plantillas de brief

### 6.1 Brief de WORKER (implementación)
```
Trabajás en el worktree <ruta> (rama spike/t<N>-<slug>). Implementá SOLO esta tarea:

--- TAREA ---
<qué, con archivos EXACTOS a tocar (≤3), y el diseño YA DECIDIDO: firmas, estados, invariantes inline>
--- FIN TAREA ---

Criterios de aceptación (al pie de la letra):
1. <verificable>  2. <incluí tests NEGATIVOS: qué NO debe pasar>

Reglas:
- NO inventes APIs: abrí y leé las firmas reales. Si dudás, dejá `// TODO(audit): verificar contra <doc>`
  y seguí — un hueco marcado vale más que una API inventada.
- NO toques: <archivos/planos prohibidos>. NO agregues features/deps que la tarea no pide.
- Al terminar: corré <gate/tests>, dejá verde, y HACÉ COMMIT.
- SERÁS AUDITADO contra esta tarea y el diff: lo fuera de alcance se reporta.
- Si te bloqueás NO adivines: registrá 'BLOCKED | ENV|SPEC|DEPS: <motivo>' y pará.
- Respuesta final CORTA: qué cambiaste, supuestos, y el estado del gate. Sin ensayos.
```

### 6.2 Brief de AUDITORÍA (read-only)
```
Revisá MI código pre-merge por bugs de correctness/conservación contra la tarea. NO modifiques nada:
solo LEÉ y REPORTÁ.   ← (framing exacto: Gemini rechaza "security audit/pentest")

Alcance: el diff <base>..<head> del worktree, contra estos criterios:
--- TAREA(S) AUDITADA(S) ---
<bloque(s) de tarea con sus criterios de aceptación>
--- FIN ---

Verificá punto por punto: 1) correctitud vs criterios  2) bugs y casos borde  3) <invariantes del
proyecto>  4) calidad  5) cobertura real. Atención especial a: <archivos fuera de alcance declarado,
si los hubo>.

Formato de salida OBLIGATORIO:
- PRIMERA línea: exactamente `VERDICT: APPROVED` o `VERDICT: CHANGES`
- Por hallazgo: severidad (Crítico/Mayor/Menor) + archivo:línea + fix sugerido en una frase
- ÚLTIMA línea: exactamente `END_AUDIT`
```
**Parseo fail-closed:** si falta cualquiera de las dos sentinelas o la salida vino truncada,
tratá el resultado como **CHANGES** (nunca como APPROVED "porque parecía que iba bien").

---

## 7. Watchdog (colgado ≠ trabajando)

Un agente colgado espera al backend con **CPU ~0**; uno productivo acumula CPU. Verificado: 31–41 min
perdidos por no mirarlo.

```bash
# al lanzar el agente (PID=$!), lanzá también:
( sleep 540; echo "== watchdog t<N> =="; ps -o pid,etime,time,%cpu -p <PID>; \
  git -C ../<repo>-t<N> log --oneline -3 ) > /tmp/watchdog-t<N>.log 2>&1 &
```
A los ~9 min leé el log: **etime alto + time (CPU) en segundos + %cpu≈0 = COLGADO** →
`kill <PID>`, commiteá el parcial si existe, relanzá UNA vez. Si repite: cambiá de pool/modelo.

Más reglas de verificación dura:
- ⛔ Nunca confíes en "exit 0" de una instalación: `which <bin> && <bin> --version`.
- ⛔ El shell puede ser zsh: `${!var}` y otros bash-ismos fallan — usá formas portables o `bash -c`.
- Paths con espacios: citá SIEMPRE (`"$RUTA"`), también dentro de `.env`.
- ⛔ Secretos NUNCA en archivos del repo (ni .env.sample, ni configs versionadas): credential store
  nativo del CLI o env vars.

---

## 8. Contratos de estado (para que cualquier agente/sesión retome)

- **Log de avance** (`ESTADO.md` / `PROGRESS.md`): UNA línea por evento, append-only, la última línea
  de una tarea define su estado:
  ```
  T<n>: DONE | gate: green
  T<n>: BLOCKED | ENV: falta wasm-opt        # taxonomía: ENV (entorno) | SPEC (plan ambiguo) | DEPS (dependencia)
  T<n>: AUDITED | gemini: APPROVED
  T<n>: MERGED | <sha>
  ```
- **IDs estables:** un `T<n>` emitido NO se renumera ni reutiliza; el trabajo nuevo (fixes de
  auditoría) usa IDs nuevos. Tarea cancelada se marca, no se borra.
- **Veredictos con sentinelas** (primera y última línea exactas) — es lo que te permite parsear con
  `head -1`/`tail -1` sin releer todo.
- Al final de cada tarea: actualizá el log + estado ANTES de empezar la siguiente. Es lo que te salva
  cuando el entorno se reinicia (ley 7).

---

## 9. Contratos de invocación por CLI (verificados; si difieren de `--help`, gana el binario)

### opencode (workers pesados)
```bash
MSG="$(cat brief.txt)"
opencode run --dir <worktree> -m opencode-go/<modelo> "$MSG"
```
⛔ Namespace `opencode-go/<id>` (Go); `opencode/<id>` es Zen — NO usar. Prompt INLINE (no `-f`, es
array-greedy). Continuar sesión: `--continue`.

### agy (auditor Gemini + workers simples)
```bash
# AUDITOR (read-only POR CAPACIDAD: sin --dangerously-skip-permissions los writes se auto-rechazan)
agy --model "Gemini 3.2 Pro (High)" --add-dir <ruta ABSOLUTA a fuentes> --print-timeout 900s -p "$MSG"
# WORKER: agregá --dangerously-skip-permissions (si no, en print mode "no hace nada")
```
⛔ String de modelo EXACTO de `agy models` (con paréntesis y mayúsculas; los nombres cambian con
updates). ⛔ `--print-timeout 900s` (el default 5m trunca audits). ⛔ `--add-dir` ACOTADO a fuentes
(un dir con `target/`/`node_modules/` lo cuelga indexando). Sin equivalente de `-o`: parseá por
sentinelas desde la última línea `VERDICT:`.

### codex (auditor GPT-5.5)
```bash
codex exec -s read-only -m gpt-5.5 --skip-git-repo-check -o /tmp/audit-out.md "$MSG"
```
`-s read-only` = read-only por capacidad. `-o` aísla el mensaje final (parser determinista).
⛔ Cuota fluctúa: preguntá al usuario antes de gastar. Gotcha conocido: en algunos entornos el prompt
como argumento se queda esperando stdin — si cuelga sin consumir cupo, probá `< brief.txt` por stdin.
Continuar sesión: `codex exec resume --last`.

---

## 10. Tabla de síntomas (diagnóstico rápido)

| Síntoma | Causa | Fix |
|---|---|---|
| agy ignora el modelo / "unknown model" | string inexacto | copiá EXACTO de `agy models` |
| Respuesta cortada ~5 min | `--print-timeout` default | `900s` o más |
| agy colgado, 0 CPU | `--add-dir` enorme o backend | acotá a fuentes; kill + retry |
| Worker "no hizo nada", solo describió | faltó `--dangerously-skip-permissions` (print mode) | agregalo (SOLO worker) |
| codex espera para siempre | prompt como arg en entorno con stdin raro | brief por stdin `< brief.txt` |
| Agente dice DONE, gate rojo | claim sin verificar | ley 5: el gate decide, no el claim |
| Trabajo hecho pero "desaparece" | agente no commiteó y el entorno murió | 2.4: verificá y commiteá VOS |
| Auditor Gemini se niega a auditar | framing "security/pentest" | "revisá MI código pre-merge por correctness" |
| Cupo quemado en horas | modelo caro en loop mecánico | leyes 2 y 6; revisá routing §4 |
| Dos sesiones pisándose | sin worktree por tarea | 2.2: un worktree POR tarea |

---

## 11. Definición de "listo para merge" (gate final)

1. Gate/tests verdes corridos por VOS (no por el claim del agente).
2. Verificación ejecutable de aceptación (si existe) en verde.
3. Auditoría del nivel correcto (§5.1) en APPROVED — sin hallazgos Críticos/Mayores abiertos.
4. Diff revisado contra el alcance declarado (drift anotado y auditado si lo hubo).
5. Si toca fondos/deploy: pase holístico adversarial de familia distinta, APPROVED.
6. Log de avance actualizado; worktree y rama limpiados tras el merge.

---

## 12. Resumen en una frase

*Diseñá vos, que implementen los baratos en worktrees aislados, verificá con comandos (nunca claims),
auditá con un panel de lentes distintas proporcional al riesgo — Gemini para el volumen, GPT para el
cierre adversarial — gastá tus tokens caros solo en decisiones, y dejá el estado en el repo para que
cualquier sesión pueda retomar.*
