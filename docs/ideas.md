# 🧠 Brainstorm — AMD Developer Hackathon: ACT II

> **Objetivo:** ganar el Track 3 (Unicorn) + premio especial Gemma, con opción de stacking en Track 1.
> **Ventana:** 6–11 de julio de 2026 (5 días). Entregas cierran el 11 de julio, 12:00 PM.
> **Requisito duro:** todo envío debe estar contenedorizado y ser ejecutable.

---

## 0. TL;DR

**Recomendación principal: HIPnosis** — un agente autónomo que porta código CUDA a ROCm/AMD:
le das un repo de GitHub y el agente lo migra, compila, testea y benchmarkea en una MI300X real
hasta dejarlo verde, entregando un PR listo.

**Plan B (co-favorito): The Distillery** — "describe tu tarea → Gemma fine-tuneado sirviendo en AMD en 1 hora".

> ✅ **Validado online (sección 1.5):** no existe ningún producto que ocupe el espacio de
> HIPnosis. Lo más cercano es una demo viral de Claude Code (ene 2026) que valida el mercado
> pero no es producto — el posicionamiento se ajusta a "el port CON verificación".

**Techo de premios del proyecto principal: $4,500** (Track 3: $2,500 + Gemma: $2,000).
**Techo con stacking Track 1: $8,000.**

---

## 1. Leer la sala: qué quiere realmente el organizador

Cada patrocinador tiene una agenda. El proyecto ganador las valida **todas a la vez**:

| Actor | Su agenda real | Cómo se la validas |
|---|---|---|
| **AMD** (Nick Ni, Sr Director AI) | Demostrar que ROCm + MI300X sirven para IA real. Su dolor existencial es el lock-in de CUDA. | Que el stack AMD sea el **sustrato** del producto, no un endpoint decorativo. |
| **Google DeepMind** (Ian Ballantyne) | Ver a Gemma haciendo trabajo real: fine-tuning, orquestación con ingenio. Hay $6,000 en premios solo por esto. | Gemma como cerebro local / modelo fine-tuneado, no como "otra llamada API". |
| **Fireworks AI** | Tráfico de API en casos donde su velocidad importe. | Fireworks como el modelo "pesado" del sistema híbrido. |
| **lablab.ai / NativelyAI** | Proyectos contenedorizados, ejecutables, con pitch de startup. | `docker compose up` y funciona + video de demo impecable. |

**Criterios explícitos del Track 3:** creatividad y originalidad, potencial de mercado,
grado de completitud, uso de plataformas AMD.

**Matemática de premios — por qué Track 3:**
- Track 3 se decide por **jueces** → pesan storytelling, polish y narrativa de mercado.
- Tracks 1 y 2 se deciden por **leaderboard** → compites contra grinders de optimización; resultado incierto.
- Track 3 1er lugar ($2,500) + Gemma "mejor proyecto alojado en AMD" ($2,000) = **$4,500 apilables con un solo proyecto**.

**La fórmula ganadora:** el 90% de los envíos usará AMD/Fireworks como "un endpoint más".
Tu diferenciación es que el stack AMD sea *esencial* — que el proyecto no tenga sentido sin él.

---

## 1.5 Validación competitiva (research online, 7 jul 2026)

Revisión del landscape antes de construir. **Veredicto: nadie ocupa el espacio de
"porting CUDA→ROCm como producto agéntico verificado". El espacio está libre, pero el
posicionamiento debe ajustarse** (ver nota sobre Claude Code abajo).

### Prior art en migración CUDA→AMD (todo lo que existe)

