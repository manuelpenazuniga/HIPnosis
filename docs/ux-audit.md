# Auditoría UX/UI — Dashboard HIPnosis

**Fecha:** 2026-07-09 (2 días antes del deadline del hackathon)
**Alcance:** `dashboard/index.html` + `dashboard/app.js` + superficie API que consume (`app/api.py`)
**Método:** lectura línea a línea del código, smoke test en vivo (uvicorn `ORACLE_MODE=replay` + Chrome), y recorrido de los 3 journeys reales: juez (replay), usuario con GPU (real), presentador (video demo).
**Estado de partida:** dashboard "wow" ya mergeado (hero + wave64 + diff + certificado). Esta auditoría busca lo que falta en **simplicidad, claridad del proceso y robustez de la experiencia**, no rehacer el diseño visual (que está bien logrado).

---

## Resumen ejecutivo

El dashboard comunica muy bien el **resultado** (burndown, verdict gigante, certificado) pero comunica débil el **proceso** (qué está haciendo HIPnosis *ahora* y por qué), y tiene tres riesgos de robustez que pueden arruinar el demo en vivo: el fallback silencioso a datos demo ante cualquier error de red, la dependencia total de CDNs externos para el estilo, y la ausencia (ya corregida) de una forma de iniciar un run desde la UI.

Prioridades: **P0** = puede romper el demo o mentirle al usuario · **P1** = confunde o esconde el proceso · **P2** = usabilidad/robustez · **P3** = pulido.

| # | Hallazgo | Prioridad | Estado |
|---|----------|-----------|--------|
| 1 | Fallback silencioso a datos demo ante cualquier error de polling | P0 | **✅ corregido (Ola 1)** |
| 2 | Todo el estilo depende de CDNs (Tailwind, fonts) — sin internet, dashboard roto | P0 | **✅ corregido (Ola 1)** |
| 3 | Sin forma de iniciar un run desde la UI | P0 | **✅ corregido** |
| 4 | Sin selector/lista de runs (`GET /runs` existe y no se usa) | P1 | **✅ corregido (Ola 2)** |
| 5 | Fases tempranas mudas: QUEUED/CLONING sin feedback ni tiempo | P1 | **parcial (Ola 1)**: repo URL visible + 404 explícito; falta elapsed/microcopy por fase |
| 6 | Métrica "Errors Resolved" muestra errores *iniciales*, no resueltos | P1 | **✅ corregido (Ola 1)** |
| 7 | Costo API: precio hardcodeado en el front + badge "$0.00" fijo contradictorio | P1 | **✅ corregido (Ola 3)** |
| 8 | Jerga sin explicar: E01, W01, NO_ORACLE, tier, delta, "REPORTING phase" | P1 | **✅ corregido (Ola 2)** |
| 9 | FAILED no muestra causa; eventos `scan`/`run_meta` se descartan | P1 | **✅ corregido (Ola 2+3)**: paneles Why-failed/Needs-human + strip de scan |
| 10 | Sin indicador de modo (replay/mock/real) | P2 | **✅ corregido (Ola 1)** |
| 11 | Sin timestamps, duración por fase, ni indicador "live" | P2 | **✅ corregido (Ola 1+3)**: live/reconnecting + run time total; duración por fase queda como nice-to-have |
| 12 | Interpolación HTML sin escapar en tablas (contenido del repo objetivo) | P2 | **✅ corregido (Ola 2)** |
| 13 | Accesibilidad: severidad solo por color, sin `aria-live`, sin reduced-motion | P2 | **✅ corregido (Ola 2+3)**: `aria-live`, contraste (gray-600→500) y `prefers-reduced-motion` |
| 14 | Certificado colapsado por defecto siendo "the deliverable" + bug de toggle | P2 | **✅ corregido (Ola 3)**: bug de toggle + auto-expand al renderizar |
| 15 | highlight.js se carga y nunca se usa (peso muerto) | P3 | **✅ corregido (Ola 1)** |
| 16 | Sin favicon ni `<title>` dinámico con estado | P3 | **✅ corregido (Ola 3)** |

---

## Journeys y dónde se caen

### Journey A — El juez (replay, sin GPU)
`docker compose --profile replay up` → abre `:8080` → ve el run grabado.

