VERDICT: CHANGES

### Auditoría Punto por Punto

#### 1. Despojado de comentarios (`//` y `/* */`) y strings
- **Preservación de saltos de línea (nº de línea y snippets):** El stripper preserva correctamente los saltos de línea (`\n`) en comentarios de línea, comentarios de bloque multilínea y literales simples, garantizando que los índices y números de línea 1-based coincidan con el código original.
- **Bug de correctness en saltos de línea escapados dentro de literales (cadenas y caracteres):** En los estados `STRING` y `CHAR` ([wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)), cuando se encuentra una barra invertida (`c == "\\"`), el código reemplaza tanto el carácter actual como el siguiente por espacios (`out[i] = " "; out[i + 1] = " "; i += 2`). Si una cadena o macro contiene una continuación de línea con salto de línea escapado (`\\\n`), **el carácter `\n` es reemplazado por un espacio**. Esto destruye el salto de línea, haciendo que `len(stripped_lines) < len(orig_lines)` y desfasando los números de línea (`lineno`) y los fragmentos (`_snippet`) de **todos** los hallazgos que ocurran después en ese archivo.
- **Comillas escapadas y comentarios multilínea:** El manejo de `/* */` multilínea es correcto. El escape de comillas (`\"` y `\'`) dentro de strings funciona adecuadamente.
- **Tests negativos:** Se verificó en [test_wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/test_wave64.py) y en el fixture [wave64_patterns.cu](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu) que los tests negativos son reales y validan eficazmente que un `W01` o `W06` dentro de comentarios o literales no sea reportado.

#### 2. Catálogo §5.2, Severidad y Explicaciones
- Las 7 expresiones regulares coinciden con el catálogo §5.2 del blueprint.
- La severidad asignada es exactamente la estipulada: `W01`-`W03` como `correctness` y `W04`-`W07` como `suspicious`.
- El atributo `explanation` es un string fijo y determinista, copiado textualmente del blueprint sin ninguna intervención o generación dinámica de LLM.

#### 3. Guarda de W05 (`_W05_LINE_GUARD`)
- Verificado: `_W05_LINE_GUARD.search(line)` ([wave64.py:210](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L210)) se evalúa antes que `_PATTERN_W05.finditer(line)`, asegurando que `W05` solo se dispare en líneas que contengan explícitamente `threadIdx`, `laneId` o `lane_id`, y no en cualquier operación mod/div sobre el número 32 en el resto del código.

#### 4. Snippets y Metadatos
- El helper `_snippet` ([wave64.py:145-148](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L145-L148)) calcula correctamente la ventana de contexto como la línea central $\pm 2$ (`max(0, idx - 2)` hasta `min(len(orig_lines), idx + 3)`).
- Los atributos `pattern_id`, `file` y `line` (1-based mediante `idx + 1`) son asignados correctamente en el modelo Pydantic `Wave64Finding`.

#### 5. Layering y Pureza L2
- Verificado: [wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py) importa únicamente `re` (de la stdlib) y `Wave64Finding` desde `core.schemas`. No hay violaciones de layering ni importaciones de configuración, fases u otros módulos de arquitectura.

---

### Hallazgos de Correctness y Catálogo (Severidad + Archivo:Línea + Fix)

