Revisá MI código pre-merge por bugs de correctness/contrato. NO modifiques nada: solo LEÉ y REPORTÁ.
Archivos: orchestrator/app/api.py, orchestrator/app/main.py, orchestrator/app/store.py, orchestrator/tests/test_api.py
Contexto: capa HTTP FastAPI. El endpoint CLAVE es GET /runs/{id}/events?after=N (poll del dashboard/replay).
Verificá punto por punto:
1. GET /runs/{id}/events?after=N: usa core.trace.read_events (no reimplementa parseo); after default -1; trace inexistente → [] con 200 (no 404); el 'after' se pasa como int correctamente (query param).
2. POST /runs: crea run con id "run_"+hex, state QUEUED; NO ejecuta pipeline (AD-3: solo encola). GET /runs/{id} 404 si no existe.
3. AD-3 / layering L6: api NO importa phases ni oracle; el control pasa por el store. Reportá cualquier import prohibido.
4. main.py: monta StaticFiles del dashboard SIN fallar si el dir no existe; incluye el router; inyecta el store.
5. store.py InMemoryRunStore: create/get/list coherentes; id colisiones improbables; budgets/counters desde schemas/config.
6. Casos borde: after mayor que el nº de eventos → []; run_id con caracteres raros; POST sin repo_url → 422.
Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`; por hallazgo severidad+archivo:línea+fix; ÚLTIMA línea `END_AUDIT`.
