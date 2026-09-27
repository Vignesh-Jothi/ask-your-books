"""Billing / cost — token usage from the provider (usage.total_tokens) with a
rough char-based estimate as fallback (mock provider). Cost uses
cost_per_1k_tokens from config.
"""
from __future__ import annotations

from src.config.settings import SETTINGS


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def usage_tokens(usage: dict, text: str = "") -> int:
    total = (usage or {}).get("total_tokens")
    if total:
        return int(total)
    return estimate_tokens(text)


def cost_usd(tokens: int) -> float:
    return round(tokens / 1000 * SETTINGS.cost_per_1k_tokens, 4)