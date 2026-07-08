Revisá MI código pre-merge por bugs de correctness. NO modifiques nada: solo LEÉ y REPORTÁ.
Archivos: orchestrator/core/errparse.py, orchestrator/tests/test_errparse.py + fixtures en tests/fixtures/errparse/
Contexto: errparse convierte salida de compilador en grupos de errores; la SIGNATURE es la clave del historial anti-loop.
Verificá punto por punto (CRÍTICO el punto 2):
1. parse(): el regex ^(file):(line):(col): (error|fatal error): (msg)$ captura bien; toma máx max_errors (default 30); líneas de linker 'undefined reference' → BuildError file="<link>".
2. signature() NORMALIZACIÓN EXACTA: números→'#', hex(0x..)→'@', PERO contenido entre comillas simples SE CONSERVA. Verificá con casos:
   - "expected 42 args" y "expected 7 args" → MISMA signature (números normalizados).
   - "undeclared identifier 'cudaMemcpy'" vs "'cudaFree'" → signatures DISTINTAS (identificador conservado).
   ¿El orden de normalización rompe algún caso (p.ej. un número dentro de comillas simples)? Reportalo.
3. group(): agrupa por signature aunque los archivos difieran (header roto → N archivos → 1 grupo); ordena por nº de errores DESC.
4. ErrorGroup/BuildError importados de core.schemas (no redefinidos). Umbral max_errors viene de parámetro (config), no hardcodeado en lógica.
5. Layering: errparse NO importa phases/oracle/llm/state.
6. Casos borde: raw vacío, error sin columna, msg con múltiples comillas simples, cascada >30.
Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`; por hallazgo severidad+archivo:línea+fix; ÚLTIMA línea `END_AUDIT`.