- ✅ Funciona y el efecto "está pasando en vivo" es potente.
- ⚠️ **Nada le dice que es una reproducción** (hallazgo 10). Si lo descubre solo, se siente engañado; si se le dice con un badge elegante ("REPLAY — recorded MI300X run"), se vuelve honestidad que suma puntos.
- ⚠️ Si la sala no tiene internet, ve HTML sin estilo (hallazgo 2). Riesgo binario: o se ve perfecto o se ve roto.
- ⚠️ Si escribe una URL en el input nuevo en modo replay, el run queda `QUEUED` para siempre sin explicación (AD-4: replay no ejecuta pipeline). Ver hallazgo 5/10.

### Journey B — Usuario real (con MI300X)
Pega URL → mira el run → descarga certificado.

- ✅ Ahora puede iniciar el run desde la UI (input agregado en esta pasada).
- ⚠️ Entre el submit y el primer evento del trace ve "INITIALIZING" y tarjetas vacías, sin saber si funcionó (hallazgo 5). Verificado en browser: la página queda muda.
- ⚠️ Si el clone falla (URL con typo, repo privado), el run termina `FAILED` sin que la UI diga **por qué** (hallazgo 9).
- ⚠️ Si su WiFi parpadea a mitad del run, la UI cambia silenciosamente a los datos del demo de bsw — **le muestra un run que no es el suyo** (hallazgo 1). Es el peor bug de confianza del producto.

### Journey C — Presentador (video demo)
- ✅ El guion visual (hero → wave64 → diff → PASS gigante → certificado) es fuerte.
- ⚠️ El "qué está haciendo ahora" depende de que el presentador lo narre; la UI no lo cuenta sola (hallazgos 5, 8, 11).

---

## Hallazgos en detalle

### P0 — Pueden romper el demo o mentir

#### 1. Fallback silencioso a demo data ante cualquier error de polling
`app.js` — `pollEvents()` catch: **cualquier** fetch fallido (un timeout, un blip de red, el server reiniciándose) dispara `loadDemoData()`, que apaga el polling para siempre (`state.polling = false`) y **mezcla los fixtures de bsw sobre el estado del run real que se estaba viendo**. El usuario ve datos falsos sin ningún aviso, y aunque el server vuelva en 2 segundos, la UI jamás se reconecta.

**Recomendación:**
- Reintentar con backoff (p. ej. 1s → 2s → 5s, indefinido) mostrando un indicador "reconnecting…".
- El modo demo solo debe activarse si (a) nunca llegó ningún evento **y** (b) se pidió explícitamente (`?demo=1`) o se sirvió como archivo estático (protocolo `file:`).
- Nunca mezclar fixtures sobre un estado con eventos reales ya recibidos.

#### 2. Dependencia total de CDNs para el estilo
`index.html:7-12,27` — Tailwind se carga como **JIT de runtime desde CDN**, más Google Fonts, highlight.js y marked. Sin internet (sala de demo, juez en avión, firewall corporativo) la página renderiza **sin ningún estilo**: el "wow" se convierte en texto plano. Contradice el espíritu de F-15/F-16 (el perfil replay debe correr "en cualquier laptop").

**Recomendación:** vendorizar todo en `dashboard/vendor/`: generar el CSS de Tailwind una vez (CLI standalone, sin build step recurrente — el output es un `.css` estático que se commitea), fuentes `woff2` locales o caer a `ui-monospace`/system-ui, `marked.min.js` local. Bonus: elimina el flash de página sin estilo del primer load.

#### 3. ✅ (corregido en esta pasada) Sin entrada para iniciar un run
La UI era 100% espectador; crear un run requería `curl`. Se agregó el form "New port" en el header (POST `/runs` → redirect `?run=<id>`), visible desde el arranque, con estado de carga y error inline. Verificado en vivo: submit → `run_b414b28f` → dashboard del run nuevo.

---

### P1 — Esconden o confunden el proceso

#### 4. Sin selector de runs
`GET /runs` devuelve la lista completa (verificado por curl) y la UI no la usa; el único acceso a un run es saber su id y escribirlo en la URL. Con el input nuevo, un usuario que lanza 2 runs pierde el primero.

**Recomendación:** dropdown/lista compacta junto al badge de run ("Run: run_bsw01a2 ▾") poblada de `GET /runs`, con estado y repo de cada uno. Es también el fix natural para el default hardcodeado `run_bsw01a2` (`app.js:47`): si no hay `?run=`, mostrar el run más reciente o la lista.

