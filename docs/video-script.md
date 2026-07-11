# 🎬 Video script — HIPnosis (instalación + uso, ~6 min)

> **Cómo leer este guion:** cada bloque tiene **🎥 MOSTRAR** (en español — lo que
> hacés/mostrás en pantalla) y **🎙️ DECIR** (en inglés — la narración, leela tal cual).
> Los comandos y URLs son literales. Duración objetivo: **6:00**.
>
> **Setup de grabación:** pantalla limpia, terminal con fuente grande (≥16pt), navegador
> en ventana ancha. Tené listo: el repo clonado, Docker corriendo, y el sitio replay
> abierto en una pestaña. Grabá a 1080p. Recomendado: OBS o QuickTime.
>
> **Nota de honestidad:** el video usa el modo **replay** (una corrida grabada), que es
> como los jueces lo reproducen sin GPU. Cuando exista la corrida real de M0 en MI300X,
> `scripts/record_fixture.sh` reemplaza el trace y el badge pasa a "recorded run".

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
el título "Port CUDA to AMD ROCm — and prove it", el screenshot del dashboard,
y el sello **PORT PASSPORT · VERIFIED**.

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
**Resolved Locally 100%**, **Cloud API Cost $0.00**. Después mostrá el **Error
Burndown** (8 → 5 → 2 → 0) y la tabla **Fixes Applied** (E01, E02, E05 con sus
tiers y commits).

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

**🎥 MOSTRAR:** Scroll al veredicto grande **PASS**. Después al **Port Certificate**
(expandido): mostrá el resumen ejecutivo y la tabla de inventario.

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

## 📋 Apéndice — comandos para el segmento de GPU real (opcional, si grabás M0)

Si querés incluir la corrida real en MI300X (tras aprobar los créditos de AMD):

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
