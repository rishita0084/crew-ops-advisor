"""LLM provider abstraction.

Everything model-specific lives behind this interface so switching provider is an env
change. The advisor must also run with no provider at all -- see app/fallback -- because
a crew desk cannot go dark because an API key expired.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ChatMessage:
    role: str                      # system | user | assistant | tool
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_api(self) -> dict:
        payload: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def chat(self, messages: list[ChatMessage], tools: list[dict] | None = None,
             temperature: float = 0.0) -> ChatResponse:
        ...


class ProviderError(RuntimeError):
    pass


def get_provider() -> LLMProvider | None:
    """Build the configured provider, or None when the LLM is disabled."""
    from app.config import LLM_ENABLED, LLM_PROVIDER

    if not LLM_ENABLED:
        return None

    if LLM_PROVIDER in ("groq", "openai", "openai_compat", "gemini"):
        from app.llm.providers.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider()

    raise ProviderError(f"Unknown LLM_PROVIDER {LLM_PROVIDER!r}")
