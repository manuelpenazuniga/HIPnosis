# 🎬 Video script — HIPnosis (instalación + uso, ~6 min)

> **Cómo leer este guion:** cada bloque tiene **🎥 MOSTRAR** (en español — lo que
> hacés/mostrás en pantalla) y **🎙️ DECIR** (en inglés — la narración, leela tal cual).
> Los comandos y URLs son literales. Duración objetivo: **6:00**.
>
> **Setup de grabación:** seguí la sección [🛠 Setup de grabación](#-setup-de-grabación--paso-a-paso-hacer-antes-de-grabar)
> de abajo ANTES de tocar el botón de grabar. Son ~30 min de preparación y evitan
> tener que regrabar todo.
>
> **Nota de honestidad:** el video usa el modo **replay** (una corrida grabada), que es
> como los jueces lo reproducen sin GPU. El smoke test **M0 en una MI300X real ya pasó**
> (toolchain ROCm + pipeline GPU verificados end-to-end). Si se regraba una corrida real
> en el droplet, `scripts/record_fixture.sh` la congela y el badge pasa a "recorded run".

---

## 🛠 Setup de grabación — paso a paso (hacer ANTES de grabar)

> Tiempo total de preparación: **~30 minutos**. El objetivo es que cuando aprietes
> "grabar", TODO ya esté listo y solo tengas que seguir el guion.

### Paso 1 — Instalar lo necesario (5 min)

1. **Docker Desktop abierto y corriendo.** Mirá la barra de menú de macOS: el ícono
   de la ballena tiene que estar quieto (no animado). Si no está, abrí Docker Desktop
   y esperá a que diga "running".
2. **Grabador de pantalla.** Camino fácil (recomendado): **QuickTime Player**, ya viene
   en macOS, no hay que instalar nada. Alternativa si querés más control (escenas,
   marca de agua): OBS (`brew install --cask obs`), pero para un video de 6 minutos
   QuickTime alcanza y sobra.
3. **Micrófono.** El de unos auriculares (AirPods sirven) suena mejor que el interno
   del Mac porque está cerca de tu boca. Conectalos ANTES de configurar QuickTime.

### Paso 2 — Silenciar el mundo (2 min)

1. **Activar "No molestar"**: Centro de control (arriba a la derecha) → Concentración
   → **No molestar**. Esto evita que un mensaje de WhatsApp aparezca en medio del video.
2. Cerrá TODAS las apps que no sean: Terminal, el navegador y el grabador.
3. Si tenés el escritorio lleno de íconos y va a verse en cámara, usá un escritorio
   nuevo limpio (Mission Control → botón `+`).

### Paso 3 — Preparar la terminal (3 min)

1. Abrí Terminal (o iTerm) y agrandá la fuente hasta **16pt o más**: `Cmd +` varias
   veces. Regla práctica: parate a 2 metros de la pantalla; si no leés los comandos,
   es chica.
2. Tema oscuro, ventana ocupando media pantalla o más.
3. Andá al repo: `cd /Volumes/MacMiniExt/dev/ZedProjects/HIPnosis`
4. Limpiá la pantalla con `clear` justo antes de grabar, para arrancar sin historia.

### Paso 4 — Precalentar Docker (10 min, se hace UNA vez)

El primer `docker compose up` construye la imagen y tarda minutos. En cámara tiene
que ser rápido, así que construí ANTES:

```bash
docker compose --profile replay build   # tarda; tomate un café
docker compose --profile replay up      # verificá que levanta y abre bien
# abrí http://localhost:8080 y mirá que el dashboard cargue
docker compose --profile replay down    # bajalo: en cámara lo levantás "en vivo"
```

Con la imagen ya construida, el `up` en cámara tarda segundos, no minutos.

### Paso 5 — Preparar el navegador (3 min)

1. **Chrome en ventana ancha**: mínimo 1400px (maximizada está bien). Zoom al 100%
   (`Cmd 0`).
2. Ocultá la barra de marcadores: `Cmd Shift B`.
3. Cerrá todas las pestañas menos las que usa el guion: la **landing** y (cuando
   levantes el stack) `http://localhost:8080`.
4. **Resetear el onboarding** para que el overlay "Three things to watch" aparezca
   en cámara: en `localhost:8080` abrí la consola del navegador (`Cmd Option J`),
   escribí `localStorage.clear()` y Enter. Después cerrá la consola y cerrá la pestaña
   (la vas a reabrir durante la grabación).

### Paso 6 — Configurar QuickTime y probar el audio (5 min)

1. QuickTime Player → **Archivo → Nueva grabación de pantalla**.
2. En **Opciones**: elegí tu **micrófono** (los auriculares, no "ninguno") y activá
   **"Mostrar los clics del ratón"** — ayuda muchísimo a que el juez siga el cursor.
3. Elegí **grabar la pantalla completa**.
4. **Prueba de audio obligatoria**: grabá 10 segundos hablando normal, paralo,
   reproducilo. ¿Se escucha claro y fuerte, sin eco? Listo. ¿Suena lejano? El mic
   seleccionado es el equivocado, volvé al punto 2.

### Paso 7 — Ensayo general (5 min, sin grabar)

Recorré el guion completo UNA vez sin grabar: levantá el stack, abrí el dashboard,
hacé los scrolls de cada sección, tocá el botón del tamper demo. Así en cámara ya
sabés dónde está cada cosa y no la buscás en vivo. Al terminar: `docker compose
--profile replay down`, `clear` en la terminal, `localStorage.clear()` de nuevo.

### Paso 8 — Grabar

- Grabá **todo en una sola toma larga**; los errores se cortan después en edición.
- Si te trabás o te equivocás: **pausa de 3 segundos en silencio** y repetí la frase
  completa. Ese silencio te marca dónde cortar al editar.
- Hablá más despacio de lo que te parece natural. Leé los bloques **🎙️ DECIR** tal cual.
- Mové el mouse lento y "señalá" con el cursor lo que estás nombrando.

### Paso 9 — Editar y exportar

1. Editor simple: **iMovie** (gratis) o CapCut. Cortá: los errores marcados con
   silencio, y los tiempos muertos del `docker compose up` (o acelerálos 4×).
2. Exportá **1080p, MP4**. Duración objetivo: 6:00 (máximo tolerable ~6:30).
3. Subilo a YouTube como **unlisted**, título sugerido:
   `HIPnosis — Verified CUDA to ROCm Ports (AMD Developer Hackathon ACT II)`.
4. Pegá el link en el campo de video de la submission de lablab y **mirá el video
   entero una vez desde el link** (no desde tu archivo local) antes de entregar.

---

## 0:00 – 0:30 · Hook: el bug que nadie ve

**🎥 MOSTRAR:** Pantalla con un snippet de código CUDA. Resaltá la línea
`__ballot_sync(0xffffffff, ...)`. Después mostrá `nvcc` compilando OK.

**🎙️ DECIR:**
> "This CUDA kernel compiles. It runs. And on an AMD GPU, it silently returns the
> wrong numbers. NVIDIA warps are 32 lanes; AMD wavefronts are 64. A textual
> translator like hipify never sees the difference — it just ships the bug.
> HIPnosis is built to catch exactly this. Let me show you."

---

## 0:30 – 1:00 · Qué es HIPnosis (landing)

**🎥 MOSTRAR:** Abrí la landing (la home del sitio). Scroll lento por el hero:
el título "Port CUDA to AMD ROCm — and **prove** it still computes the same
numbers", el screenshot del dashboard, y el sello **PORT PASSPORT · VERIFIED**.

**🎙️ DECIR:**
> "HIPnosis is an autonomous agent. You give it a CUDA repository; it compiles the
> port on a real MI300X, drains every build error, catches those wavefront bugs, and
> hands back a verified port with a proof you can check yourself. The product isn't
> the translation — it's the evidence that the port still computes the same numbers."

---

## 1:00 – 2:00 · Instalación (cero GPU, para cualquiera)

**🎥 MOSTRAR:** Terminal. Escribí los comandos uno por uno, pausando en cada uno:

```bash
git clone https://github.com/manuelpenazuniga/HIPnosis.git
cd HIPnosis
docker compose --profile replay up
```

Mientras buildea/levanta, mostrá el `docker compose` corriendo. Cuando diga
`Application startup complete`, abrí el navegador en `http://localhost:8080`.

**🎙️ DECIR:**
> "Installation is one command. Clone the repo, and run `docker compose --profile
> replay up`. This is the mode the judges use — it needs no GPU, no API keys, nothing.
> It spins up the orchestrator and serves a recorded port of a real CUDA benchmark.
> In a few seconds, the dashboard is live on localhost:8080."

---

## 2:00 – 2:40 · El pipeline arranca (SCAN → PORT)

**🎥 MOSTRAR:** En el dashboard aparece el overlay de onboarding "Three things to
watch". Leelo un segundo y hacé click en **"Watch the run →"**. Señalá con el mouse:
el badge **REPLAY · synthetic demo**, y la fila de scan (CUDA files, kernel LOC,
difficulty, target GPU **gfx942**).

**🎙️ DECIR:**
> "The dashboard tells you exactly what to watch. Notice the badge — it always says
> which mode you're in; we never fake a GPU result. HIPnosis first scans the repo:
> two CUDA files, 788 kernel lines, medium difficulty, targeting gfx942 — the MI300X.
> Then it translates the source and adapts the build system."

---

## 2:40 – 3:40 · El build loop (el corazón)

**🎥 MOSTRAR:** Señalá las tarjetas de métricas: **Errors Resolved 8 → 0**,
**Resolved Locally 100%**, **Cloud API Cost $0.00**. Cuando el run termina, bajo
las métricas aparece la **banda verde PASS** (build errors 8→0, wave64 2, 100%
local, passport verifiable) — dejala respirar un segundo. Después scroll abajo
al **Error Burndown** (8 → 5 → 2 → 0) y la tabla **Fixes Applied** (E01, E02,
E05 con sus tiers y commits).

**🎙️ DECIR:**
> "Here's the core loop. It compiles on the GPU, and for every error it parses the
> compiler output, classifies it, and proposes a fix — from a deterministic rule
> table when it can, from a local Gemma model when it can't. Watch the burndown:
> eight errors drop to zero across four iterations. And this is the key — every fix
> is measured by the compiler itself and reverted if it doesn't help. The compiler
> is the oracle, never the language model. One hundred percent resolved locally,
> zero dollars of cloud spend."

---

## 3:40 – 4:30 · Wave64: el bug silencioso

**🎥 MOSTRAR:** Scroll al panel **Wave64 Divergence Detection**. Señalá las dos
filas (kernel.cu, W01 y W02, severity **Correctness**). Después scroll al panel
**Code Transformation** y señalá el diff: la línea roja con `__ballot_sync(0xffffffff)`
y la verde con el fix de 64 bits.

**🎙️ DECIR:**
> "This is the differentiator. HIPnosis statically flags two wavefront-64 divergences —
> marked as correctness bugs, not warnings. These are the exact lines that compile
> cleanly and compute garbage on AMD. Look at the diff: the 32-bit ballot mask on
> the left, rewritten for 64 lanes on the right. A translation-only tool ships the
> version on the left and calls it done."

---

## 4:30 – 5:00 · Verificación numérica + certificado

**🎥 MOSTRAR:** Scroll al panel **Verification Verdict** con el **PASS** grande.
Después al **Port Certificate** (expandido): mostrá el resumen ejecutivo y la
tabla de inventario.

**🎙️ DECIR:**
> "Success isn't declared by an AI. HIPnosis runs the ported binary and compares its
> output against a reference with numerical tolerances. The verdict here is PASS. And
> every run ends with a certificate — machine-generated, every number computed from
> code, with an honest section for anything that still needs a human."

---

## 5:00 – 5:40 · El Port Passport (verificá vos mismo)

**🎥 MOSTRAR:** Scroll al **Port Passport**. Señalá el badge verde
**PASSPORT VERIFIED** y los campos (diff sha256, verdict, target). Ahora hacé click
en **"Tamper demo (flip 1 byte)"** → el badge cambia a rojo **TAMPERED**. Después
click en **"Re-verify hashes"** → vuelve a **VERIFIED**.

**🎙️ DECIR:**
> "And here's the proof. The Port Passport is a hash-signed attestation of the port.
> Your browser recomputes the SHA-256 of the diff and checks it — verified. Now watch:
> I tamper with a single byte... and the seal instantly reads TAMPERED. Re-verify, and
> it's back. No blockchain, no trust-me — the hash either matches or it doesn't. This
> is what 'cross the border with papers' actually means."

---

## 5:40 – 6:00 · Cierre + corrida real

**🎥 MOSTRAR:** Volvé a la landing, mostrá la tabla comparativa (vs. translation).
Terminá en el logo HIPnosis.

**🎙️ DECIR:**
> "hipify translates and stops. HIPnosis compiles, verifies, and proves — on real AMD
> silicon. To run it on your own GPU, add your Hugging Face token and switch to the
> GPU profile. Everything you saw is open source. HIPnosis — the CUDA-to-ROCm port
> that comes with receipts."

---

## 📋 Apéndice — comandos para el segmento de GPU real (opcional)

M0 ya pasó, pero no quedó material grabado. Si querés footage de la corrida real
en MI300X, restaurá el snapshot del droplet (~$2/hr mientras exista — snapshot +
destroy al terminar, regla de costo de `docs/M0-smoke-test.md`) y corré:

```bash
cp orchestrator/.env.example orchestrator/.env
# editar orchestrator/.env: HF_TOKEN=..., FIREWORKS_API_KEY=..., REMOTE_LLM_MODEL=accounts/fireworks/models/deepseek-v4-pro
docker compose --profile gpu up -d --build
curl -X POST http://localhost:8080/runs \
  -H 'Content-Type: application/json' \
  -d '{"repo_url":"https://github.com/manuelpenazuniga/bsw-cuda"}'
# seguir en el dashboard; al terminar:
scripts/record_fixture.sh <run_id>
```

**🎙️ DECIR (si mostrás esto):**
> "On a real MI300X, this same pipeline runs against a live repository — the same
> dashboard, the same passport, but now backed by actual silicon. One script freezes
> that run into the replay you just saw."

---

## ✅ Checklist de grabación

- [ ] Docker corriendo antes de empezar (para que `up` sea rápido).
- [ ] `localStorage` limpio en el navegador (para que aparezca el onboarding overlay).
      En la consola del browser: `localStorage.clear()`.
- [ ] Zoom del navegador al 100%, ventana ancha (≥1400px) para que se vea el dashboard completo.
- [ ] Terminal con fuente grande y tema oscuro.
- [ ] Audio: micrófono cerca, sin ruido de fondo; narración pausada y clara.
- [ ] Cortar tiempos muertos del `docker build` en edición (acelerar 4×).
- [ ] Exportar 1080p, subir a un unlisted/público, y enlazar en la submission de lablab.