- **[correctness] [orchestrator/core/wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [orchestrator/core/wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)**
  - **Problema:** En el stripper, al procesar secuencias de escape (`\\`) en los estados `STRING` y `CHAR`, se reemplazan `source[i]` y `source[i + 1]` con espacios intencionadamente para saltar comillas escapadas. Sin embargo, si `source[i + 1]` es un salto de línea (`\n`, común en macros o strings multilínea con continuación `\`), el salto de línea es borrado. Esto desfasa el conteo de líneas de `stripped_lines` respecto a `orig_lines`, corrompiendo el número de línea y el snippet de los hallazgos posteriores.
  - **Fix:** Verificar que el carácter escapado no sea un salto de línea antes de sobrescribirlo con espacio:
    ```python
    if c == "\\" and i + 1 < n:
        out[i] = " "
        if source[i + 1] != "\n":
            out[i + 1] = " "
        i += 2
    ```

- **[correctness] [orchestrator/core/wave64.py:34](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L34)**
  - **Problema (W01 - Falso Negativo y Falso Positivo):** `_PATTERN_W01` (`r"__ballot(_sync)?\s*\(\s*0xffffffff"`) no utiliza `re.IGNORECASE`. Si en el código CUDA/HIP se escribe la máscara en mayúsculas (`0xFFFFFFFF`), el linter no la detecta (Falso Negativo). Asimismo, al carecer de delimitador de fin de palabra, matchearía por prefijo máscaras inválidas o más largas como `0xffffffff0` (Falso Positivo).
  - **Fix:** Añadir delimitador al final o compilar con `re.IGNORECASE`:
    ```python
    _PATTERN_W01 = re.compile(r"__ballot(_sync)?\s*\(\s*0x[fF]{8}\b")
    ```

- **[correctness] [orchestrator/core/wave64.py:35](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L35)**
  - **Problema (W02 - Falso Positivo con enteros de 64 bits):** El patrón `r"(unsigned|uint32_t|int)\s+\w+\s*=\s*__ballot"` no evita coincidir dentro de tipos más amplios. En declaraciones como `unsigned long int mask = __ballot(...)` o `long int x = __ballot(...)` (donde en x86_64 Linux/HIP `long int` es de 64 bits), la subcadena `int mask = __ballot` o `int x = __ballot` genera un match, reportando erróneamente truncamiento a 32 bits en variables de 64 bits (Falso Positivo). También omite tipos muy comunes como `uint`, `int32_t` o `auto` (Falso Negativo).
  - **Fix:** Añadir word boundaries, impedir que anteceda la palabra `long` y ampliar los tipos cubiertos:
    ```python
    _PATTERN_W02 = re.compile(r"(?<!\blong\s)\b(unsigned(\s+int)?|uint32_t|int32_t|int|uint|auto)\s+\w+\s*=\s*__ballot")
    ```

- **[suspicious] [orchestrator/core/wave64.py:37](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L37)**
  - **Problema (W04 - Falso Positivo en argumentos previos):** El subpatrón `\([^)]*\b32\b` busca el token `32` en *cualquier* argumento dentro de los paréntesis de `__shfl...`. Si un kernel usa correctamente el ancho `64` para wave64 en el último parámetro, pero pasa `32` en un argumento anterior (por ejemplo, en el delta de un desplazamiento: `__shfl_up_sync(mask, val, 32, 64)`, o en un índice de arreglo: `__shfl_sync(mask, arr[32], lane, 64)`), dispara W04 incorrectamente.
  - **Fix:** Asegurar que el `32` detectado corresponda efectivamente al parámetro de ancho (el último argumento antes de cerrar paréntesis):
    ```python
    _PATTERN_W04 = re.compile(r"__shfl(_up|_down|_xor)?(_sync)?\s*\([^)]*,\s*32\s*\)")
    ```

- **[suspicious] [orchestrator/core/wave64.py:38](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L38)**
  - **Problema (W05 - Falso Positivo por producto cartesiano):** La alternancia `(%|&|/|>>)\s*(32|31|5)\b` permite cualquier combinación de operador y número. Operaciones válidas que no asumen warp de 32 pero que están en líneas con `threadIdx` (ej. división por bloques de 5 elementos: `threadIdx.x / 5`, o `% 5`, `& 5`, `>> 32`) disparan W05 erróneamente (Falso Positivo). Además, omite literales hexadecimales equivalentes como `& 0x1f` o `& 0x1F` (Falso Negativo).
  - **Fix:** Emparejar estrictamente cada operador aritmético con su operando de warp de 32 y permitir formato hexadecimal:
    ```python
    _PATTERN_W05 = re.compile(r"(?:[/%]\s*32|&\s*(?:31|0x1[fF])|>>\s*5)\b")
    ```

- **[suspicious] [orchestrator/core/wave64.py:39](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L39)**
  - **Problema (W06 - Falso Negativo en sobrecarga de función):** En Cooperative Groups, `tiled_partition` puede invocarse como plantilla (`cg::tiled_partition<32>(parent)`) o como función con tamaño en tiempo de ejecución (`cg::tiled_partition(parent, 32)`). El patrón actual solo cubre la sintaxis de plantilla `<32>`, ignorando la invocación funcional con tamaño 32.
  - **Fix:** Soportar ambas sobrecargas:
    ```python
    _PATTERN_W06 = re.compile(r"tiled_partition\s*(?:<\s*32\s*>|\([^)]*,\s*32\s*\))")
    ```

- **[suspicious] [orchestrator/core/wave64.py:40-43](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L40-L43) y [orchestrator/tests/fixtures/wave64/wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52)**
  - **Problema (W07 - Falsos Positivos por prefijo y bug de diseño en rama `constexpr`):**
    1) En `#define\s+WARP_SIZE\s+32` falta un word boundary al final, por lo que macros como `#define WARP_SIZE 320` disparan W07 por coincidencia de prefijo (Falso Positivo).
    2) En la rama `constexpr\s+\w*\s*=\s*32.*warp`, el patrón `\w*` permite como máximo un solo token antes del `=`. En C++ válido, las variables `constexpr` llevan tipo (ej. `constexpr int WARP_SIZE = 32;`), lo que representa al menos dos palabras (`int` y `WARP_SIZE`) antes del `=`, haciendo que el regex **no matchee jamás** en código C++ real.
    3) Además, el subpatrón `.*warp` exige que la palabra "warp" aparezca *después* del número `32` (a la derecha del `=`), cuando en realidad en código C++ "warp" forma parte del nombre de la variable *antes* del `=`. *Nota: Esto forzó un workaround artificial en el fixture sintético en [wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52), donde se escribió `constexpr WARP = 32; int warp = WARP;` (sintaxis inválida en C++ sin tipo y con variable ficticia final) solo para que el test pudiera pasar.*
  - **Fix:** Requerir word boundary en 32 y permitir que el tipo y el identificador que contenga "warp" se ubiquen antes o después del signo de asignación:
    ```python
    _PATTERN_W07 = re.compile(
        r"(#define\s+\w*WARP\w*\s+32\b|constexpr\s+[^=]*warp[^=]*=\s*32\b)",
        re.IGNORECASE,
    )
    ```

END_AUDIT
VERDICT: CHANGES

### Auditoría Punto por Punto

