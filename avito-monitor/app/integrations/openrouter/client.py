"""Thin AsyncOpenAI-based client for OpenRouter.

Why a wrapper instead of using ``AsyncOpenAI`` directly:

* OpenRouter expects the ``HTTP-Referer`` + ``X-Title`` headers so the
  call shows up correctly in their dashboard. The vanilla SDK doesn't
  set these, so we inject them via ``default_headers``.
* We need a single normalised :class:`LLMResponse` object — the SDK
  returns chat completion shape with ``usage.prompt_tokens`` etc.,
  and our analyzer wants a flat dict-like result with ``cost_usd``
  and ``latency_ms`` already filled.
* Cost is computed locally via ``pricing.estimate_cost_usd`` because
  some upstream providers don't include cost in their usage payload.

The client is intentionally stateless beyond the underlying httpx
connection pool — feed it a model and a list of messages, get back
content + usage + cost. Caching, prompt rendering, schema parsing all
live one layer up in :mod:`app.services.llm_analyzer`.
"""
from __future__ import annotations

import time
from typing import Any

from openai import AsyncOpenAI
from openai import APIError, APIConnectionError, RateLimitError

from app.integrations.openrouter.pricing import estimate_cost_usd
from shared.models.llm import LLMResponse

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter returns a 4xx/5xx or transport fails."""

    def __init__(
        self, message: str, *, status_code: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class OpenRouterClient:
    """Tiny ``AsyncOpenAI`` wrapper that returns :class:`LLMResponse`."""

    def __init__(
        self,
        api_key: str,
        *,
        app_base_url: str = "http://localhost:8000",
        app_title: str = "Avito Monitor",
        timeout_seconds: float = 60.0,
        # Inject for tests; in prod we make our own.
        client: AsyncOpenAI | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        self._api_key = api_key
        self._app_base_url = app_base_url
        self._app_title = app_title
        self._timeout = timeout_seconds
        self._client_override = client

    def _make_client(self) -> AsyncOpenAI:
        if self._client_override is not None:
            return self._client_override
        return AsyncOpenAI(
            api_key=self._api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=self._timeout,
            default_headers={
                "HTTP-Referer": self._app_base_url,
                "X-Title": self._app_title,
            },
        )

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str | list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Run one chat-completion expecting a JSON object response.

        ``user_content`` may be a string (plain text) or an OpenAI-style
        content array (``[{"type": "text", "text": ...}, {"type":
        "image_url", "image_url": {...}}]``) for multimodal prompts.

        We always pass ``response_format={"type": "json_object"}`` so the
        analyzer can :func:`json.loads` ``LLMResponse.content`` without
        defensive trimming.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        client = self._make_client()
        owns_client = self._client_override is None
        start = time.monotonic()
        try:
            try:
                completion = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            except RateLimitError as exc:
                raise OpenRouterError(
                    f"openrouter rate limited: {exc}",
                    status_code=429,
                    retryable=True,
                ) from exc
            except APIConnectionError as exc:
                raise OpenRouterError(
                    f"openrouter transport error: {exc}",
                    retryable=True,
                ) from exc
            except APIError as exc:
                status = getattr(exc, "status_code", None)
                raise OpenRouterError(
                    f"openrouter api error: {exc}",
                    status_code=status,
                    retryable=bool(status and status >= 500),
                ) from exc

            latency_ms = int((time.monotonic() - start) * 1000)

            choice = completion.choices[0] if completion.choices else None
            content = (choice.message.content if choice and choice.message else "") or ""

            usage = getattr(completion, "usage", None)
            in_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            out_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

            return LLMResponse(
                content=content,
                model=model,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                cost_usd=estimate_cost_usd(
                    model, input_tokens=in_tokens, output_tokens=out_tokens
                ),
                latency_ms=latency_ms,
            )
        finally:
            if owns_client:
                await client.close()