#### 5. Fases tempranas mudas
Entre QUEUED y el primer `build` no hay nada que mirar: tarjetas con "—", badge estático. En el smoke test, tras crear un run la página queda en "INITIALIZING" indefinidamente (en replay, para siempre). El momento de mayor ansiedad del usuario ("¿funcionó?") es el de menor feedback.

**Recomendación:**
- Mostrar **la URL del repo del run actual** en el header (está en `GET /runs/{id}`, la UI nunca la pinta — el usuario ni siquiera puede confirmar QUÉ repo se está porteando).
- Un timer de tiempo transcurrido junto al badge.
- Una línea de estado por fase con microcopy humana: "Cloning repository…", "Scanning 42 files for CUDA API calls…", "hipify-perl translating…".
- Si el run lleva >N s en QUEUED en modo replay: mensaje honesto "Replay mode — new runs don't execute; watch the recorded run" con link al run sembrado.

#### 6. "Errors Resolved" muestra los errores iniciales
`app.js:117-127` — la tarjeta titulada **Errors Resolved** pinta `errors_initial` en grande y "→ current" chico (en vivo se ve "8 → 2"). Ocho no es lo resuelto: lo resuelto es 6. El número héroe del dashboard contradice su etiqueta.

**Recomendación:** pintar `initial − current` en grande y "8 → 2" como subtítulo, o retitular a "Build Errors" con el burndown "8 → 2" como valor. Decidir una semántica y que número y etiqueta cuenten lo mismo.

#### 7. Costo API: número inventado en el front
`app.js:134` — `tokens_remote * 0.000003` hardcodea un precio en el cliente, y el badge de la tarjeta dice "$0.00" fijo (`index.html`) aunque el valor calculado pueda ser >0. Dos fuentes de verdad que pueden contradecirse en pantalla, y viola el principio F-17 (números de reporte salen solo de código *de backend*).

**Recomendación:** el costo llega calculado en el evento `report` (backend, con el precio en `config.py`); el front solo lo pinta. El badge "$0.00" debe ser el mismo dato, no un literal.

#### 8. Jerga sin traducir
E01/E02 (tabla de fixes), W01…W07 (wave64), `NO_ORACLE`, tiers `deterministic/local/remote`, "delta", "Waiting for REPORTING phase…". El juez no hackathon-interno no tiene el decoder.

**Recomendación (barato y de alto impacto):**
- Tooltip/`title` con la descripción de cada clase de error (la taxonomía ya tiene nombres en `rules.yaml`) y de cada patrón wave64 (las explicaciones fijas F-17 **ya existen en backend** — el evento las trae o puede traerlas; hoy `app.js:381` descarta todo salvo file/line/pattern).
- `NO_ORACLE` → subtítulo "no test oracle available — build verified only".
- Placeholder del diff: "The CUDA→HIP diff appears when porting completes" en lugar del nombre interno de la fase.

#### 9. FAILED sin causa; eventos `scan` y `run_meta` descartados
`app.js:374-378` guarda `scan` y `run_meta` en el estado y **ningún render los usa**. Ahí está el contexto que humaniza el proceso (LOC, nº de llamadas CUDA, dificultad estimada). Y ante `FAILED`, la UI solo pinta el badge rojo — la causa (clone falló, presupuesto agotado, NEEDS_HUMAN) queda enterrada en el trace/certificado.

**Recomendación:** una tarjeta "Repo" al inicio (nombre, LOC, API calls, dificultad — datos del evento `scan`) y, en estado terminal no-verde, un panel "Why" con el último error del trace + la sección NEEDS_HUMAN del reporte.

---

### P2 — Usabilidad y robustez

#### 10. Sin indicador de modo
El dashboard no distingue replay/mock/real. Mínimo: exponer `oracle_mode` en `/healthz` y pintar un badge discreto "● REPLAY — recorded run" / "● LIVE — MI300X". Es honestidad barata y en el pitch suma ("esto que ven es una grabación de la GPU real").