#### 1. Despojado de comentarios (`//` y `/* */`) y strings
- **Preservación de saltos de línea (nº de línea y snippets):** El stripper preserva correctamente los saltos de línea (`\n`) en comentarios de línea, comentarios de bloque multilínea y literales simples, garantizando que los índices y números de línea 1-based coincidan con el código original.
- **Bug de correctness en saltos de línea escapados dentro de literales (cadenas y caracteres):** En los estados `STRING` y `CHAR` ([wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)), cuando se encuentra una barra invertida (`c == "\\"`), el código reemplaza tanto el carácter actual como el siguiente por espacios (`out[i] = " "; out[i + 1] = " "; i += 2`). Si una cadena o macro contiene una continuación de línea con salto de línea escapado (`\\\n`), **el carácter `\n` es reemplazado por un espacio**. Esto destruye el salto de línea, haciendo que `len(stripped_lines) < len(orig_lines)` y desfasando los números de línea (`lineno`) y los fragmentos (`_snippet`) de **todos** los hallazgos que ocurran después en ese archivo.
- **Comillas escapadas y comentarios multilínea:** El manejo de `/* */` multilínea es correcto. El escape de comillas (`\"` y `\'`) dentro de strings funciona adecuadamente.
- **Tests negativos:** Se verificó en [test_wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/test_wave64.py) y en el fixture [wave64_patterns.cu](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu) que los tests negativos son reales y validan eficazmente que un `W01` o `W06` dentro de comentarios o literales no sea reportado.

#### 2. Catálogo §5.2, Severidad y Explicaciones
- Las 7 expresiones regulares coinciden con el catálogo §5.2 del blueprint.
- La severidad asignada es exactamente la estipulada: `W01`-`W03` como `correctness` y `W04`-`W07` como `suspicious`.
- El atributo `explanation` es un string fijo y determinista, copiado textualmente del blueprint sin ninguna intervención o generación dinámica de LLM.

#### 3. Guarda de W05 (`_W05_LINE_GUARD`)
- Verificado: `_W05_LINE_GUARD.search(line)` ([wave64.py:210](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L210)) se evalúa antes que `_PATTERN_W05.finditer(line)`, asegurando que `W05` solo se dispare en líneas que contengan explícitamente `threadIdx`, `laneId` o `lane_id`, y no en cualquier operación mod/div sobre el número 32 en el resto del código.

#### 4. Snippets y Metadatos
- El helper `_snippet` ([wave64.py:145-148](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L145-L148)) calcula correctamente la ventana de contexto como la línea central $\pm 2$ (`max(0, idx - 2)` hasta `min(len(orig_lines), idx + 3)`).
- Los atributos `pattern_id`, `file` y `line` (1-based mediante `idx + 1`) son asignados correctamente en el modelo Pydantic `Wave64Finding`.

#### 5. Layering y Pureza L2
- Verificado: [wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py) importa únicamente `re` (de la stdlib) y `Wave64Finding` desde `core.schemas`. No hay violaciones de layering ni importaciones de configuración, fases u otros módulos de arquitectura.

---

### Hallazgos de Correctness y Catálogo (Severidad + Archivo:Línea + Fix)

