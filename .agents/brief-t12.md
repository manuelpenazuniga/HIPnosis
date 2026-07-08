Trabajás en el worktree actual (rama spike/t12-llm). Implementá SOLO esta tarea.

--- TAREA T12: core/llm/client.py + router.py + prompts.py — capa LLM (funciones puras) ---
Capa L2: importa core.schemas, core.config, httpx y stdlib. ⛔ NO importa oracle/phases/state.
INV-1: el LLM NO decide control; solo `clasificar(error)→clase` y `proponer_fix(...)→parche`.

ARCHIVOS: orchestrator/core/llm/client.py, orchestrator/core/llm/router.py, orchestrator/core/llm/prompts.py
TEST: orchestrator/tests/test_llm.py   (con httpx mockeado — NO llamadas de red reales)

### client.py — UN cliente OpenAI-compatible (base_url decide local vs remoto):
    @dataclass
    class LLMResponse:
        text: str
        tokens: int              # tokens totales reportados por la API (o estimado si falta)

    class LLMClient:
        def __init__(self, base_url: str, model: str, api_key: str = "", temperature: float = 0.1): ...
        def complete(self, system: str, user: str, timeout_s: float = 60.0) -> LLMResponse:
            # POST {base_url}/chat/completions con {model, messages:[system,user], temperature}.
            # Header Authorization: Bearer {api_key} si api_key no vacío.
            # Devuelve LLMResponse(text=choices[0].message.content, tokens=usage.total_tokens).
            # Backoff exponencial 3 reintentos ante 429/5xx (F-12). Usá httpx.Client.
        # NOTA: mismo cliente para local (vLLM/Gemma) y remoto (Fireworks) — cambia base_url+model+key
        # (esto hace trivial el fallback F-01). NO hardcodees URLs: vienen de config.

### router.py — política de tier (blueprint §6.4). FUNCIÓN PURA, sin red:
    def decide_tier(strategy: str, attempts: int, tier_sugerido: str | None) -> str:
        # Reglas §6.4:
        #   if strategy == "deterministic": return "deterministic"
        #   if attempts == 0 and tier_sugerido == "local": return "local"
        #   return "remote"     # 2º intento o clase dura → remoto
        # (el 3er intento fallido lo maneja el loop marcando needs_human; router no cuenta intentos duros)

    def client_for_tier(tier: str, config) -> LLMClient:
        # "local"  -> LLMClient(config.local_llm_base_url, config.local_llm_model)
        # "remote" -> LLMClient(config.remote_llm_base_url, config.remote_llm_model, config.fireworks_api_key)
        # "deterministic" -> no usa LLM (el caller no debería pedir cliente); lanzá ValueError si se pide.

### prompts.py — plantillas EXACTAS (blueprint §6.5). Solo strings/plantillas, sin lógica de red.
    CLASSIFIER_SYSTEM / CLASSIFIER_USER_TEMPLATE  (§6.5-A): pide SOLO JSON
        {"class":"E05","confidence":0.0-1.0,"rationale":"una frase"}. Incluí el placeholder para la
        tabla de clases, los mensajes del grupo (máx 5) y el snippet del primer error (±10 líneas).
    FIXER_SYSTEM / FIXER_USER_TEMPLATE  (§6.5-B): experto CUDA→HIP CDNA3 wavefront 64; reglas
        (cambiar lo mínimo, no refactorizar, __ballot 64 bits, __popcll, warpSize runtime, inyectar
        notas de la clase); pide SOLO bloques FILE/SEARCH/REPLACE, sin explicación; placeholders para
        error, path, ventana de código (a-b de total), y HISTORIAL si attempts>0.
    def render_classifier(clases_tabla: str, mensajes: list[str], snippet: str) -> tuple[str,str]:  # (system, user)
    def render_fixer(error_msgs: list[str], path: str, code_window: str, a: int, b: int, total: int,
                     class_notes: str = "", history: str = "") -> tuple[str,str]:
    ⛔ Todos los prompts viven ACÁ (INV-9). Ninguna otra capa arma prompts inline.

### Test test_llm.py (SIN red — mockeá httpx):
- LLMClient.complete: mockeá httpx para devolver una respuesta OpenAI-style; verificá que arma bien
  el payload (model, messages), parsea text y tokens. Simulá un 429 seguido de 200 → reintenta y
  devuelve el 200 (backoff, podés monkeypatchear el sleep para que no espere).
- decide_tier: los 3 caminos (deterministic; attempts0+local→local; else→remote). Test de tabla.
- client_for_tier: local→base_url local; remote→base_url remoto+key; deterministic→ValueError.
- render_classifier/render_fixer: devuelven (system,user) no vacíos con los placeholders sustituidos.

--- FIN TAREA ---

Criterios de aceptación:
1. `cd orchestrator && <VENV> -m pytest tests/test_llm.py -q` verde. NINGUNA llamada de red real en tests.
2. llm/* NO importa oracle/phases/state. base_url/model/key vienen de config (no hardcodeados).
3. Todos los prompts en prompts.py (INV-9). router.decide_tier implementa §6.4 exacto.

Reglas duras:
- INV-1: el LLM es función pura (clasificar/proponer_fix); no decide control de flujo.
- F-12: backoff 3 reintentos en 429/5xx. F-01: mismo cliente local/remoto (solo cambia base_url+model).
- Al terminar: pytest verde + COMMIT ("feat(llm): cliente OpenAI-compat + router de tier + prompts + tests").
- Respuesta CORTA: archivos + output pytest. Bloqueo: 'BLOCKED | ...' y pará.
