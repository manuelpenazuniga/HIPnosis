Revisá MI código pre-merge por bugs de correctness/contrato. NO modifiques nada: solo LEÉ y REPORTÁ.
Archivos: orchestrator/core/oracle/base.py, orchestrator/core/oracle/mock.py, orchestrator/tests/test_oracle_mock.py
Contexto: oracle = superficie de ejecución del pipeline (build/run del repo objetivo). mock replay fixtures.
Verificá punto por punto:
1. base.py define Oracle abstracto con build()->BuildResult y run()->RunResult (tipos importados de core.schemas, NO redefinidos).
2. MockOracle.build() es SECUENCIAL y determinista: 1ª llamada build_01, 2ª build_02, etc.; la ÚLTIMA fixture es clean (count=0, ok=True); llamar de más sigue devolviendo la clean (no explota ni cicla).
3. count = conteo CRUDO de líneas ': error:'/': fatal error:' (NO usa taxonomía ni errparse). ok=(count==0). returncode coherente.
4. INV-6: mock respeta el MISMO contrato que un real (mismas firmas/tipos). ¿Alguna fuga de abstracción?
5. Layering: oracle NO importa phases/llm/state/errparse. Reportá cualquier import prohibido.
6. Casos borde: dir de fixtures vacío, archivo faltante, build() llamado 0 veces, run.txt ausente (debe dar "PASS").
Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`; por hallazgo severidad+archivo:línea+fix; ÚLTIMA línea `END_AUDIT`.