- **[correctness] [orchestrator/core/wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [orchestrator/core/wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)**
  - **Problema:** En el stripper, al procesar secuencias de escape (`\\`) en los estados `STRING` y `CHAR`, se reemplazan `source[i]` y `source[i + 1]` con espacios intencionadamente para saltar comillas escapadas. Sin embargo, si `source[i + 1]` es un salto de línea (`\n`, común en macros o strings multilínea con continuación `\`), el salto de línea es borrado. Esto desfasa el conteo de líneas de `stripped_lines` respecto a `orig_lines`, corrompiendo el número de línea y el snippet de los hallazgos posteriores.
  - **Fix:** Verificar que el carácter escapado no sea un salto de línea antes de sobrescribirlo con espacio:
    ```python
    if c == "\\" and i + 1 < n:
        out[i] = " "
        if source[i + 1] != "\n":
            out[i + 1] = " "
        i += 2
    ```

- **[correctness] [orchestrator/core/wave64.py:34](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L34)**
  - **Problema (W01 - Falso Negativo y Falso Positivo):** `_PATTERN_W01` (`r"__ballot(_sync)?\s*\(\s*0xffffffff"`) no utiliza `re.IGNORECASE`. Si en el código CUDA/HIP se escribe la máscara en mayúsculas (`0xFFFFFFFF`), el linter no la detecta (Falso Negativo). Asimismo, al carecer de delimitador de fin de palabra, matchearía por prefijo máscaras inválidas o más largas como `0xffffffff0` (Falso Positivo).
  - **Fix:** Añadir delimitador al final o compilar con `re.IGNORECASE`:
    ```python
    _PATTERN_W01 = re.compile(r"__ballot(_sync)?\s*\(\s*0x[fF]{8}\b")
    ```

- **[correctness] [orchestrator/core/wave64.py:35](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L35)**
  - **Problema (W02 - Falso Positivo con enteros de 64 bits):** El patrón `r"(unsigned|uint32_t|int)\s+\w+\s*=\s*__ballot"` no evita coincidir dentro de tipos más amplios. En declaraciones como `unsigned long int mask = __ballot(...)` o `long int x = __ballot(...)` (donde en x86_64 Linux/HIP `long int` es de 64 bits), la subcadena `int mask = __ballot` o `int x = __ballot` genera un match, reportando erróneamente truncamiento a 32 bits en variables de 64 bits (Falso Positivo). También omite tipos muy comunes como `uint`, `int32_t` o `auto` (Falso Negativo).
  - **Fix:** Añadir word boundaries, impedir que anteceda la palabra `long` y ampliar los tipos cubiertos:
    ```python
    _PATTERN_W02 = re.compile(r"(?<!\blong\s)\b(unsigned(\s+int)?|uint32_t|int32_t|int|uint|auto)\s+\w+\s*=\s*__ballot")
    ```

- **[suspicious] [orchestrator/core/wave64.py:37](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L37)**
  - **Problema (W04 - Falso Positivo en argumentos previos):** El subpatrón `\([^)]*\b32\b` busca el token `32` en *cualquier* argumento dentro de los paréntesis de `__shfl...`. Si un kernel usa correctamente el ancho `64` para wave64 en el último parámetro, pero pasa `32` en un argumento anterior (por ejemplo, en el delta de un desplazamiento: `__shfl_up_sync(mask, val, 32, 64)`, o en un índice de arreglo: `__shfl_sync(mask, arr[32], lane, 64)`), dispara W04 incorrectamente.
  - **Fix:** Asegurar que el `32` detectado corresponda efectivamente al parámetro de ancho (el último argumento antes de cerrar paréntesis):
    ```python
    _PATTERN_W04 = re.compile(r"__shfl(_up|_down|_xor)?(_sync)?\s*\([^)]*,\s*32\s*\)")
    ```

- **[suspicious] [orchestrator/core/wave64.py:38](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L38)**
  - **Problema (W05 - Falso Positivo por producto cartesiano):** La alternancia `(%|&|/|>>)\s*(32|31|5)\b` permite cualquier combinación de operador y número. Operaciones válidas que no asumen warp de 32 pero que están en líneas con `threadIdx` (ej. división por bloques de 5 elementos: `threadIdx.x / 5`, o `% 5`, `& 5`, `>> 32`) disparan W05 erróneamente (Falso Positivo). Además, omite literales hexadecimales equivalentes como `& 0x1f` o `& 0x1F` (Falso Negativo).
  - **Fix:** Emparejar estrictamente cada operador aritmético con su operando de warp de 32 y permitir formato hexadecimal:
    ```python
    _PATTERN_W05 = re.compile(r"(?:[/%]\s*32|&\s*(?:31|0x1[fF])|>>\s*5)\b")
    ```

- **[suspicious] [orchestrator/core/wave64.py:39](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L39)**
  - **Problema (W06 - Falso Negativo en sobrecarga de función):** En Cooperative Groups, `tiled_partition` puede invocarse como plantilla (`cg::tiled_partition<32>(parent)`) o como función con tamaño en tiempo de ejecución (`cg::tiled_partition(parent, 32)`). El patrón actual solo cubre la sintaxis de plantilla `<32>`, ignorando la invocación funcional con tamaño 32.
  - **Fix:** Soportar ambas sobrecargas:
    ```python
    _PATTERN_W06 = re.compile(r"tiled_partition\s*(?:<\s*32\s*>|\([^)]*,\s*32\s*\))")
    ```

- **[suspicious] [orchestrator/core/wave64.py:40-43](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L40-L43) y [orchestrator/tests/fixtures/wave64/wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52)**
  - **Problema (W07 - Falsos Positivos por prefijo y bug de diseño en rama `constexpr`):**
    1) En `#define\s+WARP_SIZE\s+32` falta un word boundary al final, por lo que macros como `#define WARP_SIZE 320` disparan W07 por coincidencia de prefijo (Falso Positivo).
    2) En la rama `constexpr\s+\w*\s*=\s*32.*warp`, el patrón `\w*` permite como máximo un solo token antes del `=`. En C++ válido, las variables `constexpr` llevan tipo (ej. `constexpr int WARP_SIZE = 32;`), lo que representa al menos dos palabras (`int` y `WARP_SIZE`) antes del `=`, haciendo que el regex **no matchee jamás** en código C++ real.
    3) Además, el subpatrón `.*warp` exige que la palabra "warp" aparezca *después* del número `32` (a la derecha del `=`), cuando en realidad en código C++ "warp" forma parte del nombre de la variable *antes* del `=`. *Nota: Esto forzó un workaround artificial en el fixture sintético en [wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52), donde se escribió `constexpr WARP = 32; int warp = WARP;` (sintaxis inválida en C++ sin tipo y con variable ficticia final) solo para que el test pudiera pasar.*
  - **Fix:** Requerir word boundary en 32 y permitir que el tipo y el identificador que contenga "warp" se ubiquen antes o después del signo de asignación:
    ```python
    _PATTERN_W07 = re.compile(
        r"(#define\s+\w*WARP\w*\s+32\b|constexpr\s+[^=]*warp[^=]*=\s*32\b)",
        re.IGNORECASE,
    )
    ```

END_AUDIT
VERDICT: CHANGES

### Auditoría Punto por Punto

