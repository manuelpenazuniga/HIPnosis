Revisá MI código pre-merge por bugs de correctness. NO modifiques nada: solo LEÉ y REPORTÁ.
Archivos: orchestrator/app/replay.py, orchestrator/app/main.py, orchestrator/app/api.py, orchestrator/app/store.py, orchestrator/tests/test_replay.py
Contexto: MODO REPLAY (AD-4). En ORACLE_MODE=replay se siembra un run grabado (fixtures/demo-run.jsonl) en el store y se sirve su trace con "timing acelerado" (drip-feed) por el endpoint GET /runs/{id}/events?after=N que ya usa el dashboard. Replay vive en capa app (NO es un oracle mode).
Verificá punto por punto:
1. ReplayClock: arranque LAZY (t0 en primer visible_count) evita el bug de reset-por-poll (el dashboard manda after=-1 hasta recibir eventos). visible_count monótono y saturado al total. ¿Algún caso donde retroceda o se pase del total?
2. Endpoint events en replay: retorna eventos con _i < visible_count filtrados por after. ¿La interacción after + visible_count es correcta (no saltea ni duplica al avanzar el reloj)? ¿Qué pasa si after >= visible? (debe dar []).
3. bootstrap_replay: siembra el run derivado del trace (id, state=última fase, counters del evento 'report' — F-17 números del trace, no inventados). Devuelve None si no es replay o no hay trace. ¿Casos borde: trace vacío, sin evento report, sin run_meta?
4. Layering L6 (AD-4): replay/api/main NO importan phases/oracle. store.put agregado para sembrar. ¿Rompe el protocolo RunStore?
5. AD-3: el control sigue pasando por el store; POST /runs no ejecuta pipeline.
6. ¿El modo no-replay quedó intacto (app.state.replay=None → rama vieja read_events(trace_path_for_run))?
Formato: PRIMERA línea `VERDICT: APPROVED` o `VERDICT: CHANGES`; por hallazgo severidad+archivo:línea+fix; ÚLTIMA línea `END_AUDIT`.