#### 11. Sin dimensión temporal ni señal de vida
No hay hora de inicio, duración de fases, ni timestamps en builds/fixes; tampoco un "latido" que confirme que el polling está vivo (si el server muere, la página simplemente se congela — combinado con el hallazgo 1, cambia a datos falsos). Un dot verde pulsante "live · updated 1s ago" + elapsed por fase resuelve ambos.

#### 12. Interpolación sin escapar (XSS desde el repo objetivo)
`renderWave64()` y `renderFixes()` interpolan `w.file`, `klass`, `f.commit` sin `escapeHtml()` (que existe y se usa en `renderDiff`). Los paths de archivo vienen **del repo que se portea** — un repo con un nombre de archivo hostil inyecta HTML en el dashboard. Improbable en el demo, trivial de cerrar: pasar todo interpolado por `escapeHtml`.

#### 13. Accesibilidad
- Severidad wave64 y deltas comunican **solo por color** (rojo/ámbar/verde) — el texto del label ya ayuda ("Correctness"/"Suspicious"), mantenerlo siempre.
- Ninguna región `aria-live`: un lector de pantalla no se entera de nada de lo que el polling actualiza. Mínimo: `aria-live="polite"` en el badge de estado y el verdict.
- Contrastes: `text-gray-600` sobre `#0a0a0f` (footer, placeholders, "findings") queda bajo AA para texto pequeño.
- Animaciones permanentes (pulse, sparkline) sin `@media (prefers-reduced-motion)`.
- El form nuevo ya tiene `label for` + `focus:ring`; replicar focus visible en el toggle del certificado (es un `div` clickeable — debería ser `<button>`).

#### 14. Certificado: colapsado por defecto + bug de primer clic ✅ (bug corregido)
`initCertToggle` inicializaba `open = true` con el contenido oculto: **el primer clic era un no-op** (cerraba lo ya cerrado) y el label decía "Expand certificate" siempre. Corregido en esta pasada (estado inicial coherente + label que alterna). Queda la decisión de producto: siendo "the deliverable", al llegar `DONE` con PASS probablemente deba **auto-expandirse** (o al menos animar la aparición del botón Download).

---

### P3 — Pulido

- **highlight.js + su CSS + 2 language packs se cargan y no se usan**: `renderDiff` colorea con clases propias y el certificado usa `marked` sin resaltado. Quitar 4 requests (o usarlo de verdad en los bloques de código del certificado).
- **Favicon + title dinámico**: `⚡ HIPnosis — BUILD_LOOP (2 errors left)` en el tab vende solo; favicon evita el ícono roto en el video.
- **Sparkline**: la línea roja con punto final verde es sutilmente contradictoria con la narrativa "bajando = bueno"; considerar degradado rojo→verde.
- **Drip del demo estático** (`loadDemoData`, 120 ms fijos): pausas naturales (más lento en `build`, rápido en `classify`) harían la reproducción más creíble.
- **Footer**: agregar link al repo GitHub (la submission lo exige público — el juez que quiere el código no tiene link desde la UI).

---

## Heurísticas de Nielsen — scorecard

| Heurística | Estado | Nota |
|---|---|---|
| 1. Visibilidad del estado del sistema | 🟡 | Fuerte en BUILD_LOOP→DONE, muda en QUEUED/CLONING y sin señal de vida del polling (H5, H11) |
| 2. Coincidencia sistema–mundo real | 🟡 | Jerga interna expuesta sin decoder (H8) |
| 3. Control y libertad del usuario | 🟡 | Ya se puede iniciar run (✅); falta navegar entre runs (H4) |
| 4. Consistencia y estándares | 🟢 | Sistema visual coherente (glass, badges, tablas) |
| 5. Prevención de errores | 🟡 | Input valida `type=url`; pero URL no-git o repo privado solo fallan minutos después sin explicación (H9) |
| 6. Reconocimiento antes que recuerdo | 🔴 | Códigos E/W y run-ids requieren memoria del equipo (H4, H8) |
| 7. Flexibilidad y eficiencia | 🟢 | `?run=` como deep-link funciona bien |
| 8. Diseño estético y minimalista | 🟢 | El punto más fuerte del dashboard |
| 9. Ayudar a reconocer y recuperarse de errores | 🔴 | FAILED sin causa; caída de red → datos falsos (H1, H9) |
| 10. Ayuda y documentación | 🟡 | Microcopy de wave64 excelente; el resto de secciones no se explican |

---

