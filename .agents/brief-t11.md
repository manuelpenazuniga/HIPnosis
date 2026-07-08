Trabajás en el worktree actual (rama spike/t11-patcher). Implementá SOLO esta tarea. Esta tarea es
CRÍTICA y de riesgo ALTO: un bug acá corrompe silenciosamente el repo objetivo (F-05) y gatea CADA
fix del loop. Seguí el diseño AL PIE DE LA LETRA.

--- TAREA T11: core/patcher.py — aplicador de parches SEARCH/REPLACE con unicidad dura ---
Capa L2: importa core.schemas, core.gitrepo (YA EXISTE), core.trace (YA EXISTE) y stdlib. NO importa
phases/oracle/llm/state.

ARCHIVO: orchestrator/core/patcher.py    TEST: orchestrator/tests/test_patcher.py

### Formato de parche (blueprint §6.3) — es lo que el LLM emite. Uno o más bloques:
    FILE: src/reduce.cu
    <<<<<<< SEARCH
    <texto exacto a buscar>
    =======
    <texto de reemplazo>
    >>>>>>> REPLACE
(Puede haber VARIOS bloques, cada uno con su `FILE:` y sus marcadores. Distintos archivos o el mismo.)

### Contrato (retorno TIPADO, NO excepciones para el flujo normal):

    from enum import Enum
    class PatchStatus(str, Enum):
        APPLIED = "applied"
        NOT_FOUND = "not_found"          # algún SEARCH matcheó 0 veces
        AMBIGUOUS = "ambiguous"          # algún SEARCH matcheó >1 vez
        INVALID = "invalid"              # parche mal formado / borde rechazado
        VERIFY_FAILED = "verify_failed"  # tras escribir, el REPLACE no quedó presente

    @dataclass
    class PatchResult:
        status: PatchStatus
        detail: str                      # motivo legible (qué archivo/bloque, qué pasó)
        commit_sha: str = ""             # sha si APPLIED, "" si no
        files_touched: list[str] = field(default_factory=list)

    def parse_blocks(patch_text: str) -> list[Block]:
        # Block = dataclass(file:str, search:str, replace:str). Parsea los marcadores
        # <<<<<<< SEARCH / ======= / >>>>>>> REPLACE y la línea FILE:. Tolerá espacios.
        # Si el texto no tiene ningún bloque bien formado → devolvé [] (el caller lo trata como INVALID).

    def apply_patch(patch_text: str, repo, commit_message: str, trace=None) -> PatchResult:
        # `repo` es un core.gitrepo.GitRepo (el workspace objetivo). `trace` es un
        # core.trace.TraceWriter opcional (None en tests).

### ALGORITMO EXACTO (diseño del arquitecto — NO improvises):
1. **Parsear** los bloques. Si 0 bloques → PatchResult(INVALID, "sin bloques SEARCH/REPLACE válidos").
2. **Validaciones de borde (rechazar ANTES de tocar disco, status=INVALID):**
   (a) SEARCH vacío → INVALID.
   (b) REPLACE == SEARCH → INVALID (no-op ⇒ loop infinito, roza INV-10).
   (c) path del FILE fuera del workspace (`..`, absoluto que escape del repo_dir) → INVALID.
   (d) archivo binario o inexistente en el workspace → INVALID.
   (e) dos bloques del MISMO archivo cuyas regiones SEARCH se SOLAPAN → INVALID.
3. **Normalizá line endings** al LEER cada archivo: CRLF→LF, consistente (y aplicá el reemplazo sobre
   el texto normalizado; al escribir, escribí LF). Documentá esta decisión.