#### 1. Despojado de comentarios (`//` y `/* */`) y strings
- **Preservación de saltos de línea (nº de línea y snippets):** El stripper preserva correctamente los saltos de línea (`\n`) en comentarios de línea, comentarios de bloque multilínea y literales simples, garantizando que los índices y números de línea 1-based coincidan con el código original.
- **Bug de correctness en saltos de línea escapados dentro de literales (cadenas y caracteres):** En los estados `STRING` y `CHAR` ([wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)), cuando se encuentra una barra invertida (`c == "\\"`), el código reemplaza tanto el carácter actual como el siguiente por espacios (`out[i] = " "; out[i + 1] = " "; i += 2`). Si una cadena o macro contiene una continuación de línea con salto de línea escapado (`\\\n`), **el carácter `\n` es reemplazado por un espacio**. Esto destruye el salto de línea, haciendo que `len(stripped_lines) < len(orig_lines)` y desfasando los números de línea (`lineno`) y los fragmentos (`_snippet`) de **todos** los hallazgos que ocurran después en ese archivo.
- **Comillas escapadas y comentarios multilínea:** El manejo de `/* */` multilínea es correcto. El escape de comillas (`\"` y `\'`) dentro de strings funciona adecuadamente.
- **Tests negativos:** Se verificó en [test_wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/test_wave64.py) y en el fixture [wave64_patterns.cu](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu) que los tests negativos son reales y validan eficazmente que un `W01` o `W06` dentro de comentarios o literales no sea reportado.

#### 2. Catálogo §5.2, Severidad y Explicaciones
- Las 7 expresiones regulares coinciden con el catálogo §5.2 del blueprint.
- La severidad asignada es exactamente la estipulada: `W01`-`W03` como `correctness` y `W04`-`W07` como `suspicious`.
- El atributo `explanation` es un string fijo y determinista, copiado textualmente del blueprint sin ninguna intervención o generación dinámica de LLM.

#### 3. Guarda de W05 (`_W05_LINE_GUARD`)
- Verificado: `_W05_LINE_GUARD.search(line)` ([wave64.py:210](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L210)) se evalúa antes que `_PATTERN_W05.finditer(line)`, asegurando que `W05` solo se dispare en líneas que contengan explícitamente `threadIdx`, `laneId` o `lane_id`, y no en cualquier operación mod/div sobre el número 32 en el resto del código.

#### 4. Snippets y Metadatos
- El helper `_snippet` ([wave64.py:145-148](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L145-L148)) calcula correctamente la ventana de contexto como la línea central $\pm 2$ (`max(0, idx - 2)` hasta `min(len(orig_lines), idx + 3)`).
- Los atributos `pattern_id`, `file` y `line` (1-based mediante `idx + 1`) son asignados correctamente en el modelo Pydantic `Wave64Finding`.

#### 5. Layering y Pureza L2
- Verificado: [wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py) importa únicamente `re` (de la stdlib) y `Wave64Finding` desde `core.schemas`. No hay violaciones de layering ni importaciones de configuración, fases u otros módulos de arquitectura.

---

### Hallazgos de Correctness y Catálogo (Severidad + Archivo:Línea + Fix)