## Plan recomendado (2 días al deadline)

**Ola 1 — antes del video/demo (≤ medio día): ✅ COMPLETADA (ver sección "Ola 1 — ejecutada")**
1. ~~Matar el fallback silencioso a demo (H1)~~ ✅
2. ~~Vendorizar CDNs (H2)~~ ✅
3. ~~Fix a "Errors Resolved" (H6) y quitar highlight.js muerto (H15)~~ ✅
4. ~~Badge de modo REPLAY/LIVE (H10) + repo URL del run en el header (parte de H5)~~ ✅

**Ola 2 — antes de la submission: ✅ COMPLETADA (ver sección "Ola 2 — ejecutada")**
5. ~~Selector de runs (H4) y estado "why failed" (H9)~~ ✅
6. ~~Tooltips de jerga + placeholders humanos (H8)~~ ✅
7. ~~Escape HTML en tablas (H12) y `aria-live` mínimo (H13)~~ ✅

**Ola 3 — si sobra tiempo: ✅ COMPLETADA (ver sección "Ola 3 — ejecutada")**
8. ~~Timers/elapsed (H11), tarjeta de scan (H9b), title dinámico + favicon (H16), auto-expand del certificado en DONE (H14)~~ ✅ + H7 (costo desde backend)

**Pendientes menores tras las 3 olas** (todos nice-to-have): duración por fase (resto de H11), microcopy/elapsed por fase temprana (resto de H5), sparkline con degradado rojo→verde, link al repo GitHub en el footer (bloqueado: el repo aún no es público).

## Ola 3 — ejecutada (2026-07-09)

Verificado end-to-end en Chrome (replay completo QUEUED→DONE) + 370 tests verdes.

1. **H7 — Costo calculado en backend (F-17 de verdad)**: hallazgo adicional al implementarlo — el evento `report` que el dashboard consume **solo existía en el fixture demo**; el pipeline real nunca lo emitía. Ahora `phases/pipeline.py` emite `report` al final de REPORTING con los counters frescos del store + `cost_remote_usd` calculado con `remote_price_per_mtok` (nuevo en `config.py`, env `REMOTE_PRICE_PER_MTOK`). El front dejó de conocer precios: pinta `cost_remote_usd` (fallback: $0.00 solo si `tokens_remote === 0`, si no "—"), y la pill fija "$0.00" pasó a ser el descriptor "Fireworks · hard cases". Fixture demo actualizado con el campo.
2. **H9 (resto) — Strip de scan**: fila compacta sobre las métricas hero con los datos del evento `scan` que se descartaban — CUDA files, kernel LOC, total de llamadas API CUDA, build system, dificultad (coloreada easy/medium/hard) y GPU target (de `run_meta`).
3. **H11 (resto) — Run time**: "run time 37s" bajo el indicador de conexión, calculado de los timestamps del trace (en replay muestra la duración *grabada*, no la del playback — honesto).
4. **H16 — Favicon + title dinámico**: favicon SVG inline (data URI, sin request) y `document.title` = "HIPnosis · BUILD LOOP/DONE/…" — el estado se ve desde el tab.
5. **H14 (resto) — Certificado auto-expandido**: al renderizarse llega abierto con label "Collapse certificate" (es el deliverable, no un acordeón).
6. **H13 (resto)**: `prefers-reduced-motion` (mata animaciones/transiciones) y sweep de contraste `text-gray-600` → `text-gray-500`.
7. **P3 — Pacing del drip demo**: pausas por tipo de evento (build 500 ms, phase 350 ms, resto 100 ms) — la reproducción estática respira como un run real.

---

## Ola 1 — ejecutada (2026-07-09)

Todo verificado end-to-end en Chrome contra el server replay, más suite completa (370 tests verdes).

