"""core.llm.client — primitive (L2): OpenAI-compatible HTTP client.

One client class for both local (vLLM / Gemma) and remote (Fireworks)
inference. The ONLY differences between the two deployments are
``base_url``, ``model`` and ``api_key`` — this is what makes the
fallback chain in blueprint F-01 trivial: the loop just swaps config.

Layering: L2 primitive. Imports only ``core.schemas``-adjacent types
plus stdlib and ``httpx``. No reference to ``phases``, ``oracle`` or
``state`` (INV-1: the LLM is a pure function, control lives elsewhere).

Reliability (F-12): exponential backoff on 429 / 5xx, up to 3 retries.
The sleep is delegated to ``_sleep`` so tests can freeze it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tokens: int


_sleep = __import__("time").sleep


class LLMError(RuntimeError):
    """Raised when the upstream LLM is unreachable after all retries."""


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        temperature: float = 0.1,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not model:
            raise ValueError("model is required")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s

    def complete(
        self,
        system: str,
        user: str,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        url = f"{self._base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(timeout=timeout_s) as client:
                    resp = client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    break
                _sleep(self._backoff_base_s * (2**attempt))
                continue

            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt >= self._max_retries:
                    raise LLMError(
                        f"LLM {resp.status_code} after {self._max_retries + 1} attempts"
                    )
                _sleep(self._backoff_base_s * (2**attempt))
                continue

            if resp.status_code >= 400:
                raise LLMError(
                    f"LLM {resp.status_code}: {resp.text[:500]}"
                )

            return _parse_response(resp.json(), self._model)

        raise LLMError(
            f"LLM unreachable after {self._max_retries + 1} attempts: {last_exc}"
        )


def _parse_response(body: dict[str, Any], model: str) -> LLMResponse:
    try:
        choices = body["choices"]
        text = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Malformed LLM response from {model}: {exc}") from exc

    usage = body.get("usage") or {}
    tokens = usage.get("total_tokens")
    if not isinstance(tokens, int) or tokens < 0:
        tokens = _estimate_tokens(text)

    return LLMResponse(text=str(text), tokens=int(tokens))


def _estimate_tokens(text: str) -> int:
    # Cheap fallback: ~4 chars/token (English / code mix). The dashboard
    # exposes the real ``usage`` field when the API provides it; this is
    # only the last-resort number for the counters.
    return max(1, len(text) // 4)