- **[correctness] [orchestrator/core/wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [orchestrator/core/wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)**
  - **Problema:** En el stripper, al procesar secuencias de escape (`\\`) en los estados `STRING` y `CHAR`, se reemplazan `source[i]` y `source[i + 1]` con espacios intencionadamente para saltar comillas escapadas. Sin embargo, si `source[i + 1]` es un salto de línea (`\n`, común en macros o strings multilínea con continuación `\`), el salto de línea es borrado. Esto desfasa el conteo de líneas de `stripped_lines` respecto a `orig_lines`, corrompiendo el número de línea y el snippet de los hallazgos posteriores.
  - **Fix:** Verificar que el carácter escapado no sea un salto de línea antes de sobrescribirlo con espacio:
    ```python
    if c == "\\" and i + 1 < n:
        out[i] = " "
        if source[i + 1] != "\n":
            out[i + 1] = " "
        i += 2
    ```

- **[correctness] [orchestrator/core/wave64.py:34](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L34)**
  - **Problema (W01 - Falso Negativo y Falso Positivo):** `_PATTERN_W01` (`r"__ballot(_sync)?\s*\(\s*0xffffffff"`) no utiliza `re.IGNORECASE`. Si en el código CUDA/HIP se escribe la máscara en mayúsculas (`0xFFFFFFFF`), el linter no la detecta (Falso Negativo). Asimismo, al carecer de delimitador de fin de palabra, matchearía por prefijo máscaras inválidas o más largas como `0xffffffff0` (Falso Positivo).
  - **Fix:** Añadir delimitador al final o compilar con `re.IGNORECASE`:
    ```python
    _PATTERN_W01 = re.compile(r"__ballot(_sync)?\s*\(\s*0x[fF]{8}\b")
    ```

- **[correctness] [orchestrator/core/wave64.py:35](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L35)**
  - **Problema (W02 - Falso Positivo con enteros de 64 bits):** El patrón `r"(unsigned|uint32_t|int)\s+\w+\s*=\s*__ballot"` no evita coincidir dentro de tipos más amplios. En declaraciones como `unsigned long int mask = __ballot(...)` o `long int x = __ballot(...)` (donde en x86_64 Linux/HIP `long int` es de 64 bits), la subcadena `int mask = __ballot` o `int x = __ballot` genera un match, reportando erróneamente truncamiento a 32 bits en variables de 64 bits (Falso Positivo). También omite tipos muy comunes como `uint`, `int32_t` o `auto` (Falso Negativo).
  - **Fix:** Añadir word boundaries, impedir que anteceda la palabra `long` y ampliar los tipos cubiertos:
    ```python
    _PATTERN_W02 = re.compile(r"(?<!\blong\s)\b(unsigned(\s+int)?|uint32_t|int32_t|int|uint|auto)\s+\w+\s*=\s*__ballot")
    ```

- **[suspicious] [orchestrator/core/wave64.py:37](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L37)**
  - **Problema (W04 - Falso Positivo en argumentos previos):** El subpatrón `\([^)]*\b32\b` busca el token `32` en *cualquier* argumento dentro de los paréntesis de `__shfl...`. Si un kernel usa correctamente el ancho `64` para wave64 en el último parámetro, pero pasa `32` en un argumento anterior (por ejemplo, en el delta de un desplazamiento: `__shfl_up_sync(mask, val, 32, 64)`, o en un índice de arreglo: `__shfl_sync(mask, arr[32], lane, 64)`), dispara W04 incorrectamente.
  - **Fix:** Asegurar que el `32` detectado corresponda efectivamente al parámetro de ancho (el último argumento antes de cerrar paréntesis):
    ```python
    _PATTERN_W04 = re.compile(r"__shfl(_up|_down|_xor)?(_sync)?\s*\([^)]*,\s*32\s*\)")
    ```

- **[suspicious] [orchestrator/core/wave64.py:38](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L38)**
  - **Problema (W05 - Falso Positivo por producto cartesiano):** La alternancia `(%|&|/|>>)\s*(32|31|5)\b` permite cualquier combinación de operador y número. Operaciones válidas que no asumen warp de 32 pero que están en líneas con `threadIdx` (ej. división por bloques de 5 elementos: `threadIdx.x / 5`, o `% 5`, `& 5`, `>> 32`) disparan W05 erróneamente (Falso Positivo). Además, omite literales hexadecimales equivalentes como `& 0x1f` o `& 0x1F` (Falso Negativo).
  - **Fix:** Emparejar estrictamente cada operador aritmético con su operando de warp de 32 y permitir formato hexadecimal:
    ```python
    _PATTERN_W05 = re.compile(r"(?:[/%]\s*32|&\s*(?:31|0x1[fF])|>>\s*5)\b")
    ```

- **[suspicious] [orchestrator/core/wave64.py:39](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L39)**
  - **Problema (W06 - Falso Negativo en sobrecarga de función):** En Cooperative Groups, `tiled_partition` puede invocarse como plantilla (`cg::tiled_partition<32>(parent)`) o como función con tamaño en tiempo de ejecución (`cg::tiled_partition(parent, 32)`). El patrón actual solo cubre la sintaxis de plantilla `<32>`, ignorando la invocación funcional con tamaño 32.
  - **Fix:** Soportar ambas sobrecargas:
    ```python
    _PATTERN_W06 = re.compile(r"tiled_partition\s*(?:<\s*32\s*>|\([^)]*,\s*32\s*\))")
    ```

- **[suspicious] [orchestrator/core/wave64.py:40-43](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L40-L43) y [orchestrator/tests/fixtures/wave64/wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52)**
  - **Problema (W07 - Falsos Positivos por prefijo y bug de diseño en rama `constexpr`):**
    1) En `#define\s+WARP_SIZE\s+32` falta un word boundary al final, por lo que macros como `#define WARP_SIZE 320` disparan W07 por coincidencia de prefijo (Falso Positivo).
    2) En la rama `constexpr\s+\w*\s*=\s*32.*warp`, el patrón `\w*` permite como máximo un solo token antes del `=`. En C++ válido, las variables `constexpr` llevan tipo (ej. `constexpr int WARP_SIZE = 32;`), lo que representa al menos dos palabras (`int` y `WARP_SIZE`) antes del `=`, haciendo que el regex **no matchee jamás** en código C++ real.
    3) Además, el subpatrón `.*warp` exige que la palabra "warp" aparezca *después* del número `32` (a la derecha del `=`), cuando en realidad en código C++ "warp" forma parte del nombre de la variable *antes* del `=`. *Nota: Esto forzó un workaround artificial en el fixture sintético en [wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52), donde se escribió `constexpr WARP = 32; int warp = WARP;` (sintaxis inválida en C++ sin tipo y con variable ficticia final) solo para que el test pudiera pasar.*
  - **Fix:** Requerir word boundary en 32 y permitir que el tipo y el identificador que contenga "warp" se ubiquen antes o después del signo de asignación:
    ```python
    _PATTERN_W07 = re.compile(
        r"(#define\s+\w*WARP\w*\s+32\b|constexpr\s+[^=]*warp[^=]*=\s*32\b)",
        re.IGNORECASE,
    )
    ```

END_AUDIT
VERDICT: CHANGES

### Auditoría Punto por Punto