1. **H1 — Polling robusto y honesto** (`app.js`): retry con backoff (1s→2s→…→5s tope) e indicador de conexión (`live` con dot verde / `connection lost — retrying…` / `run finished`). Los fixtures demo solo se cargan si la API **nunca** respondió y no llegó ningún evento (caso: dashboard servido estático), y se anuncian con badge "DEMO · offline fixtures" + "orchestrator unreachable". Un run con API viva jamás se degrada a datos falsos. `404` con API viva = mensaje "run not found" explícito (antes: silencio o datos demo). Verificado matando el server a mitad de un poll (muestra retrying, conserva el run) y sirviendo el dashboard con `http.server` puro (demo con banner).
2. **H2/H15 — Cero CDNs** (`dashboard/vendor/`): Tailwind generado como CSS estático one-shot (`scripts/build-css.sh`, config espejo en `dashboard/tailwind.config.js` — sin build step en runtime, F-15; anotado como D-6 en DEVIATIONS.md), fuentes variables Inter + JetBrains Mono locales (woff2, ~48+40 KB), `marked.min.js` local, highlight.js eliminado (nunca se usaba). Verificado por red: la página carga con **cero requests externos**. Bonus: JetBrains Mono ahora carga de verdad (el CDN nunca la incluyó — la fuente mono declarada jamás se había servido).
3. **H6 — Métrica corregida**: "Errors Resolved" muestra los resueltos (`inicial − actuales`) con "8 → 0" como subtítulo. Verificado en vivo (mid-run: "3", "8 → 5").
4. **H10 + parte de H5 — Contexto en el header**: `/healthz` ahora expone `mode` (test actualizado) y la UI pinta badge REPLAY · recorded run / LIVE · MI300X / MOCK / DEMO; la **URL del repo del run** se muestra bajo el run-id (truncada, tooltip completo).

## Ola 2 — ejecutada (2026-07-09)

Verificado end-to-end en Chrome contra el server replay (selector con 2 runs y navegación real; paneles de outcome ejercitados inyectando eventos `failed` y `build_loop.done` reales por consola; tooltips confirmados por atributo).

1. **H4 — Selector de runs**: `<select>` nativo en el header (accesible, cero dependencias) poblado de `GET /runs` con `id · estado`; al cambiar navega a `?run=<id>`. Si la lista no carga, queda el run-id plano como fallback.
2. **H9 (parcial) — La causa del final no-verde, visible**: nueva sección de outcome que consume dos eventos del trace que la UI descartaba: `failed` (`reason` + `exc_type`, panel rojo "Why this run failed") y `build_loop.done.needs_human` (panel ámbar "Needs human attention" con las firmas no resueltas — el espejo en UI de la degradación honesta del blueprint). Pendiente de H9: tarjeta con los datos de `scan` (LOC/dificultad).
3. **H8 — Decoder de jerga**: tooltips (`title` + `cursor-help`) en toda la jerga: clases E01–E99 (espejo de `core/rules.yaml`), patrones W01–W07 (espejo de las explicaciones F-17 de `core/wave64.py`), tiers deterministic/local/remote, columna "Delta" → "Δ errors" con explicación. `NO_ORACLE` siempre lleva subtítulo explicativo. Placeholder del diff humanizado ("The CUDA → HIP diff appears once porting completes"). Solo texto fijo descriptivo — los números siguen saliendo del backend (F-17).
4. **H12 — Escape HTML**: todo lo interpolado en tablas y paneles (paths de archivo, firmas, clases, commits — contenido que viene del repo objetivo) pasa por `escapeHtml()`.
5. **H13 (parcial) — `aria-live="polite"`/`role="status"`** en status badge, indicador de conexión y verdict; el selector tiene `aria-label`. Pendiente: contraste de grises y `prefers-reduced-motion`.
6. Bonus: la tabla de fixes usa `klass` directo del evento `fix` (antes solo el lookup por firma del evento `classify`).

## Cambios ya aplicados en la pasada inicial (2026-07-09)

1. **Input "New port" en el header** (`index.html`): form con `label` accesible, placeholder con ejemplo real, botón con estado de carga (`Starting…`), mensaje de error inline si el POST falla, y microcopy de una línea explicando qué hace HIPnosis. `POST /runs` → redirect a `?run=<id>`.
2. **Shell visible de inmediato** (`app.js` `init()`): la app ya no queda oculta tras el spinner hasta el primer evento — header, input y timeline de fases (todas pendientes) se ven desde el primer paint. El caso "API muerta y sin demo" reporta el error en el mensaje del form.
3. **Bug del toggle del certificado corregido**: estado inicial coherente con el contenido oculto (el primer clic ahora expande) y el label alterna Expand/Collapse.
4. Verificado end-to-end en Chrome contra el server replay: form renderiza, submit crea run y redirige, replay sembrado intacto.
