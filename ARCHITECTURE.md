# Arquitectura — HIPnosis

> Diseño vivo (v3 §1.1). Fuente de verdad de implementación: `hipnosis-blueprint.md`.
> Los `AD`/`INV` de acá salen de la consulta de arranque al Arquitecto (2026-07-08).

## Mapa de módulos (dirección de dependencias = LEY)

```
L7  dashboard/            → NADA de Python. Solo contrato JSON (schemas §4 + eventos trace §4.3)
L6  app/main.py, api.py   → state, schemas, config, trace(reader)          [transporte HTTP]
L5  core/state.py         → phases/*, schemas, trace, config      [FSM+SQLite: ÚNICO driver de fases]
L4  core/phases/*,        → oracle, llm, gitrepo, errparse, wave64, taxonomy, patcher,
    core/report.py          manifest, buildsys, report, schemas, trace, config
L3  core/oracle/real,mock → oracle/base, schemas, config                   [ejecución]
L2  errparse, wave64, taxonomy(+rules.yaml), patcher, manifest, buildsys,
    llm/{client,router,prompts}, oracle/base, gitrepo → schemas, config    [primitivas puras]
L1  core/trace.py         → schemas                                        [JSONL append-only]
L0  core/config.py, core/schemas.py → NADA interno                         [hojas del grafo]
```

### Direcciones PROHIBIDAS (el panel externo no las ve: no conoce el mapa)
- `config`/`schemas` no importan nada interno (hojas → rompen ciclos, habilitan mock-first).
- `oracle/*` **nunca** importa `phases`, `llm`, `state`. Superficie de ejecución pura.
- `llm/*` **nunca** importa `oracle`, `phases`, `state`. Función pura.
- `app/api` **nunca** importa `phases`/`oracle` directo: todo control pasa por `state`.
- `report.py` **nunca** llama al LLM para producir números.
- `dashboard/` no importa Python; consume solo JSON.

## Decisiones (ADR-lite, append-only, NUNCA borrar — se supersede con una nueva)

AD-1 [2026-07-08] `config.py`/`schemas.py` son hojas (no importan nada interno) — por qué: contrato base; importar hacia arriba crea ciclos y rompe mock-first — descartado: schemas leyendo defaults de config (los límites viven en config y se pasan por argumento).
AD-2 [2026-07-08] `BuildResult`/`RunResult` se definen en `schemas.py`, no en `oracle/base.py` — por qué: contrato compartido por real/mock/loop/trace; evita que `phases` importe de `oracle` solo por tipos — descartado: tipos en `base.py` (acopla phases a oracle).
AD-3 [2026-07-08] `state.py` es el único driver de `phases`; `api` nunca llama fases inline — por qué: FSM como única autoridad de control (§0.1), habilita reanudación, testea el loop sin HTTP — descartado: api inline (imposible reanudar).
AD-4 [2026-07-08] `replay` vive en la capa `api` (pagina un trace grabado), NO es un oracle mode — por qué: replay no ejecuta pipeline (§9); como oráculo obligaría a fabricar fases falsas — descartado: replay como tercer oráculo.
AD-5 [2026-07-08] Dos tipos de fixture distintos: (a) `fixtures/<repo>/build_NN.txt` que `mock.py` replay (insumo de tests de loop); (b) `fixtures/demo-run.jsonl`, trace de `record_fixture.sh` para modo replay — descartado: un solo formato (conflación = bug latente).

## Invariantes (lo que NINGÚN cambio puede romper — van inline en cada brief que los roce)

INV-1: `llm/*` no decide control; solo `clasificar()→clase` y `proponer_fix()→parche`. (§0.1)
INV-2: El veredicto de éxito sale solo de `oracle/` + comparador numérico. Ningún LLM. (§0.2)
INV-3: Todo cambio al repo objetivo = commit atómico vía `gitrepo`; solo SEARCH/REPLACE con unicidad. (§0.3, §6.3)
INV-4: Evento al trace ANTES de actuar/transicionar. (§0.4, §3)
INV-5: No resuelto → `needs_human`; `DONE_PARTIAL` es final legítimo, nunca `FAILED`. (§0.5)
INV-6: `mock` y `real` = idéntico contrato de `oracle/base`; ninguna fase distingue el modo. (§0.6, §9)
INV-7: Números solo de código/JSON; el LLM redacta prosa que no puede alterar cifras. (F-17)
INV-8: Nombres de campo de `schemas §4` y `ev` del trace `§4.3` = contrato congelado; no se renombran sin AD.
INV-9: Umbrales solo en `config.py`; prompts solo en `prompts.py`. (§13.5)
INV-10: `MAX_ITERATIONS`/`MAX_ATTEMPTS_PER_GROUP` = cotas duras; nunca reintento infinito. (§6.4, F-06)
INV-11: El workspace nunca contiene la variante `-hip` oficial. (§7.2, anti-fuga)
INV-12: Dirección de capas del mapa; nunca al revés; `dashboard` no importa Python.

## Actualizaciones CP-1 [2026-07-08]
AD-4 (reforzada): `replay` pagina un trace grabado en capa `api`. Se agrega `fixtures/demo-run.jsonl`
  hand-authored (conforme §4.3, INV-8) para desacoplar el modo replay de que el loop grabe algo:
  la submission ejecutable NO depende del loop.
Gate de proceso (CP-1): "fixture-first" — ninguna primitiva del camino-loop mergea sin su fixture
  consumido commiteado al lado (build_NN.txt / demo-run.jsonl). Valida oráculos sin GPU.
Re-ruteo de modelos (CP-1): ola dura ALTO (T11 patcher, T14a/b loop, T15b paridad) → deepseek-v4-pro
  SERIALIZADO (uno a la vez). m3 → T7/T10/T12/T16; qwen3.7-plus → T18 dashboard.
