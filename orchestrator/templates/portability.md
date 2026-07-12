# HIPnosis — Portability Report

> **Repo:** `{{ data.repo_url }}`  ·  **Run:** `{{ data.run_id }}`  ·  **Generated:** {{ data.generated_at }}

## Executive summary

{% if data.executive_summary %}{{ data.executive_summary }}
{% else %}_(No summary — section reserved for the LLM writer, F-17/INV-7)._
{% endif %}

## Inventory and difficulty

| Metric | Value |
|---|---|
| CUDA files | {{ data.files_cuda }} |
| Kernel LOC | {{ data.loc_kernels }} |
| Build system | `{{ data.build_system }}` |
| Difficulty | `{{ data.difficulty }}` |
| NVIDIA libraries | {% if data.libs %}{{ data.libs | join(", ") }}{% else %}_none_{% endif %} |

## Wave64 (summary)

{% set sev = namespace(correctness=0, suspicious=0) %}
{% for f in data.wave64_findings %}{% if f.severity == "correctness" %}{% set sev.correctness = sev.correctness + 1 %}{% elif f.severity == "suspicious" %}{% set sev.suspicious = sev.suspicious + 1 %}{% endif %}{% endfor %}
- Total findings: **{{ data.wave64_findings | length }}**
  - `correctness` (W01–W03): **{{ sev.correctness }}**
  - `suspicious` (W04–W07): **{{ sev.suspicious }}**

{% if data.wave64_findings %}
| file:line | Pattern | Severity | Explanation |
|---|---|---|---|
{% for f in data.wave64_findings %}| `{{ f.file }}:{{ f.line }}` | `{{ f.pattern_id }}` | `{{ f.severity }}` | {{ f.explanation }} |
{% endfor %}
{% endif %}

## Efficiency metrics (F-17)

- % local fixes: **{{ ((data.counters.fixes_deterministic + data.counters.fixes_local) * 100 // (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote)) if (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote) > 0 else 0 }}%**
- Local/remote tokens: {{ data.counters.tokens_local }} / {{ data.counters.tokens_remote }}
- Iterations: {{ data.counters.iterations }}

## Limitations and NEEDS_HUMAN

{% if data.needs_human %}
- {% for sig in data.needs_human %}`{{ sig }}`{% if not loop.last %}, {% endif %}{% endfor %}
{% else %}_(No unresolved groups.)_
{% endif %}

---

_Portability Report · numbers from code (F-17/INV-7)._
