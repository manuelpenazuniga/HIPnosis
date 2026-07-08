Trabajás en el worktree actual (rama spike/t15b-parity). Implementá SOLO esta tarea. Es de riesgo ALTO:
son los NÚMEROS del producto (F-09/F-17). Un comparador mal hecho da PASS a un port roto o FAIL a uno
correcto → mata la credibilidad del certificado.

--- TAREA T15b: core/parity.py — comparador numérico rtol/atol (F-09) ---
Capa L2: importa core.schemas y stdlib (re, math). NO importa phases/oracle/llm/state/config.
⛔ F-09: JAMÁS comparación exacta de floats. SIEMPRE rtol/atol. El orden de reducción / FMA cambia
los últimos bits legítimamente.

ARCHIVO: orchestrator/core/parity.py    TEST: orchestrator/tests/test_parity.py

### Contrato:

    @dataclass
    class ParityResult:
        ok: bool
        detail: str                 # qué se comparó, con qué tolerancia, cuántos valores, primer mismatch
        n_compared: int = 0

    def extract_floats(text: str) -> list[float]:
        # Extrae TODOS los números (int y float, notación científica incl. -1.2e-5, nan, inf) del texto,
        # en orden de aparición. Regex robusto: r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'.
        # Manejá 'nan'/'inf' si aparecen como palabras. Ignorá números pegados a identificadores si
        # podés, pero priorizá capturar los valores numéricos de salida.

    def compare_floats(actual: list[float], expected: list[float],
                       rtol: float = 1e-5, atol: float = 1e-8) -> ParityResult:
        # 1. Si len difiere → ok=False, detail dice "conteo distinto: N vs M".
        # 2. Compará posicionalmente con la fórmula de numpy.isclose SIN numpy:
        #    close = abs(a-e) <= atol + rtol*abs(e)   (para cada par)
        #    Manejá nan (nan==nan se considera IGUAL acá, es válido en algunos self-checks; documentá)
        #    e inf (inf==inf igual, inf!=-inf distinto).
        # 3. ok = todos cercanos. detail: "N valores comparados, rtol=..., atol=..."; si falla, el
        #    PRIMER índice que difiere con sus valores (a vs e y la diferencia).

    def check_self_check(stdout: str, pass_regex: str) -> ParityResult:
        # Modo self_check (§7.1): el benchmark imprime PASS/FAIL. ok = re.search(pass_regex, stdout) is not None.
        # detail: "self_check: patrón '<pass_regex>' {encontrado|no encontrado}".

    def check_golden(stdout: str, golden_text: str, rtol: float = 1e-5, atol: float = 1e-8) -> ParityResult:
        # Modo golden_output (§7.1): extraé floats de stdout y de golden_text, comparalos con compare_floats.

### Test test_parity.py (el comparador ES el producto — testealo a fondo):
- extract_floats: "Average time 12.5 ms, error 1.2e-5" → [12.5, 1.2e-5]; maneja negativos, científica.
- compare_floats: [1.0, 2.0] vs [1.0000001, 2.0] con rtol=1e-5 → ok=True (diferencia dentro de tol).
- compare_floats: [1.0] vs [1.1] rtol=1e-5 → ok=False, detail menciona el índice 0 y los valores.
- compare_floats: conteo distinto ([1,2] vs [1,2,3]) → ok=False.
- compare_floats: [nan] vs [nan] → ok=True (documentá la decisión); [inf] vs [inf] → ok=True; [inf] vs [-inf] → False.
- ⚠️ TEST CLAVE F-09: [0.1+0.2] vs [0.3] (que en float NO son exactamente iguales: 0.30000000000000004)
  con rtol default → ok=True. (comparación exacta daría FALSE — este test PRUEBA que no comparás exacto.)
- check_self_check: stdout con "PASS" y pass_regex="PASS" → ok=True; stdout con "FAIL" → ok=False.
- check_golden: dos textos con los mismos floats (uno con 12.5000, otro 12.5) → ok=True.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_parity.py -q` verde, INCLUYENDO el test F-09 (0.1+0.2 vs 0.3 → PASS).
2. F-09: NUNCA comparación exacta de floats. La fórmula es atol + rtol*abs(e).
3. parity.py NO importa phases/oracle/llm/state. Puro L2.
4. Los detail son informativos (qué se comparó, tolerancia, primer mismatch) — insumo del certificado (F-17).

Reglas duras:
- F-09: rtol/atol SIEMPRE, exacto JAMÁS. F-17: los números salen de este código, no de un LLM.
- Defaults rtol=1e-5, atol=1e-8 (los reales vienen del manifiesto/config, pero acá son defaults de firma).
- Al terminar: pytest verde + COMMIT ("feat(core): parity comparador rtol/atol (F-09) + tests").
- Respuesta CORTA: archivos + output pytest + confirmá que el test F-09 (0.1+0.2 vs 0.3) pasa. Bloqueo: 'BLOCKED | ...' y pará.