| Proyecto | Qué es | Por qué NO es HIPnosis |
|---|---|---|
| **HIPIFY** (AMD) | Herramienta oficial de traducción sintáctica CUDA→HIP (~80-90% del código) | Mecánica, no semántica: no arregla errores de compilación, no detecta bugs de wavefront, no verifica ni benchmarkea. Es nuestra pieza [2. PORT], no un competidor. |
| **ZLUDA** | Capa de traducción runtime: corre binarios CUDA sobre AMD sin recompilar | Perdió su financiación en 2025-26 y volvió a ser **proyecto hobby de una persona**. Cobertura parcial. Traduce en runtime, no libera el código: el lock-in sigue. |
| **SCALE** (Spectral Compute) | Compilador que compila código CUDA nativamente para AMD | Empresa de consultoría UK, **closed-source, sin respaldo de AMD**. Recompila, no porta: tu codebase sigue siendo CUDA. HIPnosis entrega código ROCm nativo y un PR. |
| **GEAK** (AMD-AGI) | Familia de agentes de AMD que **generan y optimizan kernels Triton** desde descripciones | Genera kernels nuevos en Triton; no migra codebases CUDA existentes. Es señal de que AMD cree en agentes para GPU code — valida la tesis, no la compite. |
| **Papers académicos** (UniPar, LASSI, IntrinTrans, Sakana 2025) | Pipelines LLM multi-agente de traducción de código paralelo con loop compile-test | Investigación, no producto: sin UI, sin PR, sin reporte de paridad, sin CI. Validan que el approach técnico (loop agéntico + compilador como oráculo) funciona — cita 1-2 en el README para credibilidad. |
| **Claude Code demo viral** (ene 2026) | Un dev portó un backend CUDA a ROCm en ~30 min con Claude Code (Reddit/gist, cobertura de prensa: "¿se rompe el moat de NVIDIA?") | ⚠️ **El hallazgo más importante del research.** Ver análisis abajo. |

### ⚠️ El hallazgo clave: la demo viral de Claude Code (enero 2026)

Un agente de código generalista ya demostró que *puede* portar CUDA→ROCm. Esto tiene dos caras:

- **Amenaza:** "¿por qué no usar Claude Code y ya?" — el porting crudo está parcialmente
  comoditizado por agentes generalistas.
- **Regalo:** la prensa ya validó el mercado y educó a los jueces. Y la demo viral expuso
  exactamente lo que le falta a un agente generalista para ser producto.

**Reposicionamiento de HIPnosis (consecuencia directa):** no vendemos "un agente que porta"
— vendemos **la capa de verificación y entrega que convierte un port en un port confiable**:

1. **Paridad numérica garantizada** — Claude Code no te dice si los resultados son idénticos; nuestro harness sí.
2. **Detección semántica de bugs wave64** — el linter agéntico de warp-size 32→64 que ningún tool tiene.
3. **Benchmark en MI300X real** — "compila" ≠ "rinde"; entregamos TFLOPs medidos.
4. **Modelos abiertos en infra AMD** — Gemma + Fireworks, sin dependencia de un modelo cerrado (requisito del hackathon y argumento de soberanía para el cliente).
5. **Producto, no sesión de chat** — Portability Report, PR automático, modo CI.

**Nuevo gancho de pitch:** *"En enero, Claude Code se hizo viral portando CUDA a ROCm en 30
minutos. Pero una demo no es un producto: nadie garantizó que los números fueran correctos.
HIPnosis es el port CON pruebas: paridad numérica, detección de bugs de wavefront y benchmarks
en silicio AMD real — construido 100% con modelos abiertos."*

### Landscape de la Idea 2 (The Distillery)

- **OpenPipe** — el jugador icónico de destilación — **pivoteó a RL y fue adquirido por
  CoreWeave (sep 2025)**; su producto original de destilación quedó absorbido en el stack
  CoreWeave. El nicho "destilación simple self-serve" quedó más vacío de lo que parecía.
- **Pero:** en el ACT I abundaron los proyectos de fine-tuning de modelos pequeños
  (CyberSecQwen-4B, Path to Care con Gemma+LoRA en MI300X…). Para estos jueces,
  "fine-tuneé un modelo en AMD" ya no es novedad — la *plataforma* que lo automatiza lo sería,
  pero parte con menos frescura percibida. **Punto para HIPnosis.**

### Qué ganó en el ACT I (para no repetir)

477 proyectos. Dominaron: salud/clínica (OncoTriage, ClinSight, Path to Care, Autonomous
Oncology Board), IDEs con IA, y modelos especialistas fine-tuneados. **Cero proyectos de
porting CUDA→ROCm o developer tools para el ecosistema GPU de AMD.** El carril está vacío
y es el que más le duele/importa al juez principal.

---

## 1.6 El enfoque definitivo de HIPnosis: capas y confianza

*(Versión condensada — el desarrollo completo está en [`hipnosis.md`](hipnosis.md).)*

