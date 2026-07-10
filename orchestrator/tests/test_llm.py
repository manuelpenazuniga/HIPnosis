"""tests/test_llm.py — pure L2 tests for ``core.llm``.

These tests are the regression fence around the LLM layer
(blueprint §6.4 / §6.5). No network: ``httpx`` is replaced by a
``MockTransport`` and the client's backoff sleep is monkeypatched so
the suite runs in milliseconds.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from core.config import Config
from core.llm import client as client_mod
from core.llm import router
from core.llm.client import LLMClient, LLMError, LLMResponse
from core.llm.prompts import render_classifier, render_fixer


# --- helpers -------------------------------------------------------------


def _make_response(
    text: str = "ok",
    prompt_tokens: int = 3,
    completion_tokens: int = 4,
) -> dict[str, Any]:
    return {
        "id": "cmpl-test",
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _transport(handler):
    return httpx.MockTransport(handler)


# Bound at import time so the factory below can call the *real*
# ``httpx.Client`` even while the attribute is patched on the module.
_RealClient = httpx.Client


def _make_client_factory(transport):
    """Return a stand-in for ``httpx.Client`` wired to ``transport``."""

    def factory(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return _RealClient(*args, **kwargs)

    return factory


def _capturing_handler(
    text: str = "ok",
    status: int = 200,
    raise_request_exc: Exception | None = None,
):
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        try:
            captured["body"] = json.loads(request.content.decode("utf-8"))
        except Exception:
            captured["body"] = request.content
        if raise_request_exc is not None:
            raise raise_request_exc
        return httpx.Response(status, json=_make_response(text=text))

    return handler, captured


# --- client.complete -----------------------------------------------------


def test_complete_sends_openai_payload_and_parses_tokens() -> None:
    handler, captured = _capturing_handler(text="hello world")
    transport = _transport(handler)

    with patch.object(client_mod.httpx, "Client", _make_client_factory(transport)):
        c = LLMClient(
            base_url="http://vllm:8000/v1", model="google/gemma-3-27b-it"
        )
        resp = c.complete("sys", "usr")

    assert resp == LLMResponse(text="hello world", tokens=7)
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/chat/completions")
    body = captured["body"]
    assert body["model"] == "google/gemma-3-27b-it"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert body["temperature"] == pytest.approx(0.1)
    assert "authorization" not in {k.lower() for k in captured["headers"]}


def test_complete_adds_bearer_header_when_api_key_set() -> None:
    handler, captured = _capturing_handler(text="hi")
    transport = _transport(handler)

    with patch.object(client_mod.httpx, "Client", _make_client_factory(transport)):
        c = LLMClient(
            base_url="https://api.fireworks.ai/inference/v1",
            model="accounts/fireworks/models/qwen3-coder",
            api_key="sk-test",
        )
        c.complete("s", "u")

    assert captured["headers"]["authorization"] == "Bearer sk-test"


def test_complete_retries_on_429_then_succeeds() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=_make_response(text="recovered"))

    transport = _transport(handler)
    with patch.object(client_mod, "_sleep", lambda s: sleeps.append(s)), \
         patch.object(client_mod.httpx, "Client", _make_client_factory(transport)):
        c = LLMClient(
            base_url="http://vllm:8000/v1",
            model="m",
            max_retries=3,
            backoff_base_s=0.5,
        )
        resp = c.complete("s", "u")

    assert resp.text == "recovered"
    assert calls["n"] == 2
    assert sleeps, "backoff sleep must run between retries"
    assert sleeps[0] == pytest.approx(0.5)


def test_complete_retries_on_5xx_then_raises_after_budget() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "down"})

    transport = _transport(handler)
    with patch.object(client_mod, "_sleep", lambda s: sleeps.append(s)), \
         patch.object(client_mod.httpx, "Client", _make_client_factory(transport)):
        c = LLMClient(
            base_url="http://vllm:8000/v1",
            model="m",
            max_retries=2,
            backoff_base_s=0.1,
        )
        with pytest.raises(LLMError):
            c.complete("s", "u")

    # initial + 2 retries = 3 calls
    assert calls["n"] == 3
    assert len(sleeps) == 2


def test_complete_estimates_tokens_when_usage_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "abc"}}],
                # no usage field
            },
        )

    transport = _transport(handler)
    with patch.object(client_mod.httpx, "Client", _make_client_factory(transport)):
        c = LLMClient(base_url="http://vllm:8000/v1", model="m")
        resp = c.complete("s", "u")

    assert resp.text == "abc"
    # 3 chars / 4 = 0 → floored to 1 by the estimator
    assert resp.tokens == 1


def test_complete_strips_trailing_slash_on_base_url() -> None:
    handler, captured = _capturing_handler()
    transport = _transport(handler)
    with patch.object(client_mod.httpx, "Client", _make_client_factory(transport)):
        c = LLMClient(base_url="http://vllm:8000/v1/", model="m")
        c.complete("s", "u")
    assert captured["url"].endswith("/chat/completions")
    assert "//chat" not in captured["url"]


def test_client_ctor_rejects_empty_base_url_or_model() -> None:
    with pytest.raises(ValueError):
        LLMClient(base_url="", model="m")
    with pytest.raises(ValueError):
        LLMClient(base_url="http://x", model="")


# --- router --------------------------------------------------------------


def _cfg(**overrides: Any) -> Config:
    base = dict(
        oracle_mode="mock",
        local_llm_base_url="http://vllm:8000/v1",
        local_llm_model="google/gemma-3-27b-it",
        remote_llm_base_url="https://api.fireworks.ai/inference/v1",
        remote_llm_model="accounts/fireworks/models/qwen3-coder",
        fireworks_api_key="sk-fw",
        hf_token="",
        github_token="",
        gpu_arch="gfx942",
        max_iterations=25,
        max_attempts_per_group=3,
        max_errors_parsed=30,
        confidence_threshold=0.6,
        price_h100_hr=0.0,
        price_mi300x_hr=0.0,
    )
    base.update(overrides)
    return Config(**base)


@pytest.mark.parametrize(
    "strategy,attempts,tier_sugerido,expected",
    [
        ("deterministic", 0, None, "deterministic"),
        ("deterministic", 0, "local", "deterministic"),
        ("deterministic", 2, "remote", "deterministic"),
        ("llm", 0, "local", "local"),
        ("llm", 0, None, "remote"),
        ("llm", 0, "remote", "remote"),
        ("llm", 1, "local", "remote"),
        ("llm", 2, "local", "remote"),
        # P1 (audit codex): local_then_remote prueba local en el 1er intento,
        # remoto en los siguientes (antes saltaba directo a remoto).
        ("llm", 0, "local_then_remote", "local"),
        ("llm", 1, "local_then_remote", "remote"),
    ],
)
def test_decide_tier_table(strategy, attempts, tier_sugerido, expected):
    assert router.decide_tier(strategy, attempts, tier_sugerido) == expected


def test_client_for_tier_local_uses_local_config() -> None:
    cfg = _cfg()
    c = router.client_for_tier("local", cfg)
    assert c._base_url == cfg.local_llm_base_url
    assert c._model == cfg.local_llm_model
    assert c._api_key == ""


def test_client_for_tier_remote_uses_remote_config_and_key() -> None:
    cfg = _cfg()
    c = router.client_for_tier("remote", cfg)
    assert c._base_url == cfg.remote_llm_base_url
    assert c._model == cfg.remote_llm_model
    assert c._api_key == cfg.fireworks_api_key == "sk-fw"


def test_client_for_tier_deterministic_raises() -> None:
    cfg = _cfg()
    with pytest.raises(ValueError):
        router.client_for_tier("deterministic", cfg)


def test_client_for_tier_unknown_tier_raises() -> None:
    cfg = _cfg()
    with pytest.raises(ValueError):
        router.client_for_tier("nope", cfg)


# --- prompts -------------------------------------------------------------


def test_render_classifier_substitutes_placeholders_and_caps_messages() -> None:
    sys, user = render_classifier(
        clases_tabla="E01|missing-include|header CUDA sin hipificar",
        mensajes=[f"err{i}" for i in range(8)],  # 8 → cap to 5
        snippet="line1\nline2",
    )
    assert sys and "HIP/ROCm" in sys
    assert "E01|missing-include|header CUDA sin hipificar" in user
    # only first 5 appear
    for i in range(5):
        assert f"err{i}" in user
    assert "err5" not in user and "err7" not in user
    assert "line1" in user and "line2" in user
    assert "Responde SOLO JSON" in user


def test_render_classifier_handles_empty_messages() -> None:
    sys, user = render_classifier("CLASES", [], "snip")
    assert "(sin mensajes)" in user


def test_render_fixer_substitutes_placeholders() -> None:
    sys, user = render_fixer(
        error_msgs=["e1", "e2"],
        path="src/k.cu",
        code_window="int x = 0;",
        a=10,
        b=40,
        total=120,
        class_notes="CLASS_NOTES_HERE",
        history="",
    )
    assert sys and "wavefront de 64" in sys
    for needle in (
        "CLASS_NOTES_HERE",
        "ARCHIVO src/k.cu (líneas 10-40 de 120)",
        "int x = 0;",
        "- e1",
        "- e2",
        "__popcll",
        "FILE/SEARCH/REPLACE",
    ):
        assert needle in user
    # no history block when not provided
    assert "HISTORIAL" not in user


def test_render_fixer_includes_history_block_when_provided() -> None:
    _, user = render_fixer(
        error_msgs=["boom"],
        path="k.cu",
        code_window="x",
        a=1,
        b=2,
        total=3,
        history="HISTORIAL: el intento anterior falló con X",
    )
    assert "HISTORIAL: el intento anterior falló con X" in user
