## HIPnosis port — `{{ data.run_id }}`

> Port automático de `{{ data.repo_url }}` a ROCm/HIP.
> **Verdict:** `{{ data.verify_verdict }}`  ·  **Dificultad:** `{{ data.difficulty }}`  ·  **Build:** `{{ data.build_system }}`

### Cambios

- Archivos CUDA portados: **{{ data.files_cuda }}** (LOC kernels: {{ data.loc_kernels }})
- Sistema de build adaptado a `{{ data.build_system }}` para `hipcc`/`gfx942`
{% if data.fixes_by_class %}
- Fixes aplicados:
{% for row in data.fixes_by_class %}
  - `{{ row.klass }}` × {{ row.n }} (tier `{{ row.tier }}`){% if row.commits %} — commits {% for sha in row.commits %}`{{ sha }}`{% if not loop.last %}, {% endif %}{% endfor %}{% endif %}
{% endfor %}
{% endif %}

### Wave64 (linter determinista)

{% if data.wave64_findings %}
- {{ data.wave64_findings | length }} hallazgos (catálogo cerrado §5.2):
{% for f in data.wave64_findings %}
  - `{{ f.file }}:{{ f.line }}` — `{{ f.pattern_id }}` (`{{ f.severity }}`): {{ f.explanation }}
{% endfor %}
{% else %}
- 0 hallazgos — el código no asume warp=32.
{% endif %}

### Verificación

- **Verdict:** `{{ data.verify_verdict }}`
{% if data.verify_detail %}
- **Detalle:** {{ data.verify_detail }}
{% endif %}

### Limitaciones y NEEDS_HUMAN

{% if data.needs_human %}
- {% for sig in data.needs_human %}`{{ sig }}`{% if not loop.last %}, {% endif %}{% endfor %}
{% else %}
- _(Sin grupos sin resolver.)_
{% endif %}

### Métricas

- % fixes locales: **{{ ((data.counters.fixes_deterministic + data.counters.fixes_local) * 100 // (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote)) if (data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote) > 0 else 0 }}%** ({{ data.counters.fixes_deterministic }} deterministic + {{ data.counters.fixes_local }} local / {{ data.counters.fixes_deterministic + data.counters.fixes_local + data.counters.fixes_remote }} total)
- Iteraciones del loop: {{ data.counters.iterations }}
- Errores: {{ data.counters.errors_initial }} → {{ data.counters.errors_current }}

---

_Generado por HIPnosis. PR es azúcar; el certificado es el producto (F-13b)._
