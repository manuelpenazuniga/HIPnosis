# DEVIATIONS — desviaciones del blueprint (una línea c/u, ANTES de implementar)

D-1 [2026-07-08] Auditor continuo = "Gemini 3.1 Pro (High)" (no "3.2 Pro"): `agy models` no lista 3.2; el binario manda (v2 §9). Sin impacto de diseño.
D-2 [2026-07-08] M0 (smoke test droplet MI300X) queda como tarea del HUMANO: no hay acceso al droplet ni ROCm desde la máquina de desarrollo (Mac). Todo el pipeline avanza en modo `mock` (§9, §13.2); `oracle/real.py` se valida en M0 por el humano.
