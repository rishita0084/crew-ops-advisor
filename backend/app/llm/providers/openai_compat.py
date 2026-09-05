"""One client for every OpenAI-compatible chat API.

Groq, Gemini's compatibility endpoint and OpenAI itself all speak the same wire format
for chat completions and tool calling, so a single implementation covers all three and
new providers are a base-URL change.
"""
from __future__ import annotations

import json
import re
import time

import httpx

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER
from app.llm.provider import ChatMessage, ChatResponse, ProviderError

DEFAULT_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}

TIMEOUT_SECONDS = 25.0
MAX_RETRIES = 3
MAX_BACKOFF_SECONDS = 8.0


def _retry_after(response: httpx.Response) -> float:
    """How long the API asked us to wait, from the header or the error message.

    Returned unclamped and on purpose. The caller needs the *real* wait to decide
    whether waiting is worth it at all -- clamping here silently turned "come back in
    54 seconds" into three pointless 8-second sleeps.
    """
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    match = re.search(r"try again in ([\d.]+)\s*(ms|s)", response.text)
    if match:
        value = float(match.group(1))
        return value / 1000 if match.group(2) == "ms" else value + 0.25
    return 1.0


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self) -> None:
        self.base_url = (LLM_BASE_URL or DEFAULT_BASE_URLS.get(LLM_PROVIDER, "")).rstrip("/")
        if not self.base_url:
            raise ProviderError(f"No base URL configured for provider {LLM_PROVIDER!r}")
        if not LLM_API_KEY:
            raise ProviderError("LLM_API_KEY is empty")
        self.model = LLM_MODEL
        self.name = LLM_PROVIDER

    def chat(self, messages: list[ChatMessage], tools: list[dict] | None = None,
             temperature: float = 0.0) -> ChatResponse:
        payload: dict = {
            "model": self.model,
            "messages": [m.to_api() for m in messages],
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = None
        for attempt in range(MAX_RETRIES):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=TIMEOUT_SECONDS,
                )
            except httpx.HTTPError as exc:
                raise ProviderError(f"{self.name} unreachable: {exc}") from exc

            # Free tiers rate-limit per minute AND per day. A short per-minute wait is
            # worth taking -- waiting 2s beats dropping to the terser fallback. A daily
            # cap is not: the API says "try again in 54s", nobody on a crew desk waits
            # that long, and sleeping anyway just delays the fallback we were always
            # going to use. Honour the number the API gives us, and give up when it is
            # longer than a controller would tolerate.
            if response.status_code == 429 and attempt < MAX_RETRIES - 1:
                wait = _retry_after(response)
                if wait <= MAX_BACKOFF_SECONDS:
                    time.sleep(wait)
                    continue
            break

        if response.status_code == 429:
            # Say what actually happened, so "it got slow and terse" is diagnosable
            # from the logs instead of looking like a bug in the engine.
            raise ProviderError(
                f"{self.name} rate limit reached; falling back to the deterministic "
                f"router. {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise ProviderError(f"{self.name} returned {response.status_code}: {response.text[:300]}")

        try:
            body = response.json()
            choice = body["choices"][0]["message"]
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise ProviderError(f"{self.name} returned an unexpected body: {exc}") from exc

        return ChatResponse(
            content=choice.get("content") or "",
            tool_calls=choice.get("tool_calls") or [],
            raw=body,
        )
