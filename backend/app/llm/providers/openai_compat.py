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
    """How long the API asked us to wait, from the header or the error message."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    match = re.search(r"try again in ([\d.]+)\s*(ms|s)", response.text)
    if match:
        value = float(match.group(1))
        seconds = value / 1000 if match.group(2) == "ms" else value
        return min(seconds + 0.25, MAX_BACKOFF_SECONDS)
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

            # free tiers rate-limit by tokens per minute; the API tells us how long to
            # wait, and waiting briefly beats dropping to the fallback
            if response.status_code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(_retry_after(response))
                continue
            break

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
