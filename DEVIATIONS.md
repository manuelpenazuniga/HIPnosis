# DEVIATIONS — desviaciones del blueprint (una línea c/u, ANTES de implementar)

D-1 [2026-07-08] Auditor continuo = "Gemini 3.1 Pro (High)" (no "3.2 Pro"): `agy models` no lista 3.2; el binario manda (v2 §9). Sin impacto de diseño.
D-2 [2026-07-08] M0 (smoke test droplet MI300X) queda como tarea del HUMANO: no hay acceso al droplet ni ROCm desde la máquina de desarrollo (Mac). Todo el pipeline avanza en modo `mock` (§9, §13.2); `oracle/real.py` se valida en M0 por el humano.
D-3 [2026-07-08] Consultas al Arquitecto (rol premium v3): modelo = Opus 4.8 xhigh, no Fable (cuota Fable muy limitada; escalar a fable high solo si Opus falla). Ajuste operativo del workflow, no del producto.
D-4 [2026-07-08] Routing de workers ajustado a cuotas reales (humano): aprovechar agy (Gemini 3.1 Pro High = audit; Flash Medium/High = workers) y opencode-go (deepseek-v4-pro / minimax-m3 / qwen3.7-plus). VETADOS por caros: GLM y Kimi (TODAS las variantes) + Qwen 3.7 Max. Ajuste operativo, no del producto.
D-5 [2026-07-08] Baseline wave64 mergeado fiel a §5.2; tightening de regex (precisión, audit Gemini T6) DIFERIDO a T6b como la calibración día-2 que el blueprint §6.2/§12 M2 ya prescribe, validada contra repos reales (bsw/softmax). No es desviación del spec sino su calibración planificada.
