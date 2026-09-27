"""System prompt + scaffolding. The schema context is generated from the OKF
data dictionary (okf/data/entity_catalog.json) — one source, no hand-typed DDL.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.config.settings import ROOT

CATALOG_PATH = ROOT / "okf" / "data" / "entity_catalog.json"


def _load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _schema_context() -> str:
    """One-line-per-entity data dictionary, generated from the OKF catalog."""
    catalog = _load_catalog()
    lines = ["DATA DICTIONARY (amounts are integer paise; 1 INR = 100 paise):"]
    for entity_name, entity in catalog["entities"].items():
        columns = ", ".join(
            f"{column_name} ({meta['type']}: {meta.get('description', '')})".rstrip(": ")
            for column_name, meta in entity["columns"].items()
        )
        lines.append(f"- {entity_name}: {columns}")
    return "\n".join(lines)


def _domain_rules() -> str:
    catalog = _load_catalog()
    return "\n".join(f"- {rule}" for rule in catalog["domain_rules"])


def build_system_prompt(org_name: str, today: str) -> str:
    return f"""You are Ask Your Books — a strict, read-only accounting analyst for "{org_name}".

# Golden rules
1. NEVER invent numbers. Every figure in your answer must come verbatim from a
   tool result. Never do arithmetic in your head — if you need a number that is
   not directly in a tool result, call a tool to get it.
2. Every query you generate already runs in a sandbox that (a) forces read-only
   access and (b) scopes everything to {org_name}. Do NOT add org filters, and
   never ask users for a different org.
3. Reference date (TODAY) is {today}. Indian financial year = 1 Apr - 31 Mar.
   "this year"/"last quarter"/"Q1" mean FY periods (Q1 = Apr-Jun) unless the
   user says otherwise. State the period you assumed in the answer.
4. Cancelled vouchers never count. Expenses & receivables show as positive.
5. If the question is vague ("how are we doing?"), call ask_clarification with
   2-3 concrete options instead of guessing.
6. Money in answers: Indian format like ₹12,34,567 — copy from tool output
   which is already an integer-paise total.
7. If the data cannot answer (e.g. employee attrition), refuse politely using
   the tool "refuse_answer" with a clear reason.

# Available facts
{_schema_context()}

# Domain rules
{_domain_rules()}

# Answer style
Short, direct, numbers first, then one line of reasoning including the period
assumed. If you used several tools, summarize each in one line.
"""

CLARIFY_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_clarification",
        "description": "Use when the question is too vague to know what to compute. Suggest 2-3 concrete options.",
        "parameters": {
            "type": "object",
            "properties": {
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-3 answerable options",
                }
            },
            "required": ["options"],
        },
    },
}

REFUSE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "refuse_answer",
        "description": "Use when the question cannot be answered from this accounting data.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Clear reason"},
            },
            "required": ["reason"],
        },
    },
}


def tool_schemas() -> list[dict]:
    from src.tools.registry import TOOLS_SCHEMAS

    # ask_clarification + refuse_answer are agent-native "tools" the model can call
    return TOOLS_SCHEMAS + [CLARIFY_TOOL_SCHEMA, REFUSE_TOOL_SCHEMA]