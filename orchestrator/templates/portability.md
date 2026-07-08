# HIPnosis — Portability Report

> **Repo:** `{{ data.repo_url }}`  ·  **Run:** `{{ data.run_id }}`  ·  **Generado:** {{ data.generated_at }}

## Resumen ejecutivo

{% if data.executive_summary %}{{ data.executive_summary }}
{% else %}_(Sin resumen — sección reservada para el redactor LLM, F-17/INV-7)._
{% endif %}

## Inventario y dificultad

| Metric | Value |
|---|---|
| Archivos CUDA | {{ data.files_cuda }} |
| LOC kernels | {{ data.loc_kernels }} |
| Build system | `{{ data.build_system }}` |
| Dificultad | `{{ data.difficulty }}` |
| Librerías NVIDIA | {% if data.libs %}{{ data.libs | join(", ") }}{% else %}_ninguna_{% endif %} |

## Wave64 (resumen)

{% set sev = namespace(correctness=0, suspicious=0) %}
{% for f in data.wave64_findings %}{% if f.severity == "correctness" %}{% set sev.correctness = sev.correctness + 1 %}{% elif f.severity == "suspicious" %}{% set sev.suspicious = sev.suspicious + 1 %}{% endif %}{% endfor %}
- Total hallazgos: **{{ data.wave64_findings | length }}**
  - `correctness` (W01–W03): **{{ sev.correctness }}**
  - `suspicious` (W04–W07): **{{ sev.suspicious }}**

{% if data.wave64_findings %}
| file:line | Pattern | Severity | Explicación |
|---|---|---|---|
{% for f in data.wave64_findings %}| `{{ f.file }}:{{ f.line }}` | `{{ f.pattern_id }}` | `{{ f.severity }}` | {{ f.explanation }} |
{% endfor %}
{% endif %}

## Métricas de eficiencia (F-17)

- % fixes locales: **{{ ((data.counters.fixes_deterministic + data.counters.fixes_local) * 100 // (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote)) if (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote) > 0 else 0 }}%**
- Tokens local/remoto: {{ data.counters.tokens_local }} / {{ data.counters.tokens_remote }}
- Iteraciones: {{ data.counters.iterations }}

## Limitaciones y NEEDS_HUMAN

{% if data.needs_human %}
- {% for sig in data.needs_human %}`{{ sig }}`{% if not loop.last %}, {% endif %}{% endfor %}
{% else %}_(Sin grupos sin resolver.)_
{% endif %}

---

_Portability Report · números de código (F-17/INV-7)._