**Abstracción 1 — la capa del stack determina el destino estratégico.** El moat de CUDA se
puede atacar en cuatro capas: binario/runtime (ZLUDA), compilador (SCALE), fuente-sintáctico
(HIPIFY) y generación greenfield (GEAK). ZLUDA y SCALE son **capas de compatibilidad**, y las
capas de compatibilidad tratan el síntoma ("mi código no corre en AMD") preservando la
enfermedad ("mi codebase está escrito en el idioma del monopolio"). La historia del software
es brutal con esa categoría (Wine nunca mató a Windows; la compatibilidad Windows de OS/2 mató
a OS/2). AMD lo entendió: retiró el funding de ZLUDA. **HIPnosis se para en la única capa que
cura: la migración del activo** — cruzas la frontera una vez, con papeles, y el resultado es
código ROCm nativo que el cliente posee, sin dependencia runtime de nadie. Framing de pitch:
ZLUDA te deja *correr*, SCALE te deja *recompilar*, HIPnosis te hace *ciudadano*.

**Abstracción 2 — el producto no es la traducción, es la confianza.** La traducción cruda está
comoditizada (hipify + la demo viral de Claude Code lo prueban). Lo que detiene a un CTO es:
*"¿cómo sé que el código convertido es correcto y rápido, y cuánto me cuesta averiguarlo?"*
Un port que compila pero produce números sutilmente distintos es peor que no portar.
**HIPnosis es una máquina de verificación cuyo subproducto es el port** — la unidad de valor
es el certificado: paridad numérica medida, auditoría wave32→wave64, benchmark en silicio real.

**Abstracción 3 — por qué es viable como agente:** el loop está anclado por **oráculos no
negociables** (compilador, tests, diff numérico, profiler). Es un problema de búsqueda de lazo
cerrado con objetivo verificable — la clase exacta de problema donde los agentes funcionan en
2026. La alucinación no se mitiga: queda estructuralmente contenida.

**Abstracción 4 — el activo que se compone:** la **taxonomía de fallos de porting** (wave64,
máscaras de shuffle, gaps cuDNN→MIOpen, idiomas de occupancy…) codificada como detectores +
plantillas de fix. Cada repo portado la enriquece → flywheel. Y cada trace del loop
(error→parche→¿compiló?→¿pasó paridad?) es un dato de entrenamiento con **recompensa
verificable** → el roadmap natural es entrenar por RL un "Gemma porter" propio (ver §1.7).

**GEAK no es competencia, es componente:** en la fase de optimización post-port, los kernels
calientes pasan por GEAK. "Integramos el agente de AMD como subrutina del nuestro" vale oro
ante el juez.

---

## 1.7 La lección OpenPipe → CoreWeave (y qué implica para nosotros)

*(Versión condensada — el análisis completo y su aplicación está en
[`vertigodx-finetune.md`](vertigodx-finetune.md).)*

**La historia en tres actos:** (1) 2023–24: OpenPipe facturaba destilando workflows GPT-4 a
modelos abiertos pequeños (SDK-proxy que capturaba tráfico → SFT → 1/10–1/50 del costo).
(2) 2024–25: la economía se rompió — los precios frontier colapsaron ~10x/año (el ahorro se
evaporaba antes del payback) y la destilación SFT se volvió *feature* de plataforma (OpenAI
distillation API, Fireworks/Together fine-tuning). Lección: **la destilación SFT es una
feature, no una empresa.** (3) 2025: pivot a RL para agentes — **ART** (GRPO sobre trayectorias
reales del agente, checkpoints LoRA) y **RULER** (LLM-juez que rankea trayectorias como reward:
sin labels, sin reward engineering; ganó a frontier prompteado en 4/4 tareas). Sep 2025:
**CoreWeave los adquiere** (tras comprar W&B) → "serverless RL" en oct 2025.

**Implicancias:**
1. *Mercado:* un neocloud de GPUs subiendo por el stack (GPUs → tracking → training) para no
   ser commodity — **exactamente el movimiento que AMD intenta con este hackathon.** Entender
   esto es entender al juez.
2. *Técnica:* el valor migró de **copiar salidas del teacher** (SFT) a **optimizar contra
   recompensas verificables en el entorno** (RLVR/GRPO). Frontera nítida: tarea estrecha y
   estática (clasificar, extraer, formatear) → SFT sigue siendo la herramienta correcta y más
   barata; tarea multi-paso con éxito medible → RL.
