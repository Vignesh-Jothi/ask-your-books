"""OpenAI-compatible client (OpenAI / Groq / Ollama / LM Studio).

The python `openai` SDK speaks the same wire protocol to any base_url, so a
single client covers every provider listed in the brief.
"""
from __future__ import annotations

import os

from src.config.settings import SETTINGS
from src.llm.client import ChatResult, ToolCall


class OpenAICompatClient:
    def __init__(self):
        from openai import OpenAI

        kwargs = {}
        if SETTINGS.base_url:
            kwargs["base_url"] = SETTINGS.base_url
        if SETTINGS.api_key:
            kwargs["api_key"] = SETTINGS.api_key
        self._client = OpenAI(**kwargs)
        self.model = SETTINGS.model or "gpt-4o-mini"

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        kwargs = dict(
            model=self.model,
            # strip our internal "meta" key before sending to the provider wire format
            messages=[{key: value for key, value in message.items() if key != "meta"} for message in messages],
            temperature=SETTINGS.temperature,
            max_tokens=SETTINGS.max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resp = self._client.chat.completions.create(**kwargs)
        message = resp.choices[0].message

        calls = []
        if getattr(message, "tool_calls", None):
            for tool_call in message.tool_calls:
                import json

                args = {}
                if tool_call.function.arguments:
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        # never let a malformed args payload crash the turn
                        args = {"raw": tool_call.function.arguments}
                calls.append(ToolCall(name=tool_call.function.name, arguments=args))

        usage = {
            "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(resp.usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(resp.usage, "total_tokens", 0) or 0,
        }
        return ChatResult(text=message.content or "", tool_calls=calls, usage=usage)