"""Known model specs, keyed by "provider/model".

A user still only supplies provider + key (+ model name): when the chosen
model has a spec here, the app uses it — e.g. the model's output cap clamps
the per-call max_tokens so we never ask a model for more than it can emit.
context_window is stored as reference data for future prompt-trimming; today
sessions are small (chat_service caps history at `services.chat_history_size`),
so it is not enforced.
"""
from __future__ import annotations

OPENROUTER_MODELS = {
    "minimax/minimax-m3": {
        "context_window": 1_000_000,
        "max_output_tokens": 64_000,
        "reasoning": True,
        "supports_images": True,
        "supports_tools": True,
        "supports_streaming": True,
    },
    "deepseek/deepseek-v4-flash-0731": {
        "context_window": 1_000_000,
        "max_output_tokens": 64_000,
        "reasoning": True,
        "supports_images": False,
        "supports_tools": True,
        "supports_streaming": True,
    },
    "moonshotai/kimi-k2.7-code": {
        "context_window": 262_144,
        "max_output_tokens": 32_000,
        "reasoning": True,
        "supports_images": True,
        "supports_tools": True,
        "supports_streaming": True,
    },
    "z-ai/glm-5.2": {
        "context_window": 128_000,
        "max_output_tokens": 32_000,
        "reasoning": True,
        "supports_images": True,
        "supports_tools": True,
        "supports_streaming": True,
    },
}

PROVIDER_MODEL_SPECS = {
    "openrouter": OPENROUTER_MODELS,
}


def model_spec(provider: str, model: str) -> dict | None:
    """Spec for a known provider/model, or None (the app works fine without one)."""
    return (PROVIDER_MODEL_SPECS.get(provider) or {}).get(model)