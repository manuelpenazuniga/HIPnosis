Revisá MI código pre-merge por bugs de correctness. NO modifiques nada: solo LEÉ y REPORTÁ.
Archivos: orchestrator/core/phases/scan.py, orchestrator/tests/test_scan.py + fixtures tests/fixtures/scan_repo/
Contexto: FASE 1 SCAN — inventario CUDA + linter wave64 + heurística de dificultad (sin LLM).
Verificá punto por punto:
1. Inventario §5.1: api_calls cuenta llamadas cuda[A-Z]\w+ correctamente (¿cuenta dentro de comentarios/strings? scan reusa el stripper de wave64 — ¿bien?); libs detecta cublas/curand/cufft/cudnn; build_system make/cmake; loc_kernels solo .cu/.cuh.
2. Dificultad §5.3 heurística FIJA: easy=(0 PTX ∧ 0 libs ∧ loc<2000); hard=(PTX ∨ cudnn ∨ loc>10000); si no medium. ¿Bordes correctos (exactamente 2000/10000)? ¿PTX detectado por asm(...)?
3. F-17: los números salen de código; executive_summary queda "" (no LLM). Verificá que NO se llama a ningún LLM.
4. wave64_findings: corre wave64 sobre cada .cu/.cuh y los junta.
5. Layering L4: importa wave64/schemas (L2), NUNCA state/api/oracle. Nota: importa _strip_comments_and_strings (privado) de wave64 — ¿problema de encapsulación? reportalo como menor si aplica.
6. Casos borde: repo vacío, archivo no-utf8, Makefile ausente, cero archivos cuda.
Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`; por hallazgo severidad+archivo:línea+fix; ÚLTIMA línea `END_AUDIT`.
