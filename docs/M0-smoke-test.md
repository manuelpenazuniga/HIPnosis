# M0 — Smoke test del droplet MI300X (tarea HUMANA, BLOQUEANTE para GPU real)

> **Quién:** vos (humano), en el droplet MI300X del AMD Developer Cloud.
> **Por qué:** el desarrollo del pipeline avanza 100% en modo `mock` sin GPU (ver `DEVIATIONS.md` D-2).
> M0 valida que el hardware/toolchain real funciona, y produce el trace real que reemplaza al
> `demo-run.jsonl` hand-authored. **Sin M0 verde no se corre el pipeline en modo `real`.**
> **Tiempo estimado (ruta eficiente):** droplet vivo **~45–60 min ≈ $1.5–2** — la mayor parte es
> la descarga de pesos (usá Gemma **12B** y solapá con el smoke; ver §4). El costo corre mientras
> el droplet EXISTE, no mientras lo usás → snapshot + destruir apenas quede verde.
> Referencia: blueprint §12 (M0), §11 (F-01, F-01c, F-02), §1 (topología), §10 (env vars).

---

## 0. Antes de empezar — conseguir el hardware y las credenciales

Esta sección es lo único que **no** está automatizado: crear el droplet MI300X y juntar
las credenciales. Seguila en orden; cada sub-paso explica el *por qué* además del *cómo*.
Al terminar tenés: una MI300X accesible por SSH, y `HF_TOKEN` + `FIREWORKS_API_KEY` listos.

> 💡 **Regla de oro del costo:** el droplet **factura mientras EXISTE, no mientras lo usás**
> (~$1.99/h una MI300X en AMD Developer Cloud). M0 son ~2 h ≈ $4. Si lo dejás toda la noche,
> ~$48. Cuando M0 quede verde: sacá el snapshot (paso 6) y **destruí el droplet**. Lo restaurás
> del snapshot cuando lo necesites.

### 0.1 — Cuenta + créditos en AMD Developer Cloud

**Por qué:** el AMD Developer Cloud es donde vive la MI300X. Corre sobre infraestructura de
DigitalOcean y el registro nuevo da **$100 de crédito (~50 h de una MI300X)**.

1. Entrá a la [página del AMD Developer Cloud](https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html)
   y registrate / iniciá sesión (pide cuenta del **AMD Developer Program**).
2. Verificá que el crédito esté disponible en tu cuenta. La documentación nueva dice que los
   $100 son **instantáneos al registrarte**; si tu cuenta quedó en la aprobación manual de 2–3
   días que menciona el hackathon, esperá esa aprobación o cargá una tarjeta (M0 cuesta ~$5–10).

### 0.2 — Generar tu llave SSH (en tu Mac)

**Por qué:** los GPU Droplets **solo** aceptan login por llave SSH, nunca por password. Generás
un par (privada + pública); la pública se la das al droplet, la privada nunca sale de tu máquina.

```bash
# Si ya tenés ~/.ssh/id_ed25519.pub, saltá este paso.
ssh-keygen -t ed25519 -C "manuelpz.dev@gmail.com"    # Enter a todo (sin passphrase está ok)
cat ~/.ssh/id_ed25519.pub | pbcopy                    # copia la clave PÚBLICA al portapapeles
```

### 0.3 — Crear el droplet MI300X

**Por qué:** es la máquina real donde `hipcc` compila y el kernel corre. La imagen ROCm ya trae
el toolchain, así no instalás nada.

En la consola del cloud → **Create GPU Droplet**:
- **Hardware:** `1x MI300X` — **una sola GPU**, NO el nodo de 8 (costaría 8× = ~$16/h).
- **Image:** la imagen **ROCm Software** (trae ROCm 6.x + Docker preinstalados).
- **SSH key:** "Add SSH key" → pegá la clave pública que copiaste en 0.2.
- Create. Tarda **2–4 min** en pasar de *Creating* a *Active*. Copiá la **IP pública**.

### 0.4 — Conectarte y verificar el entorno

**Por qué:** confirmar que la GPU está visible y que Docker existe ANTES de descargar 70 GB de
imágenes. Si algo de esto falla, el droplet salió mal — destruilo y creá otro (2 min).

