# M0 — Smoke test del droplet MI300X (tarea HUMANA, BLOQUEANTE para GPU real)

> **Quién:** vos (humano), en el droplet MI300X del AMD Developer Cloud.
> **Por qué:** el desarrollo del pipeline avanza 100% en modo `mock` sin GPU (ver `DEVIATIONS.md` D-2).
> M0 valida que el hardware/toolchain real funciona, y produce el trace real que reemplaza al
> `demo-run.jsonl` hand-authored. **Sin M0 verde no se corre el pipeline en modo `real`.**
> **Tiempo estimado:** ~2 h (la mayor parte es esperar descargas de imágenes/pesos).
> Referencia: blueprint §12 (M0), §11 (F-01, F-01c, F-02), §1 (topología), §10 (env vars).

---

## 0. Antes de empezar (checklist de acceso)

- [ ] Tenés acceso SSH al droplet MI300X (`ssh usuario@<ip-droplet>`).
- [ ] El droplet tiene ROCm 6.x y Docker instalados (la imagen del AMD Developer Cloud suele traerlos).
- [ ] Tenés una cuenta de HuggingFace y **aceptaste la licencia de Gemma** en
      https://huggingface.co/google/gemma-3-27b-it (⚠️ **F-01c**: sin esto la descarga da 401).
      Generá un token de lectura en https://huggingface.co/settings/tokens → será tu `HF_TOKEN`.
- [ ] (Opcional) Una API key de Fireworks (https://fireworks.ai) para el fixer remoto → `FIREWORKS_API_KEY`.
- [ ] (Opcional) Un `GITHUB_TOKEN` si querés que el pipeline genere PRs.

---

## 1. Clonar el repo en el droplet

```bash
git clone https://github.com/<tu-usuario>/HIPnosis.git   # el repo público de la submission
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

```bash
# Exportá HF_TOKEN para el servicio vllm (lo lee de tu shell)
export HF_TOKEN=$(grep '^HF_TOKEN=' orchestrator/.env | cut -d= -f2)

docker compose --profile gpu up -d --build
# Esto levanta 2 servicios:
#   - vllm  : imagen oficial rocm/vllm sirviendo Gemma 3 27B IT en :8000 (⚠️ F-01: NO compilar vLLM)
#   - orchestrator : FastAPI + pipeline en :8080
```

### 4.1 — Verificar que vLLM sirve Gemma (⚠️ F-01, el escalón más frágil)

```bash
# Esperá 3-10 min a que baje los pesos (la 1ª vez). Seguí el progreso:
docker compose --profile gpu logs -f vllm    # Ctrl-C cuando veas "Application startup complete"

# Probá un chat:
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"google/gemma-3-27b-it","messages":[{"role":"user","content":"di OK"}],"max_tokens":5}'
# Esperado: un JSON con una respuesta. Si funciona → F-01 superado.
```

⚠️ **Si vLLM crashea/cuelga (F-01), cadena de fallbacks EN ORDEN, máx 45 min por escalón** (blueprint §11 F-01):
1. Reintentar con `--max-model-len 32768` (ya está en el compose).
2. Bajar a **Gemma 3 12B**: en `docker-compose.yml`, servicio `vllm`, cambiá `--model google/gemma-3-12b-it`
   y `LOCAL_LLM_MODEL=google/gemma-3-12b-it` en `.env`.
3. llama.cpp-ROCm con un GGUF de Gemma.
4. **Gemma vía Fireworks**: en `.env`, apuntá `LOCAL_LLM_BASE_URL` al endpoint de Fireworks y usá
   `FIREWORKS_API_KEY`. Se pierde el "0 tokens locales" pero el producto sobrevive.
   *La decisión de fallback se toma con cronómetro, no con orgullo.*

### 4.2 — Verificar el orquestador

```bash
curl -s http://localhost:8080/healthz          # {"ok":true}
# Abrí el dashboard en tu browser (túnel SSH si hace falta):  http://<ip-droplet>:8080/
```

---

## 5. Correr el pipeline REAL contra el primer repo demo (bsw-cuda)

```bash
# Disparar un run real. El pipeline clona bsw-cuda, hipifica, compila, parchea en loop, verifica.
curl -s -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/zjin-lcf/HeCBench"}'
# (el repo/subdir demo exacto lo maneja el pipeline según el manifiesto; ver hipnosis.yaml)

# Seguí el run EN VIVO en el dashboard, o por API:
#   curl "http://localhost:8080/runs/<run_id>/events?after=-1"
```

✅ **M0 verde = el run llega a `DONE` con `verify: PASS`** (bsw-cuda compila en ROCm y su self-check
interno pasa). Los contadores (fixes local/remoto/deterministic) quedan poblados.

---

## 6. Grabar el trace real (reemplaza al demo-run hand-authored)

```bash
# Una vez que un run real quede verde, grabá su trace para el modo replay de los jueces:
cp workspaces/<run_id>/trace.jsonl fixtures/demo-run.jsonl
git add fixtures/demo-run.jsonl
git commit -m "chore(fixtures): trace real de M0 (bsw-cuda verde en MI300X) reemplaza el hand-authored"
git push
# Ahora el perfil replay muestra una corrida REAL, no la simulada.
```

📸 **Sacá un snapshot/imagen del droplet ahora** (tras M0 verde) — es tu seguro contra F-14
(si el droplet muere a mitad de semana, restaurás desde acá).

---

## 7. Reportar el resultado

Avisá al equipo (o dejá una línea en `ESTADO.md`):
```
M0: DONE | gfx942 ✓, hipcc saxpy ✓, hipify-perl ✓, vllm+Gemma ✓ (o fallback N), bsw-cuda run real: PASS | trace grabado
```
Si algún paso falló y no se pudo resolver en su ventana de tiempo, anotá cuál y seguimos en modo
`mock`+`replay` (la submission ejecutable NO depende de M0 — ese es el punto del perfil replay).

---

## Resumen ultra-corto (si ya sabés lo que hacés)
```bash
rocminfo | grep gfx942                                   # 1. GPU
hipcc --offload-arch=gfx942 saxpy.cpp -o s && ./s        # 2. toolchain
which hipify-perl                                        # 3. hipify (perl!)
cp orchestrator/.env.example orchestrator/.env && vim orchestrator/.env   # 4. HF_TOKEN
export HF_TOKEN=... && docker compose --profile gpu up -d --build          # 5. stack
curl localhost:8000/v1/chat/completions -d '{...}'       # 6. Gemma vivo (F-01)
curl -X POST localhost:8080/runs -d '{"repo_url":"..."}' # 7. run real → PASS
cp workspaces/<id>/trace.jsonl fixtures/demo-run.jsonl   # 8. grabar trace real
```
