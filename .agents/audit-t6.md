Revisá MI código pre-merge por bugs de correctness. NO modifiques nada: solo LEÉ y REPORTÁ.
Archivos: orchestrator/core/wave64.py, orchestrator/tests/test_wave64.py + fixtures tests/fixtures/wave64/
Contexto: linter estático determinista, catálogo CERRADO W01-W07; explicaciones son TEXTO FIJO (jamás LLM).
Verificá punto por punto:
1. Despojado de comentarios (// y /* */) y strings ANTES de matchear: ¿preserva los saltos de línea (nº de línea correcto)? ¿maneja /* */ multilínea? ¿strings con comillas escapadas? Un W01 dentro de un comentario o string NO debe reportarse (hay tests negativos: verificá que sean reales).
2. Los 7 regex (W01..W07) coinciden con el catálogo del blueprint §5.2. severity correcta (W01-W03=correctness, W04-W07=suspicious). explanation = string FIJO EXACTO por patrón (no generado).
3. W05 solo dispara en líneas que ADEMÁS contienen threadIdx|laneId|lane_id (no en cualquier %32).
4. snippet = línea ±2. pattern_id/file/line correctos (1-based).
5. Layering: wave64 importa SOLO core.schemas + re. Sin config/phases/etc.
6. Falsos positivos/negativos del catálogo: ¿algún regex demasiado amplio o demasiado estrecho? ¿case-insensitive donde corresponde (W07)?
Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`; por hallazgo severidad+archivo:línea+fix; ÚLTIMA línea `END_AUDIT`.