4. **UNICIDAD DURA (el corazón, INV-3/§6.3):** por cada bloque, contá apariciones LITERALES del texto
   SEARCH en su archivo (comparación exacta con whitespace, sobre el texto normalizado):
   - alguna == 0 → PatchResult(NOT_FOUND, "<file>: SEARCH no encontrado"). **NO escribas nada.**
   - alguna > 1 → PatchResult(AMBIGUOUS, "<file>: SEARCH aparece N veces"). **NO escribas nada.**
   ⛔ JAMÁS apliques en ambigüedad. SIN fuzzy matching. Un match no-único es un fallo, no una heurística.
5. **VALIDATE-ALL-THEN-WRITE (all-or-nothing):** solo si TODOS los bloques matchean EXACTAMENTE 1 vez,
   procedé. Si alguno falla, ya devolviste en el paso 4 sin escribir NADA (nunca aplicación parcial).
6. **INV-4 (trace antes de actuar):** si trace no es None, emití ANTES de escribir:
   `trace.emit("patch_attempt", files=[...], blocks=<n>, all_unique=True)`.
7. **Escribir** cada archivo con su(s) reemplazo(s) aplicados (reemplazá la única aparición).
8. **Commit atómico** vía `repo.commit_all(commit_message)` → guardá el sha.
9. **Self-check post-write:** re-leé cada archivo tocado y confirmá que el texto REPLACE está presente.
   Si en alguno NO está → `repo.revert_head()` (revierte el commit) → PatchResult(VERIFY_FAILED, ...).
10. Éxito → PatchResult(APPLIED, "N bloques aplicados", commit_sha=sha, files_touched=[...]).

### Test test_patcher.py (pytest, tmp_path + GitRepo real sobre un repo git temporal):
Creá un repo git en tmp_path (init + un archivo fuente con contenido conocido + commit inicial),
abrilo con core.gitrepo.GitRepo. Casos:
- **APPLIED**: parche cuyo SEARCH aparece 1 vez → status APPLIED, el archivo cambió, hay commit nuevo,
  files_touched correcto. Self-check pasa.
- **NOT_FOUND**: SEARCH que no existe → NOT_FOUND, el archivo NO cambió, NO hay commit nuevo.
- **AMBIGUOUS**: SEARCH que aparece 2 veces → AMBIGUOUS, sin escribir, sin commit.
- **Multi-bloque all-or-nothing**: 2 bloques, uno válido y otro NOT_FOUND → NADA se escribe (el válido
  tampoco), status NOT_FOUND. (test crítico de atomicidad)
- **INVALID borde**: SEARCH vacío; REPLACE==SEARCH; path con `..`; bloques solapados → INVALID cada uno.
- **Multi-archivo APPLIED**: 2 bloques en 2 archivos distintos, ambos únicos → ambos aplicados, 1 commit.
- (opcional) trace: pasá un TraceWriter a un jsonl temporal y verificá que se emitió patch_attempt.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_patcher.py -q` verde (TODOS los casos, incl. atomicidad multi-bloque).
2. patcher.py NO importa phases/oracle/llm/state. Usa gitrepo para commit/revert (INV-3) y trace opcional (INV-4).
3. UNICIDAD DURA verificada por test: 0→NOT_FOUND, >1→AMBIGUOUS, jamás escribe en esos casos.
4. ALL-OR-NOTHING verificado: un parche multi-bloque con un bloque inválido NO escribe ninguno.

Reglas duras:
- INV-3: todo cambio al repo objetivo = commit atómico vía gitrepo; solo SEARCH/REPLACE con unicidad. Nunca reescritura de archivo completo, nunca diffs unificados.
- F-05: sin fuzzy matching. Un SEARCH no-único es fallo tipado, no una adivinanza.
- INV-4: patch_attempt al trace ANTES de escribir (si hay trace).
- Al terminar: pytest verde + COMMIT ("feat(core): patcher SEARCH/REPLACE unicidad dura + tests").
- Respuesta CORTA: archivos + output pytest + confirmá que los casos NOT_FOUND/AMBIGUOUS/atomicidad pasan. Bloqueo: 'BLOCKED | ...' y pará.
