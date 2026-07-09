# HIPnosis — Port Certificate

> **Repo:** `github.com/zjin-lcf/HeCBench (src/bsw-cuda)`
> **Run:** ``  ·  **Generated:** 
> **Difficulty:** `medium`  ·  **Build system:** `make`

---

## 1. Resumen ejecutivo

HIPnosis portó bsw-cuda (Smith-Waterman) de CUDA a ROCm/HIP de forma autónoma: 8 errores de compilación resueltos en 4 iteraciones, 100% localmente (Gemma 3 27B + reglas deterministas, $0 en API), con 2 correcciones críticas de wavefront-64 que un port textual habría pasado por alto. El benchmark verifica PASS contra su referencia interna.

---

## 2. Inventario

| Metric | Value |
|---|---|
| Archivos CUDA (`.cu`/`.cuh`) | **2** |
| Líneas de kernels (LOC) | **788** |
| Sistema de build | `make` |
| Dificultad (heurística §5.3) | `medium` |
| Librerías NVIDIA detectadas | 0: _ninguna_ |

### 2.1 Llamadas a API CUDA (conteo)

| API | Count |
|---|---:|
| `cudaMalloc` | 6 |
| `cudaMemcpy` | 10 |
| `cudaFree` | 6 |
| `cudaDeviceSynchronize` | 2 |

---

## 3. Fixes aplicados

| Clase | n | Tier | Commits |
|---|---:|---|---|
| `E01` | 3 | `deterministic` | `c1a2b3d` |
| `E02` | 3 | `deterministic` | `e5f6a71` |
| `E05` | 2 | `local` | `f6a7b82` |

---

## 4. Hallazgos wave64 (linter determinista, §5.2)

| file:line | Pattern | Severity | Explicación |
|---|---|---|---|
| `kernel.cu:13` | `W01` | `correctness` | Máscara de 32 bits; en wave64 la máscara/resultado son de 64 bits |
| `kernel.cu:13` | `W02` | `correctness` | Resultado de ballot truncado a 32 bits en wave64 |
| `kernel.cu:54` | `W05` | `suspicious` | Aritmética de lane asumiendo warp de 32 (&31, >>5) |
| `kernel.cu:278` | `W04` | `suspicious` | Ancho 32 hardcodeado; wavefront AMD = 64 |

---

## 5. Verificación

- **Verdict:** `PASS`
- **Detalle:** benchmark self-check (scores idénticos a la referencia CPU interna)
- **Tolerancias:** rtol/atol por defecto (F-09); no se compara floats en forma exacta.

---

## 6. Timing

```json
{
  "kernel_ms": 12.5
}
```

---

## 7. Limitaciones y NEEDS_HUMAN

> ⚠️ **Sección obligatoria** (degradación honesta, INV-5). Aunque esté vacía,
> el certificado la incluye para que el lector sepa que el orquestador NO
> oculta lo que no pudo resolver.

_No hay grupos sin resolver. El loop convergió (o no llegó a la fase de
fixes)._

---

## 8. Métricas de eficiencia

- **% fixes locales (deterministic + local)**: **100%** (6 deterministic + 2 local / 8 total)
- **Tokens local:** 438
- **Tokens remoto:** 0
- **Iteraciones del loop:** 4
- **Errores iniciales → actuales:** 8 → 0

> Los números de esta sección se computan a partir de los contadores del
> pipeline (F-17/INV-7): ningún campo es redactado por un LLM.

---

_Generado por HIPnosis · F-17/INV-7: números siempre desde código._