#### 1. Despojado de comentarios (`//` y `/* */`) y strings
- **Preservación de saltos de línea (nº de línea y snippets):** El stripper preserva correctamente los saltos de línea (`\n`) en comentarios de línea, comentarios de bloque multilínea y literales simples, garantizando que los índices y números de línea 1-based coincidan con el código original.
- **Bug de correctness en saltos de línea escapados dentro de literales (cadenas y caracteres):** En los estados `STRING` y `CHAR` ([wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)), cuando se encuentra una barra invertida (`c == "\\"`), el código reemplaza tanto el carácter actual como el siguiente por espacios (`out[i] = " "; out[i + 1] = " "; i += 2`). Si una cadena o macro contiene una continuación de línea con salto de línea escapado (`\\\n`), **el carácter `\n` es reemplazado por un espacio**. Esto destruye el salto de línea, haciendo que `len(stripped_lines) < len(orig_lines)` y desfasando los números de línea (`lineno`) y los fragmentos (`_snippet`) de **todos** los hallazgos que ocurran después en ese archivo.
- **Comillas escapadas y comentarios multilínea:** El manejo de `/* */` multilínea es correcto. El escape de comillas (`\"` y `\'`) dentro de strings funciona adecuadamente.
- **Tests negativos:** Se verificó en [test_wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/test_wave64.py) y en el fixture [wave64_patterns.cu](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu) que los tests negativos son reales y validan eficazmente que un `W01` o `W06` dentro de comentarios o literales no sea reportado.

#### 2. Catálogo §5.2, Severidad y Explicaciones
- Las 7 expresiones regulares coinciden con el catálogo §5.2 del blueprint.
- La severidad asignada es exactamente la estipulada: `W01`-`W03` como `correctness` y `W04`-`W07` como `suspicious`.
- El atributo `explanation` es un string fijo y determinista, copiado textualmente del blueprint sin ninguna intervención o generación dinámica de LLM.

#### 3. Guarda de W05 (`_W05_LINE_GUARD`)
- Verificado: `_W05_LINE_GUARD.search(line)` ([wave64.py:210](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L210)) se evalúa antes que `_PATTERN_W05.finditer(line)`, asegurando que `W05` solo se dispare en líneas que contengan explícitamente `threadIdx`, `laneId` o `lane_id`, y no en cualquier operación mod/div sobre el número 32 en el resto del código.

#### 4. Snippets y Metadatos
- El helper `_snippet` ([wave64.py:145-148](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L145-L148)) calcula correctamente la ventana de contexto como la línea central $\pm 2$ (`max(0, idx - 2)` hasta `min(len(orig_lines), idx + 3)`).
- Los atributos `pattern_id`, `file` y `line` (1-based mediante `idx + 1`) son asignados correctamente en el modelo Pydantic `Wave64Finding`.

#### 5. Layering y Pureza L2
- Verificado: [wave64.py](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py) importa únicamente `re` (de la stdlib) y `Wave64Finding` desde `core.schemas`. No hay violaciones de layering ni importaciones de configuración, fases u otros módulos de arquitectura.

---

### Hallazgos de Correctness y Catálogo (Severidad + Archivo:Línea + Fix)