3. *Para nuestros proyectos, corta en direcciones opuestas:* valida el fine-tuning SFT para
   **vertigoDx** (tarea estrecha, con oráculo programático propio — caso de libro) y convierte
   a **HIPnosis** en tierra fértil de RL a futuro (compila/testea/paridad = rewards duros
   gratis; ni siquiera necesita RULER).

---

## 2. Las 7 ideas, desarrolladas

### Idea 1 — 🥇 HIPnosis: el agente que porta CUDA → ROCm

**Pitch (15 seg, versión post-research — ver sección 1.5):** *"En enero, Claude Code se hizo
viral portando CUDA a ROCm en 30 minutos. Pero una demo no es un producto: nadie garantizó que
los números fueran correctos. HIPnosis es el port CON pruebas: pégale la URL de tu repo CUDA y
recibe un PR verificado — paridad numérica, detección de bugs de wavefront y benchmarks en
silicio AMD real — construido 100% con modelos abiertos."*

**El dolor latente:** miles de empresas miran GPUs AMD sensiblemente más baratas y con más VRAM,
pero no migran porque su código está escrito en CUDA. El costo de switching no es hardware,
es tiempo de ingeniería. AMD literalmente paga consultores para hacer estas migraciones a mano.

**Por qué es ingenioso (y no sobreingeniería):**
- AMD ya tiene la herramienta mecánica (`hipify-clang`) que convierte ~80% del código.
  El problema es el **último 20%**: PTX inline, supuestos de warp size, gaps de librerías,
  build systems rotos. Ese 20% es exactamente la forma de problema donde un agente con
  loop de verificación real brilla.
- No inventas nada frágil: orquestas una herramienta probada + un **compilador como oráculo
  de verdad** + tests como criterio de éxito. El agente nunca "alucina que funcionó" porque
  el compilador y los tests no negocian.

**El bug perfecto para la demo:** las GPUs NVIDIA ejecutan en warps de 32 threads; las AMD en
wavefronts de 64. Código CUDA con `32` hardcodeado (shuffles, reducciones, máscaras `0xffffffff`)
**compila perfectamente en ROCm y da resultados incorrectos en silencio**. `hipify` NO lo detecta
— es un bug semántico, no sintáctico. Un agente que lo detecta y corrige demuestra en 30 segundos
por qué esto necesita IA y no un script. Graba ese momento en el video.

**Arquitectura (deliberadamente simple):**

```
repo URL
   │
   ▼
[1. SCAN]      Gemma local (vLLM-ROCm en la MI300X) inventaría el repo:
               superficie CUDA, llamadas cuBLAS/cuDNN, build system.
               → Emite "Portability Report": dificultad estimada + ahorro en USD.
   │             (Este reporte gratis es el wedge freemium de go-to-market.)
   ▼
[2. PORT]      hipify-clang hace el 80% mecánico.
   │
   ▼
[3. LOOP]      Compila en la MI300X real. Cada error se enruta:
               • trivial  → Gemma local (0 tokens remotos)
               • duro     → Fireworks (Qwen3-Coder / DeepSeek)
               Parche → rebuild → repetir hasta verde.
   │
   ▼
[4. VERIFY]    Tests del repo + harness de paridad numérica
               (mismos inputs, ¿mismos outputs que la versión CUDA?) + benchmark.
   │
   ▼
[5. DELIVER]   PR en GitHub: diff + reporte de paridad + "corre a X TFLOPs en MI300X".
```

**Detalle de pitch que enamora a los jueces:** el paso 3 es la filosofía del Track 1
(routing híbrido token-eficiente: local barato vs remoto potente) **viviendo dentro de un
producto del Track 3**. Coherencia total con el espíritu del evento.

