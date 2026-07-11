# Deploy del demo público (Vercel)

El sitio público es el **demo/replay estático**: la landing (`index.html`) + el
dashboard (`dashboard/`) reproduciendo un run grabado desde los fixtures. **No**
incluye el backend real — el orquestador Python + GPU corren en la MI300X, no en
serverless (sería deshonesto y técnicamente imposible: SQLite, threads, `hipcc`
por subprocess). El badge del dashboard siempre dice el modo (`synthetic demo`).

Qué se deploya (ver `.vercelignore`): `index.html`, `dashboard/`, `fixtures/`.
Todo lo demás (orchestrator, docs, scripts) queda fuera del deploy.

## Opción A — GitHub integration (recomendada)

Auto-deploy en cada push, con preview URL por commit:

1. [vercel.com/new](https://vercel.com/new) → Import el repo `manuelpenazuniga/HIPnosis`.
2. Framework preset: **Other**. Root directory: **`./`** (raíz). Build command:
   **vacío**. Output directory: **vacío** (servimos estático tal cual).
3. Deploy. Vercel toma `vercel.json` y `.vercelignore` automáticamente.

URLs resultantes:
- `https://<proyecto>.vercel.app/` → landing.
- `https://<proyecto>.vercel.app/dashboard/?run=run_bsw01a2` → demo en vivo.

## Opción B — CLI (deploy manual puntual)

```bash
npm i -g vercel      # una vez
vercel                # preview deploy (URL efímera)
vercel --prod         # a producción
```

## Verificar antes de deployar (local, sin backend)

```bash
python3 -m http.server 8097        # desde la raíz del repo
# abrir http://localhost:8097/            → landing
# abrir http://localhost:8097/dashboard/?run=run_bsw01a2  → demo
```

El dashboard cae a los fixtures bundleados cuando no hay API (`fetchStaticFallback`),
así que la demo completa —loop, wave64, diff, verdict, certificado y **Port
Passport verificable**— corre sin ningún backend. El Passport recomputa
`sha256(diff)` en el browser: botón *Tamper* → `TAMPERED`, *Re-verify* → `VERIFIED`.

## Cuando M0 grabe el run real

`scripts/record_fixture.sh <run_id>` reemplaza los fixtures por el trace/diff/
certificado/attestation reales. Al re-deployar, el badge pasa solo de
`synthetic demo` a `recorded run` y el Passport verifica el diff de silicio real.
