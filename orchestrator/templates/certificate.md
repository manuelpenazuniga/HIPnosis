# HIPnosis — Port Certificate

> **Repo:** `{{ data.repo_url }}`
> **Run:** `{{ data.run_id }}`  ·  **Generated:** {{ data.generated_at }}
> **Difficulty:** `{{ data.difficulty }}`  ·  **Build system:** `{{ data.build_system }}`

---

## 1. Resumen ejecutivo

{% if data.executive_summary %}{{ data.executive_summary }}
{% else %}_(Sin resumen ejecutivo — generado únicamente con datos del pipeline; F-17/INV-7)._
{% endif %}

---

## 2. Inventario

| Metric | Value |
|---|---|
| Archivos CUDA (`.cu`/`.cuh`) | **{{ data.files_cuda }}** |
| Líneas de kernels (LOC) | **{{ data.loc_kernels }}** |
| Sistema de build | `{{ data.build_system }}` |
| Dificultad (heurística §5.3) | `{{ data.difficulty }}` |
| Librerías NVIDIA detectadas | {{ data.libs | length }}: {% if data.libs %}`{{ data.libs | join('`, `') }}`{% else %}_ninguna_{% endif %} |

### 2.1 Llamadas a API CUDA (conteo)

{% if data.api_calls %}
| API | Count |
|---|---:|
{% for name, n in data.api_calls.items() %}| `{{ name }}` | {{ n }} |
{% endfor %}
{% else %}_(Sin llamadas detectadas.)_
{% endif %}

---

## 3. Fixes aplicados

{% if data.fixes_by_class %}
| Clase | n | Tier | Commits |
|---|---:|---|---|
{% for row in data.fixes_by_class %}| `{{ row.klass }}` | {{ row.n }} | `{{ row.tier }}` | {% if row.commits %}{% for sha in row.commits %}`{{ sha }}`{% if not loop.last %}, {% endif %}{% endfor %}{% else %}_(sin commits registrados)_{% endif %} |
{% endfor %}
{% else %}_(El loop no aplicó fixes — el repo ya compila o no se llegó a la fase BUILD_LOOP.)_
{% endif %}

---

## 4. Hallazgos wave64 (linter determinista, §5.2)

{% if data.wave64_findings %}
| file:line | Pattern | Severity | Explicación |
|---|---|---|---|
{% for f in data.wave64_findings %}| `{{ f.file }}:{{ f.line }}` | `{{ f.pattern_id }}` | `{{ f.severity }}` | {{ f.explanation }} |
{% endfor %}
{% else %}_(Sin hallazgos wave64 — el código no asume warp=32 en patrones conocidos.)_
{% endif %}

---

## 5. Verificación

- **Verdict:** `{{ data.verify_verdict }}`
{% if data.verify_detail %}
- **Detalle:** {{ data.verify_detail }}
{% endif %}
{% if data.timing %}
- **Tolerancias:** rtol/atol por defecto (F-09); no se compara floats en forma exacta.
{% endif %}

---

## 6. Timing

{% if data.timing %}
```json
{{ data.timing | tojson(indent=2) }}
```
{% else %}_(Sin timing reportado — el verify no se ejecutó o no proveyó métricas.)_
{% endif %}

---

## 7. Limitaciones y NEEDS_HUMAN

> ⚠️ **Sección obligatoria** (degradación honesta, INV-5). Aunque esté vacía,
> el certificado la incluye para que el lector sepa que el orquestador NO
> oculta lo que no pudo resolver.

{% if data.needs_human %}
El loop no logró resolver las siguientes firmas (subjetivas a contexto del
repo o fuera del catálogo de reglas deterministas). Requieren intervención
humana o un modelo con más contexto que el LLM local:

{% for sig in data.needs_human %}
- `{{ sig }}`
{% endfor %}
{% else %}
_No hay grupos sin resolver. El loop convergió (o no llegó a la fase de
fixes)._
{% endif %}

---

## 8. Métricas de eficiencia

- **% fixes locales (deterministic + local)**: **{{ ((data.counters.fixes_deterministic + data.counters.fixes_local) * 100 // (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote)) if (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote) > 0 else 0 }}%** ({{ data.counters.fixes_deterministic }} deterministic + {{ data.counters.fixes_local }} local / {{ data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote }} total)
- **Tokens local:** {{ data.counters.tokens_local }}
- **Tokens remoto:** {{ data.counters.tokens_remote }}
- **Iteraciones del loop:** {{ data.counters.iterations }}
- **Errores iniciales → actuales:** {{ data.counters.errors_initial }} → {{ data.counters.errors_current }}

> Los números de esta sección se computan a partir de los contadores del
> pipeline (F-17/INV-7): ningún campo es redactado por un LLM.

---

_Generado por HIPnosis · F-17/INV-7: números siempre desde código._