**Modelo de negocio:**
- *Freemium:* Portability Report gratis (lead-gen — le dice al CTO cuánto ahorraría).
- *Pago:* la migración completa, por repo o por suscripción CI ("cada PR de tu equipo se
  verifica también contra ROCm").
- *Cliente:* cualquier empresa de ML/HPC con código CUDA y presión de costos de GPU.
- *TAM en una slide:* (precio hora H100 − precio hora MI300X) × horas anuales del cliente
  × #empresas bloqueadas por CUDA. Es cuantificable en dólares, no en vibes.

**Mapeo contra criterios del jurado:**

| Criterio | Puntaje | Por qué |
|---|---|---|
| Creatividad/Originalidad | ★★★★★ | No existe producto agéntico pulido para esto. Es "el agente que hace crecer el ecosistema del propio juez" — meta y memorable. |
| Potencial de mercado | ★★★★★ | Ahorro cuantificable en USD; AMD es a la vez juez, sponsor y cliente emocional. |
| Completitud | ★★★★☆ | Demo con 2–3 repos reales portados end-to-end + dashboard en vivo. |
| Uso de plataformas AMD | ★★★★★ | ROCm es el sustrato del producto; la MI300X es el oráculo de verificación; Gemma + Fireworks son el cerebro. Máximo posible. |

**Riesgos y mitigaciones:**
- *Build systems infernales* → MVP restringido a CMake/Makefile simples; imagen Docker base
  pre-horneada con todo el toolchain ROCm.
- *Repos gigantes* → curar de antemano 3 repos objetivo pequeños/medianos (librerías de
  kernels standalone, NO PyTorch). El demo se graba sobre esos; el producto acepta cualquiera.
- *"hipify ya hace casi todo"* → esa es la trampa retórica: la demo muestra el contador de
  errores bajando de 47 → 0 **después** de hipify. El valor está en la última milla, y se hace visible.

---

### Idea 2 — 🥈 The Distillery: destilación autopilot ("prompt → Gemma fine-tuneado en AMD en 1 hora")

**Pitch:** *"Describe tu tarea en una frase. En una hora tienes un Gemma fine-tuneado que la hace
al 95% de la calidad de un modelo frontier, a 1/40 del costo, entrenado y sirviendo en GPUs AMD.
Con report card de calidad incluido."*

**El dolor latente:** la economía de agentes exige modelos pequeños y baratos por tarea, y todo
el mundo habla de destilación — pero casi nadie la hace porque el pipeline (datos sintéticos,
filtrado, fine-tuning, eval, serving) es fricción pura y conocimiento de brujo. El desarrollador
promedio quiere el resultado, no el ritual.

**Pipeline:**

```
descripción de tarea + 5-10 ejemplos del usuario
   │
   ▼
[1. DESIGN]    El agente diseña el schema de datos y el plan de generación.
   ▼
[2. GENERATE]  Modelo grande en Fireworks (el "profesor": DeepSeek/Llama/Qwen)
               genera el dataset sintético (2-5k ejemplos).
   ▼
[3. FILTER]    Dedupe + LLM-judge descarta ejemplos de baja calidad.
   ▼
[4. TRAIN]     LoRA sobre Gemma-3 4B/12B en la MI300X (TRL/PEFT corren en ROCm).
   ▼
[5. EVAL]      Eval automática contra el profesor en held-out set.
               → Report card: "94% de la calidad del profesor a 1/40 del costo."
   ▼
[6. SERVE]     vLLM-ROCm sirve el modelo + endpoint OpenAI-compatible + pesos descargables.
```

**Scope quirúrgico (la anti-sobreingeniería):** SOLO tres tipos de tarea en el MVP —
clasificación, extracción estructurada y transferencia de estilo. Nada de razonamiento
complejo ni agentes. Tres tipos bien resueltos > diez a medias.

**La demo hipnótica:** entrenar un modelo EN VIVO durante el video de 3 minutos.
Ejemplo: "clasificador de sentimiento financiero en español" o "redactor de PII".
Mostrar el report card al final: calidad vs profesor, costo por millón de tokens, latencia.

**Modelo de negocio:** SaaS por modelo entrenado o suscripción; el cliente es cualquier equipo
que quema dinero llamando a modelos frontier para tareas repetitivas de clasificación/extracción
(fintechs, legaltech, soporte, moderación de contenido).

**Fortalezas:**
- **Máximo puntaje Gemma** de todas las ideas: fine-tuning + serving de Gemma = candidato
  natural al premio de $2,000 ("mejor proyecto Gemma alojado en AMD").
- Historia AMD doble: **entrenamiento Y serving** en MI300X.
- Riesgo técnico menor que HIPnosis: TRL/PEFT/axolotl ya soportan ROCm.

**Debilidad honesta (actualizada con el research de la sección 1.5):** OpenPipe pivoteó a RL
y fue adquirido por CoreWeave (2025), así que el nicho self-serve quedó más libre de lo esperado
(queda Predibase). El problema real es otro: **en el ACT I abundaron los proyectos de
fine-tuning sobre AMD** (CyberSecQwen-4B, Path to Care con Gemma+LoRA en MI300X) — para estos
jueces, "fine-tuning en AMD" ya no es fresco. La plataforma que lo automatiza sí lo es,
pero parte con menos novedad percibida que HIPnosis.

**Riesgos:** entorno de fine-tuning en ROCm puede dar sorpresas de dependencias
→ resolver el Día 1; si LoRA en MI300X se atasca, fallback a QLoRA o a Gemma 4B.

---

### Idea 3 — Swarm-on-a-Chip: 20 agentes Gemma en una sola GPU

**Pitch:** *"Una MI300X = una empresa entera de agentes. 192 GB de VRAM permiten correr
15–20 instancias de Gemma-27B en paralelo en un solo chip: auditorías de código masivas,
paneles de verificación adversarial, análisis de miles de documentos — sin cluster."*

**El dolor latente:** los flujos multiagente serios (paneles de jueces, verificación cruzada,
fan-out sobre corpus grandes) son carísimos y lentos vía API, y montarlos on-prem exige clusters.

**El insight de hardware:** la MI300X tiene **192 GB de VRAM vs 80 GB de una H100**.
Es la única idea de la lista que explota una ventaja física exclusiva de AMD: lo que aquí
corre en un chip, en NVIDIA necesita 2–3 GPUs con todo el overhead de orquestación.

**Caso de uso demo:** auditoría de seguridad de un repo completo — 20 agentes Gemma revisan
módulos en paralelo con lentes distintas (inyección, secretos, lógica), un agente sintetizador
consolida, y un panel adversarial de 3 vota cada hallazgo antes de reportarlo.

**Por qué NO es la recomendación principal:** es una demo técnica espectacular buscando un
caso de uso — la historia de producto es más débil ("¿por qué no llamo a una API y ya?").
El potencial de mercado es difuso comparado con las ideas 1 y 2.

**Mejor uso de esta idea:** como *feature* dentro de HIPnosis (varios agentes portando módulos
en paralelo) o como slide de "esto solo es posible en AMD" en cualquier pitch. Es un
amplificador, no un producto.

---

### Idea 4 — Sovereign AI in a Box: IA privada llave en mano sobre AMD

**Pitch:** *"El ChatGPT interno de tu hospital, estudio jurídico o ministerio: un
`docker compose up` que levanta asistente conversacional + RAG sobre tus documentos +
transcripción de audio, 100% en tu hardware AMD. Tus datos jamás salen del edificio."*

**El dolor latente:** salud, legal, banca y gobierno no pueden mandar datos a APIs de terceros
(HIPAA, GDPR, secreto profesional, soberanía nacional). Hoy sus opciones son: no usar IA,
o proyectos de integración de 6 meses.

**Stack:** Gemma-27B (chat + RAG) + Whisper (transcripción) + embeddings, todo sirviendo
vía vLLM sobre ROCm, con UI web simple y conectores de ingesta (PDF, docx, audio).
La MI300X de 192 GB permite que TODO el stack viva en una sola GPU — el argumento de
venta es "un servidor, no un datacenter".

**Modelo de negocio:** licencia por instalación + soporte. El canal natural son los
integradores de sistemas que ya venden a gobierno/salud.

**Fortalezas:** narrativa de mercado sólida y muy alineada con AMD ("IA soberana sobre
hardware abierto"); completitud alcanzable en 5 días porque son piezas maduras.

**Por qué no es la principal:** baja originalidad — habrá muchos proyectos "RAG privado con
Gemma" en el hackathon, y la demo es genérica (un chat más). Pierde en el criterio de
creatividad, que es el primero de la lista del jurado.

**Cómo rescatarla si se elige:** verticalizar brutalmente. No "IA privada genérica" sino
*una* vertical con demo real: p.ej. "escriba médico: graba la consulta, genera la ficha
clínica estructurada, todo offline". La verticalización compra originalidad.

---

### Idea 5 — Wavefront: "cualquier modelo de HuggingFace, óptimo en ROCm, sin prueba y error"

**Pitch:** *"¿Correrá mi modelo en AMD? ¿Con qué cuantización, qué flags de vLLM, qué batch?
Wavefront lo averigua por ti: un agente que toma cualquier modelo de HuggingFace, explora
configuraciones de serving en una MI300X real y te entrega la config óptima con benchmarks."*

**El dolor latente:** servir modelos en ROCm hoy es prueba y error: qué cuantizaciones
funcionan, qué flags de vLLM, qué shapes de batch rinden. Cada equipo re-descubre lo mismo.

**Mecánica:** el agente lee la model card, propone un espacio de configs (cuantización ×
paralelismo × flags), las ejecuta en la MI300X midiendo throughput/latencia/calidad
(perplejidad en un set fijo), y publica un "AMD Serving Report" reproducible.
Efecto de red: los reportes se acumulan en un índice público — "el caniusegpu.com de ROCm".

**Fortalezas:** dolor real y específico del ecosistema AMD; el índice público tiene efecto
de red y valor comunitario que a AMD le encantaría adoptar.

**Por qué no es la principal:** es el hermano menor de HIPnosis — mismo espíritu
("que AMD simplemente funcione") con menos profundidad técnica y menos historia de agente.
**Mejor uso:** slide de roadmap de HIPnosis ("fase 2: no solo tu código, también tus modelos").

---

### Idea 6 — CaptionForge: Gemma fine-tuneado para los 4 tonos (Track 2)

**Pitch:** *"Un solo Gemma-3 vision, cuatro personalidades: LoRA fine-tuneado para generar
captions formales, sarcásticos, humor-tech y humor-no-tech de clips de video."*

**Mecánica:** frames muestreados + transcript de audio (Whisper en MI300X) → Gemma 3 vision
→ caption en el tono pedido. El diferencial: **fine-tuning de tono con LoRA** (el reglamento
lo permite explícitamente) usando dataset sintético generado por un modelo grande de Fireworks
y filtrado por LLM-judge — exactamente el pipeline de The Distillery aplicado a este track.

**El premio:** el especial Gemma del Track 2 es **el más gordo de todos ($3,000)** + $2,500
del primer lugar del track = techo de $5,500.

**Por qué no es la principal:** es leaderboard (LLM-judge evalúa precisión y tono) → resultado
incierto contra un campo desconocido, y no construye un producto que resuelva un dolor —
que es lo que pediste. **Solo tiene sentido si el equipo es de 3+ y alguien puede dedicarse
a esto en paralelo sin tocar el proyecto principal.**

---

### Idea 7 — Router-as-a-Product: el gateway híbrido token-eficiente (Track 1 productizado)

**Pitch:** *"Un gateway OSS drop-in (API OpenAI-compatible) que decide por request si tu query
la resuelve un Gemma local (0 tokens remotos) o necesita un modelo frontier vía Fireworks.
Facturas de LLM 40–70% más bajas sin tocar tu código."*

**El dolor latente:** las empresas queman dinero mandando queries triviales a modelos frontier.
El 60–80% del tráfico real de un producto LLM es resoluble por un modelo pequeño.

**Técnicas para el leaderboard del Track 1 (se evalúa: tokens consumidos + precisión):**
- **Gating por confianza:** el modelo local responde primero; si la confianza (logprobs,
  self-consistency barata) supera umbral, se entrega. Solo escala a Fireworks si duda.
- **Draft local, verificación remota:** el local redacta, el remoto solo valida/corrige
  (verificar es más barato en tokens que generar).
- **Cache semántico** de respuestas previas.
- **Compresión de prompt** antes de cualquier llamada remota.

**Por qué no es la principal como producto:** mercado ya poblado (RouteLLM, NotDiamond,
Martian) → pierde en originalidad ante jueces que conocen el espacio.

**Su verdadero valor — la jugada de stacking:** el loop de HIPnosis (Idea 1) YA contiene
este router (Gemma para errores triviales, Fireworks para los duros). Extraerlo como entrada
standalone al Track 1 cuesta medio día y compra un boleto de lotería de $2,500 + $1,000
(premio Gemma Track 1 "mejor uso vía Fireworks").

---

## 3. Estrategia de premios (prize stacking)

| Jugada | Track | Techo | Esfuerzo | Decisión |
|---|---|---|---|---|
| **HIPnosis** (o Distillery) | 3 | $2,500 + $2,000 Gemma = **$4,500** | 4.5 días | ✅ Principal |
| Router extraído de HIPnosis | 1 | $2,500 + $1,000 Gemma = **$3,500** | 0.5 día | ⚠️ Solo si sobra tiempo |
| CaptionForge | 2 | $2,500 + $3,000 Gemma = **$5,500** | 2+ días | ❌ Solo con equipo 3+ |

**Techo realista: $4,500. Techo con stacking: $8,000.**

> ⚠️ **Verificar en el Discord de lablab** que un equipo puede enviar proyectos a más de un
> track — históricamente lo permiten con proyectos separados, pero confírmalo antes de
> invertir el medio día.

---

## 4. Plan de ejecución — 5 días (HIPnosis)

| Día | Objetivo | Detalle |
|---|---|---|
| **1 (Jul 6-7)** | Infraestructura | Droplet MI300X + imagen Docker con ROCm/hipify/vLLM. Harness: clone → hipify → build → captura de errores. Elegir los 3 repos demo (librerías de kernels pequeñas/medianas con tests). ⚠️ Créditos de registro tardío llegan el **7 de julio**. |
| **2** | El loop | Loop agéntico (error → parche → rebuild) con Fireworks + triage Gemma local. Trace JSON de cada paso (será la visualización del dashboard). |
| **3** | Verificación | Tests del repo + harness de paridad numérica + benchmark. Generación automática de PR + Portability Report (Gemma). |
| **4** | Producto | Dashboard web (URL → log del agente en vivo → PR). Contenedorización final: `docker compose up` y funciona. Pulido. |
| **5** | Submission | **Video demo primero** (es el activo #1 para jueces — incluir el momento del bug warp-size 32→64). README impecable con GIF. Envío en lablab.ai. Stretch: entrada Track 1. |

**Checklist de submission (de des.md):**
- [ ] Título + descripción corta y larga + tags de tecnología
- [ ] Imagen de portada + video de presentación + slides
- [ ] Repo público de GitHub con README
- [ ] URL de app demo funcionando
- [ ] Contenedorizado y ejecutable

---

## 5. El principio rector

**HIPnosis es la única idea donde el patrocinador, el juez y el cliente son la misma entidad
emocional** — alguien que quiere desesperadamente que salir de CUDA sea fácil.

> Cuando el pitch, el producto y la agenda del juez apuntan al mismo lugar, ganas.

---

## 6. Fuentes del research competitivo (7 jul 2026)

- [ZLUDA pierde funding y vuelve a ser hobby (Tom's Hardware)](https://www.tomshardware.com/pc-components/gpu-drivers/cuda-emulator-for-amd-gpus-zluda-loses-funding-with-v6-release-embattled-project-goes-back-to-hobby-status-but-now-includes-32-bit-physx-support)
- [SCALE de Spectral Compute: compilar CUDA para AMD (Phoronix)](https://www.phoronix.com/news/SCALE-CUDA-Apps-For-AMD-GPUs)
- [Claude Code porta CUDA a ROCm en 30 min (Techstrong.ai)](https://techstrong.ai/features/claude-code-ports-nvidia-cuda-to-amd-rocm-in-30-minutes/) · [gist original de la guía de porting](https://gist.github.com/johnnytshi/33d3cec152faf46ff36e91cbf36fd28a)
- [GEAK: agente de kernels Triton de AMD (ROCm Blogs)](https://rocm.blogs.amd.com/software-tools-optimization/triton-kernel-ai/README.html) · [GEAK v2 family](https://rocm.blogs.amd.com/artificial-intelligence/geak-agents-family/README.html) · [paper arXiv](https://arxiv.org/abs/2507.23194)
- [HIPIFY docs oficiales (AMD)](https://rocm.docs.amd.com/projects/HIPIFY/en/latest/)
- Papers de traducción agéntica: [UniPar](https://arxiv.org/pdf/2509.12136) · [LASSI](https://arxiv.org/pdf/2407.01638) · [Sakana: Robust Agentic CUDA Kernel Benchmarking](https://pub.sakana.ai/static/paper.pdf)
- [Recap ACT I con proyectos ganadores (lablab.ai)](https://lablab.ai/ai-hackathons/amd-developer) · [CyberSecQwen-4B, ejemplo de fine-tuning ganador](https://huggingface.co/blog/lablab-ai-amd-developer-hackathon/cybersecqwen-4b)
- [CoreWeave adquiere OpenPipe (sep 2025)](https://www.coreweave.com/news/coreweave-to-acquire-openpipe-leader-in-reinforcement-learning)
- [Coding Agents en GPUs AMD — Aider + DeepSeek en MI300X (ROCm Blogs)](https://rocm.blogs.amd.com/artificial-intelligence/coding-agent/README.html)
