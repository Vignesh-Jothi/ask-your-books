"""Per-provider defaults — the ONLY thing a user supplies is provider + API key
(+ optionally a model name); base_url, default model and the cost used by the
eval report are derived here.

All providers are spoken to over the OpenAI-compatible /chat/completions wire
format (the `openai` SDK points at their base_url), so one client covers them.
"""
from __future__ import annotations

PROVIDERS = {
    # offline deterministic dispatch (no network, no key) — default
    "mock": {"base_url": None, "model": "", "cost_per_1k": 0.0},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "cost_per_1k": 0.0025},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile", "cost_per_1k": 0.0005},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "llama3.1:8b", "cost_per_1k": 0.0},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash", "cost_per_1k": 0.0025},
    "claude": {"base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-4-20250514", "cost_per_1k": 0.003},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "anthropic/claude-3.5-sonnet", "cost_per_1k": 0.003},
}


def provider_defaults(provider: str) -> dict:
    """Defaults for a provider name ({} for unknown — the user must then supply model/base_url)."""
    return dict(PROVIDERS.get(provider, {}))