- **[correctness] [orchestrator/core/wave64.py:109-112](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L109-L112) y [orchestrator/core/wave64.py:124-127](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L124-L127)**
  - **Problema:** En el stripper, al procesar secuencias de escape (`\\`) en los estados `STRING` y `CHAR`, se reemplazan `source[i]` y `source[i + 1]` con espacios intencionadamente para saltar comillas escapadas. Sin embargo, si `source[i + 1]` es un salto de línea (`\n`, común en macros o strings multilínea con continuación `\`), el salto de línea es borrado. Esto desfasa el conteo de líneas de `stripped_lines` respecto a `orig_lines`, corrompiendo el número de línea y el snippet de los hallazgos posteriores.
  - **Fix:** Verificar que el carácter escapado no sea un salto de línea antes de sobrescribirlo con espacio:
    ```python
    if c == "\\" and i + 1 < n:
        out[i] = " "
        if source[i + 1] != "\n":
            out[i + 1] = " "
        i += 2
    ```

- **[correctness] [orchestrator/core/wave64.py:34](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L34)**
  - **Problema (W01 - Falso Negativo y Falso Positivo):** `_PATTERN_W01` (`r"__ballot(_sync)?\s*\(\s*0xffffffff"`) no utiliza `re.IGNORECASE`. Si en el código CUDA/HIP se escribe la máscara en mayúsculas (`0xFFFFFFFF`), el linter no la detecta (Falso Negativo). Asimismo, al carecer de delimitador de fin de palabra, matchearía por prefijo máscaras inválidas o más largas como `0xffffffff0` (Falso Positivo).
  - **Fix:** Añadir delimitador al final o compilar con `re.IGNORECASE`:
    ```python
    _PATTERN_W01 = re.compile(r"__ballot(_sync)?\s*\(\s*0x[fF]{8}\b")
    ```

- **[correctness] [orchestrator/core/wave64.py:35](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L35)**
  - **Problema (W02 - Falso Positivo con enteros de 64 bits):** El patrón `r"(unsigned|uint32_t|int)\s+\w+\s*=\s*__ballot"` no evita coincidir dentro de tipos más amplios. En declaraciones como `unsigned long int mask = __ballot(...)` o `long int x = __ballot(...)` (donde en x86_64 Linux/HIP `long int` es de 64 bits), la subcadena `int mask = __ballot` o `int x = __ballot` genera un match, reportando erróneamente truncamiento a 32 bits en variables de 64 bits (Falso Positivo). También omite tipos muy comunes como `uint`, `int32_t` o `auto` (Falso Negativo).
  - **Fix:** Añadir word boundaries, impedir que anteceda la palabra `long` y ampliar los tipos cubiertos:
    ```python
    _PATTERN_W02 = re.compile(r"(?<!\blong\s)\b(unsigned(\s+int)?|uint32_t|int32_t|int|uint|auto)\s+\w+\s*=\s*__ballot")
    ```

- **[suspicious] [orchestrator/core/wave64.py:37](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L37)**
  - **Problema (W04 - Falso Positivo en argumentos previos):** El subpatrón `\([^)]*\b32\b` busca el token `32` en *cualquier* argumento dentro de los paréntesis de `__shfl...`. Si un kernel usa correctamente el ancho `64` para wave64 en el último parámetro, pero pasa `32` en un argumento anterior (por ejemplo, en el delta de un desplazamiento: `__shfl_up_sync(mask, val, 32, 64)`, o en un índice de arreglo: `__shfl_sync(mask, arr[32], lane, 64)`), dispara W04 incorrectamente.
  - **Fix:** Asegurar que el `32` detectado corresponda efectivamente al parámetro de ancho (el último argumento antes de cerrar paréntesis):
    ```python
    _PATTERN_W04 = re.compile(r"__shfl(_up|_down|_xor)?(_sync)?\s*\([^)]*,\s*32\s*\)")
    ```

- **[suspicious] [orchestrator/core/wave64.py:38](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L38)**
  - **Problema (W05 - Falso Positivo por producto cartesiano):** La alternancia `(%|&|/|>>)\s*(32|31|5)\b` permite cualquier combinación de operador y número. Operaciones válidas que no asumen warp de 32 pero que están en líneas con `threadIdx` (ej. división por bloques de 5 elementos: `threadIdx.x / 5`, o `% 5`, `& 5`, `>> 32`) disparan W05 erróneamente (Falso Positivo). Además, omite literales hexadecimales equivalentes como `& 0x1f` o `& 0x1F` (Falso Negativo).
  - **Fix:** Emparejar estrictamente cada operador aritmético con su operando de warp de 32 y permitir formato hexadecimal:
    ```python
    _PATTERN_W05 = re.compile(r"(?:[/%]\s*32|&\s*(?:31|0x1[fF])|>>\s*5)\b")
    ```

- **[suspicious] [orchestrator/core/wave64.py:39](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L39)**
  - **Problema (W06 - Falso Negativo en sobrecarga de función):** En Cooperative Groups, `tiled_partition` puede invocarse como plantilla (`cg::tiled_partition<32>(parent)`) o como función con tamaño en tiempo de ejecución (`cg::tiled_partition(parent, 32)`). El patrón actual solo cubre la sintaxis de plantilla `<32>`, ignorando la invocación funcional con tamaño 32.
  - **Fix:** Soportar ambas sobrecargas:
    ```python
    _PATTERN_W06 = re.compile(r"tiled_partition\s*(?:<\s*32\s*>|\([^)]*,\s*32\s*\))")
    ```

- **[suspicious] [orchestrator/core/wave64.py:40-43](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/core/wave64.py#L40-L43) y [orchestrator/tests/fixtures/wave64/wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52)**
  - **Problema (W07 - Falsos Positivos por prefijo y bug de diseño en rama `constexpr`):**
    1) En `#define\s+WARP_SIZE\s+32` falta un word boundary al final, por lo que macros como `#define WARP_SIZE 320` disparan W07 por coincidencia de prefijo (Falso Positivo).
    2) En la rama `constexpr\s+\w*\s*=\s*32.*warp`, el patrón `\w*` permite como máximo un solo token antes del `=`. En C++ válido, las variables `constexpr` llevan tipo (ej. `constexpr int WARP_SIZE = 32;`), lo que representa al menos dos palabras (`int` y `WARP_SIZE`) antes del `=`, haciendo que el regex **no matchee jamás** en código C++ real.
    3) Además, el subpatrón `.*warp` exige que la palabra "warp" aparezca *después* del número `32` (a la derecha del `=`), cuando en realidad en código C++ "warp" forma parte del nombre de la variable *antes* del `=`. *Nota: Esto forzó un workaround artificial en el fixture sintético en [wave64_patterns.cu:52](file:///Volumes/MacMiniExt/dev/ZedProjects/HIPnosis-t6/orchestrator/tests/fixtures/wave64/wave64_patterns.cu#L52), donde se escribió `constexpr WARP = 32; int warp = WARP;` (sintaxis inválida en C++ sin tipo y con variable ficticia final) solo para que el test pudiera pasar.*
  - **Fix:** Requerir word boundary en 32 y permitir que el tipo y el identificador que contenga "warp" se ubiquen antes o después del signo de asignación:
    ```python
    _PATTERN_W07 = re.compile(
        r"(#define\s+\w*WARP\w*\s+32\b|constexpr\s+[^=]*warp[^=]*=\s*32\b)",
        re.IGNORECASE,
    )
    ```

END_AUDIT