```bash
ssh root@<ip-droplet>                    # desde tu Mac

rocminfo | grep -i gfx942                # debe listar la MI300X. Si NO aparece → parar acá.
apt list --installed 2>/dev/null | grep rocm-core   # ROCm 6.x
docker --version                         # Docker viene en la imagen ROCm
docker compose version                   # si falla: apt-get update && apt-get install -y docker-compose-plugin
```

### 0.5 — HuggingFace + licencia de Gemma  ✅ (ya lo tenés)

**Por qué (F-01c):** Gemma 3 27B es un modelo *gated*. Sin aceptar la licencia con tu cuenta,
la descarga de pesos da **401** y vLLM no levanta.

- Confirmá que en [google/gemma-3-27b-it](https://huggingface.co/google/gemma-3-27b-it) la página
  diga **"You have been granted access"** (no el formulario). Ojo: tiene que ser esa variante
  exacta (27b-it), no otra Gemma.
- El token va a ser tu `HF_TOKEN` (uno de **Read**, de https://huggingface.co/settings/tokens).

### 0.6 — Fireworks  ✅ (ya lo tenés)

**Por qué:** el tier remoto (fixes duros) usa Fireworks. Con el bonus de $50 sobra — el pipeline
solo manda a la nube la cola difícil (centavos por run).

- `FIREWORKS_API_KEY` = tu key `fw_...`.
- `REMOTE_LLM_MODEL` = `accounts/fireworks/models/deepseek-v4-pro` (ya validado con curl).

### 0.7 — GITHUB_TOKEN (opcional, saltable para M0)

Solo hace falta si querés que el pipeline abra el **PR** automáticamente. Sin él, entrega branch
+ `.patch` (suficiente para M0). Si lo querés: [github.com/settings/tokens](https://github.com/settings/tokens)
→ "Generate new token (classic)" → scope `repo` → copiá el `ghp_...`.

### 0.8 — Checklist final antes de seguir

- [ ] SSH al droplet funciona (`ssh root@<ip>`), `rocminfo` muestra **gfx942**, `docker compose` responde.
- [ ] `HF_TOKEN` a mano y la licencia de Gemma **aceptada** (0.5).
- [ ] `FIREWORKS_API_KEY` + `REMOTE_LLM_MODEL` a mano (0.6).
- [ ] (Opcional) `GITHUB_TOKEN`.
- [ ] Anotá recordar: **snapshot + destruir el droplet** al terminar M0 (regla de costo).

Cuando todos estén ✅, seguí con el paso 1.

---

## 1. Clonar el repo en el droplet

```bash
# En el droplet (por SSH). Es el repo público de la submission.
git clone https://github.com/manuelpenazuniga/HIPnosis.git
cd HIPnosis
```

---

## 2. Smoke test del HARDWARE y TOOLCHAIN (blueprint §11.1)

Corré estos comandos **en el droplet** (no en un contenedor todavía). Cada uno debe pasar:

```bash
# 2.1 — La GPU MI300X está visible y es gfx942
rocminfo | grep -i gfx942
# Esperado: al menos una línea "Name: gfx942". Si NO aparece → la GPU no está pasada al entorno; parar acá.

# 2.2 — hipcc compila y ejecuta un kernel HIP mínimo (saxpy)
cat > /tmp/saxpy.cpp <<'EOF'
#include <hip/hip_runtime.h>
#include <cstdio>
__global__ void saxpy(int n, float a, float* x, float* y){
  int i = blockIdx.x*blockDim.x + threadIdx.x;
  if (i < n) y[i] = a*x[i] + y[i];
}
int main(){
  const int n=1<<20; size_t sz=n*sizeof(float);
  float *x,*y; hipMallocManaged(&x,sz); hipMallocManaged(&y,sz);
  for(int i=0;i<n;i++){x[i]=1.0f;y[i]=2.0f;}
  saxpy<<<(n+255)/256,256>>>(n,3.0f,x,y);
  hipDeviceSynchronize();
  printf("y[0]=%.1f (esperado 5.0)\n", y[0]);
  return (y[0]==5.0f)?0:1;
}
EOF
hipcc --offload-arch=gfx942 /tmp/saxpy.cpp -o /tmp/saxpy && /tmp/saxpy
# Esperado: "y[0]=5.0 (esperado 5.0)" y exit 0.

# 2.3 — hipify-perl presente (⚠️ F-02: usamos hipify-PERL, NUNCA hipify-clang)
which hipify-perl && hipify-perl --version 2>/dev/null | head -1
# Esperado: una ruta (p.ej. /opt/rocm/bin/hipify-perl). Si falta: `apt-get install hipify-clang` NO —
# hipify-perl viene con rocm; si no está, instalá el paquete rocm que lo trae. hipify-clang NO se usa.

# 2.4 — HeCBench clonado (corpus de repos demo)
git clone --depth 1 https://github.com/zjin-lcf/HeCBench.git ../HeCBench
ls ../HeCBench/src/bsw-cuda ../HeCBench/src/softmax-cuda
# Esperado: los dos directorios existen (son los repos demo, ver ESTADO.md T0.5).
```

✅ **Si 2.1–2.4 pasan: el hardware está listo.** Si algo falla, es un problema de infra del droplet
(no del código): resolvelo o abrí ticket con AMD Developer Cloud antes de seguir.

---

## 3. Configurar los secretos (env vars — blueprint §10)

```bash
cp orchestrator/.env.example orchestrator/.env
# Editá orchestrator/.env y completá AL MENOS:
#   HF_TOKEN=hf_xxxxxxxx           # tu token de HuggingFace (Gemma es gated — F-01c)
#   ORACLE_MODE=real
#   GPU_ARCH=gfx942
# Opcionales:
#   FIREWORKS_API_KEY=fw_xxxx      # fixer remoto (si no, el pipeline usa solo el local)
#   REMOTE_LLM_MODEL=<id exacto>   # verificar en fireworks.ai el id del modelo de código
#   GITHUB_TOKEN=ghp_xxxx          # para generar PR (opcional; sin él, branch + format-patch)
```
⚠️ **NUNCA** commitees `orchestrator/.env` (está en `.gitignore`). El `.env.example` sí se versiona.

---

## 4. Levantar el stack REAL con docker compose (perfil gpu)

> ⏱️ **RUTA EFICIENTE (pagás vos — el droplet factura mientras existe).** Dos decisiones
> que recortan el mayor sumidero de tiempo (la descarga de pesos):
>
> 1. **Usá Gemma 3 12B, no 27B.** Baja **~24 GB en vez de ~54 GB** (≈15–20 min menos), usa
>    menos VRAM (menos riesgo de F-01), y mantiene la historia "Gemma local, $0 API" (sigue
>    siendo Gemma → sigue contando para el premio Gemma). En `docker-compose.yml`, servicio
>    `vllm`: `--model google/gemma-3-12b-it`; y `LOCAL_LLM_MODEL=google/gemma-3-12b-it` en `.env`.
> 2. **Solapá la descarga con el smoke de hardware.** Arrancá el stack en background (`up -d`)
>    y mientras baja los pesos corré el paso 2 (rocminfo, hipcc saxpy, hipify-perl) — el reloj
>    de la GPU corre igual, así que no lo desperdicies mirando una barra de progreso.
>
> **Solo corré bsw** (paso 5), no los 3 repos: un run verde grabado alcanza. Y apenas esté
> verde: capturas + `record_fixture.sh` + **snapshot + DESTRUIR** (secciones 6 y 6.5).
> Objetivo realista: **droplet vivo ~45–60 min ≈ $1.5–2**.

```bash
# HF_TOKEN ya NO se exporta a mano: el servicio vllm lee orchestrator/.env
# directamente (env_file, arreglado post-audit P0.11). Solo asegurate de que
# el paso 3 dejó HF_TOKEN= completo en orchestrator/.env.

docker compose --profile gpu up -d --build   # -d = background: dejalo bajando y seguí con el paso 2
# Esto levanta 2 servicios:
#   - vllm  : imagen oficial rocm/vllm sirviendo Gemma 3 12B IT en :8000 (⚠️ F-01: NO compilar vLLM)
#   - orchestrator : FastAPI + pipeline en :8080
```

### 4.1 — Verificar que vLLM sirve Gemma (⚠️ F-01, el escalón más frágil)

```bash
# La descarga de pesos es lo más lento. Mientras baja, andá haciendo el paso 2
# (smoke de hardware) en otra terminal SSH — solapás y no perdés tiempo de GPU.
docker compose --profile gpu logs -f vllm    # Ctrl-C cuando veas "Application startup complete"

# Probá un chat (ajustá el model si usaste 27B):
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"google/gemma-3-12b-it","messages":[{"role":"user","content":"di OK"}],"max_tokens":5}'
# Esperado: un JSON con una respuesta. Si funciona → F-01 superado.
```

⚠️ **Cronómetro DURO (pagás vos): si vLLM no sirve en ~20–25 min, cortá y andá al fallback Fireworks.**
No pelees con vLLM una hora — eso es plata. Cadena de fallbacks EN ORDEN (blueprint §11 F-01):
1. Reintentar con `--max-model-len 32768` (ya está en el compose).
2. Si empezaste con 27B, bajá a **12B** (`--model google/gemma-3-12b-it` + `LOCAL_LLM_MODEL`).
3. **Fireworks para TODO el tier LLM** (el corte de tiempo): en `orchestrator/.env` poné
   `LOCAL_LLM_BASE_URL=https://api.fireworks.ai/inference/v1` y
   `LOCAL_LLM_MODEL=accounts/fireworks/models/deepseek-v4-pro`, y levantá **solo el orquestador**
   sin vLLM: `docker compose --profile gpu up -d --build --no-deps orchestrator`. Se pierde el
   "$0 local" del run grabado (la fix de wave64 va a la nube, centavos), pero seguís teniendo lo
   que importa: compile REAL en MI300X + paridad numérica + wave64. *El fallback se decide con
   cronómetro, no con orgullo.*

### 4.2 — Verificar el orquestador

```bash
curl -s http://localhost:8080/healthz          # {"ok":true}
# Abrí el dashboard en tu browser (túnel SSH si hace falta):  http://<ip-droplet>:8080/
```

---

## 5. Correr el pipeline REAL contra bsw-cuda (solo ese)

**Antes de disparar el run:** abrí un túnel SSH para ver (y GRABAR) el dashboard desde tu Mac.
Es el momento estrella — el badge va a decir **LIVE · MI300X**, no "synthetic demo".

```bash
# En tu Mac, en otra terminal — túnel al dashboard del droplet:
ssh -L 8080:localhost:8080 root@<ip-droplet>
# Ahora abrí http://localhost:8080/ en tu browser. Empezá a grabar pantalla (ver 6.5).
```

```bash
# En el droplet: disparar el run real contra el repo demo STANDALONE (clonable directo,
# con su hipnosis.yaml y su test-data; NO el HeCBench completo — F-03/P0.10).
curl -s -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/manuelpenazuniga/bsw-cuda"}'
# Guardá el run_id que devuelve. El endpoint solo acepta repos de REPO_ALLOWLIST (ya en compose).
# (softmax-cuda y scan-cuda existen, pero para M0 eficiente con bsw ALCANZA — no los corras.)
```

Seguí el run en el dashboard (o por API: `curl "http://localhost:8080/runs/<run_id>/events?after=-1"`).

✅ **M0 verde = el run llega a `DONE` con `verify: PASS`** (bsw-cuda compila en ROCm y su golden
de Smith-Waterman pasa). Los contadores (fixes local/remoto/deterministic) quedan poblados.

---

## 6. Grabar el trace real + capturas (reemplaza al demo-run hand-authored)

```bash
# En el droplet: un solo comando graba trace + certificado + diff + attestation del run
# real a fixtures/ (reemplaza el demo sintético; el badge pasa solo a 'recorded run'):
scripts/record_fixture.sh <run_id>
```

Después, **traé los fixtures a tu Mac y commiteá desde ahí** (no comitees en el droplet efímero):

```bash
# En tu Mac:
scp -r root@<ip-droplet>:HIPnosis/fixtures/demo-run.jsonl \
       root@<ip-droplet>:HIPnosis/fixtures/demo-certificate.md \
       root@<ip-droplet>:HIPnosis/fixtures/demo-diff.txt \
       root@<ip-droplet>:HIPnosis/fixtures/demo-attestation.jsonl  ./fixtures/
git add fixtures/ && git commit -m "chore(fixtures): trace REAL de M0 (bsw-cuda verde en MI300X)" && git push
```

📸 **Snapshot del droplet ANTES de destruir** (seguro F-14 + te deja re-correr sin re-descargar):
consola del cloud → tu droplet → **Take snapshot**. Cuando termine, **Destroy** el droplet.

---

## 6.5 Qué grabar / capturar durante M0 (hacelo con el droplet VIVO)

El artefacto obligatorio lo produce `record_fixture.sh` (arriba). Pero mientras la GPU está
viva —y solo mientras lo está— capturá esto para el **video y la submission**. Es material que
prueba silicio real y no lo podés volver a sacar sin re-encender el droplet ($$):

**Obligatorio (prueba de MI300X real):**
- [ ] Salida de `rocminfo | grep -i gfx942` (copiá el texto o screenshot) — prueba de la GPU.
- [ ] Salida del `hipcc saxpy` del paso 2 (`y[0]=5.0`) — prueba del toolchain.
- [ ] Los 4 fixtures que graba `record_fixture.sh` (ya cubiertos en la sección 6).

**Para el video (la escena "GPU real" del guion, `docs/video-script.md`):**
- [ ] **Screen-recording del dashboard EN VIVO durante el run** (vía el túnel SSH del paso 5):
      el badge **LIVE · MI300X**, el burndown drenando, el panel wave64, el veredicto **PASS**,
      y el **Port Passport con digests reales** (commits reales, gfx942). Esto convierte el
      segmento "GPU real" del video de apéndice en footage de verdad.
- [ ] Screenshots del estado final: dashboard con badge LIVE, el certificado, y el Passport
      (mostrando source/final commit reales + `gfx942`).
- [ ] (Opcional) La terminal del run: `POST /runs` → los eventos drenando por API.

**Guardalo todo en tu Mac** (scp / grabación local) **antes de destruir el droplet.**

> 🎬 Tip: grabá la pantalla del dashboard en 1080p desde que disparás el `POST /runs`. Un solo
> take de ~1–2 min del run real vale más que cualquier tarjeta de marketing — es la evidencia
> de que HIPnosis corre en la MI300X, no un terminal scripteado.

---

## 7. Reportar el resultado

Avisá al equipo (o dejá una línea en `ESTADO.md`):
```
M0: DONE | gfx942 ✓, hipcc saxpy ✓, hipify-perl ✓, vllm+Gemma ✓ (o fallback N), bsw-cuda run real: PASS | trace grabado
```
Si algún paso falló y no se pudo resolver en su ventana de tiempo, anotá cuál y seguimos en modo
`mock`+`replay` (la submission ejecutable NO depende de M0 — ese es el punto del perfil replay).

---

## Resumen ultra-corto — ruta eficiente (droplet vivo mínimo)
```bash
# 0. TODO listo antes de crear el droplet (§0): SSH key, HF_TOKEN, Fireworks, licencia Gemma.
# 1. crear droplet 1x MI300X (imagen ROCm) → ssh root@<ip> → git clone .../HIPnosis && cd HIPnosis
cp orchestrator/.env.example orchestrator/.env && vim orchestrator/.env   # HF_TOKEN + Fireworks
# usar Gemma 12B (mitad de descarga): editar docker-compose.yml vllm --model google/gemma-3-12b-it
docker compose --profile gpu up -d --build               # 2. arrancar EN BACKGROUND (deja bajando)
# 3. MIENTRAS baja, en paralelo: smoke de hardware
rocminfo | grep gfx942 && hipcc --offload-arch=gfx942 saxpy.cpp -o s && ./s && which hipify-perl
curl localhost:8000/v1/chat/completions -d '{...}'       # 4. Gemma vivo (F-01; cronómetro 20min→Fireworks)
# 5. en tu Mac: ssh -L 8080:localhost:8080 root@<ip>  → abrir dashboard + EMPEZAR A GRABAR
curl -X POST localhost:8080/runs -d '{"repo_url":"https://github.com/manuelpenazuniga/bsw-cuda"}'  # 6. run → PASS
scripts/record_fixture.sh <run_id>                       # 7. grabar artefactos reales
# 8. capturas (rocminfo, dashboard LIVE, cert, passport) → scp a tu Mac (§6.5)
# 9. SNAPSHOT + DESTROY el droplet (cortás el costo)
```
