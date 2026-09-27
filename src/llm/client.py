"""LLM client factory.

* mock        — deterministic local dispatch (no network; unit tests + eval default)
* openai/groq/ollama — any OpenAI-compatible /chat/completions endpoint via the
                `openai` SDK, configured with LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL.

Each provider exposes `chat(messages, tools) -> ChatResult` where ChatResult has
`.text`, `.tool_calls` (list[ToolCall(name, arguments)]), `.usage` (dict).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config.settings import SETTINGS


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class ChatResult:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)


def get_client():
    provider = SETTINGS.provider
    if provider == "mock":
        from src.llm.mock import MockClient

        return MockClient()
    from src.llm.openai_compat import OpenAICompatClient

    return OpenAICompatClient()


__all__ = ["get_client", "ChatResult", "ToolCall"]