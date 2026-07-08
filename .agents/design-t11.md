**5. Riesgo próximo → T11 patcher (el más peligroso).** No T8 (plumbing con spec clara). T11 puede hacer **ediciones silenciosas erróneas** (F-05 catalogado) que corrompen el repo objetivo, y su correctness gatea CADA fix del loop. Diseño clave para el brief:

- **Unicidad dura (el corazón):** SEARCH debe matchear **exactamente 1 vez**. 0 → `PATCH_NOT_FOUND`; >1 → `PATCH_AMBIGUOUS`. **Jamás aplicar en ambigüedad** (INV-3/§6.3). Sin fuzzy por defecto — fuzzy = edits mudos mal.
- **Validate-all-then-write:** en parche multi-bloque, verificá que TODOS los SEARCH matchean únicos ANTES de tocar disco; luego escribir + **un** commit atómico vía gitrepo. Nunca aplicación parcial (all-or-nothing).
- **INV-4:** evento `patch_attempt` (file, hash de bloques, match count) al trace ANTES de escribir.
- **Self-check post-write:** re-leer y confirmar que REPLACE está presente; si no → `gitrepo` revert (reset HEAD~1) + fallo tipado.
- **Retorno tipado** (APPLIED/NOT_FOUND/AMBIGUOUS/VERIFY_FAILED) para que el loop ramifique — no excepciones sueltas.
- **Bordes que el worker se salta (los diseño yo):** (a) CRLF vs LF → normalizar line-endings al leer, consistente; (b) SEARCH vacío → reject; (c) REPLACE == SEARCH → reject (no-op ⇒ loop infinito, roza INV-10); (d) bloques solapados en misma región → reject; (e) file binario/fuera de workspace → reject tipado.
- *T14a (más lejos):* su riesgo es la convergencia de invariantes (INV-1/2/4/5/10). Su brief necesitará la **tabla estado×clase-error→acción** explícita + los dos contadores duros (MAX_ITERATIONS, MAX_ATTEMPTS_PER_GROUP). Ese diseño puede esperar a que T11/T13 aterricen.

**6. Proceso (UNA).** **Gate "fixture-first": ninguna primitiva mergea al camino-loop sin su fixture consumido commiteado al lado** (`build_NN.txt` AD-5a / `demo-run.jsonl` AD-5b). Convierte la deuda "validar contra M0-algún-día" en requisito por-tarea y ataca la causa raíz de errparse/T6b diferidos. Sin GPU es la única forma honesta de cerrar oráculos.
