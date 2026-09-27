"""Tool registry — single list of tools the LLM can call.

Schemas are OpenAI function-calling format. Handlers are metric functions
(hand-written SQL, correct by construction) plus the sandboxed SQL escape
hatch. Both routes go through the same guard pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.services import metrics_service
from src.services.metrics_service import MetricResult


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: callable


def _period_param(**extra):
    return {
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "description": "OPTIONAL period phrase: 'this year', 'last year', 'Q1', 'this quarter', 'last quarter', 'this month', 'FY 2025-26', or 'YYYY-MM-DD..YYYY-MM-DD'. Defaults to current FY if omitted.",
            },
            **extra,
        },
        "required": [],
    }


TOOLS: list[Tool] = [
    Tool(
        "expense_by_group",
        "Total spending (expenses/purchases/freight) per ledger group for an optional period. Sum is expenditure, always shown positive.",
        _period_param(filter_groups={
            "type": "array", "items": {"type": "string"},
            "description": "optional subset of groups: Purchase Accounts, Direct Expenses, Indirect Expenses, Duties & Taxes",
        }),
        metrics_service.h_expense_by_group,
    ),
    Tool(
        "income_by_group",
        "Total revenue/sales/income per ledger group for an optional period. Always shown positive.",
        _period_param(),
        metrics_service.h_income_by_group,
    ),
    Tool(
        "fy_comparison",
        "Compare a metric (expense or income) for a period against the same period in the previous financial year.",
        _period_param(metric={"type": "string", "enum": ["expense", "income"]}),
        metrics_service.h_fy_comparison,
    ),
    Tool(
        "receivables_ageing",
        "Receivables aging: outstanding receivables bucketed by days overdue from due_date vs TODAY. Pass age='overdue' for only-overdue buckets.",
        _period_param(age={"type": "string", "enum": ["overdue", None]}),
        metrics_service.h_receivables_ageing,
    ),
    Tool(
        "top_parties",
        "Rank parties by receivable (who owes us the most) or payable (who we owe the most) balance in a period.",
        _period_param(
            metric={"type": "string", "enum": ["receivable", "payable"]},
            limit={"type": "integer", "description": "max rows to return, default 10"},
        ),
        metrics_service.h_top_parties,
    ),
    Tool(
        "outstanding_bills",
        "Bill-wise outstanding for parties (receivable positive, payable negative). Optionally filter by party name.",
        _period_param(party={"type": "string"}, limit={"type": "integer"}),
        metrics_service.h_outstanding_bills,
    ),
    Tool(
        "sql_query",
        "LAST RESORT: run a user-formulated read-only SELECT against the accounting schema. Fully sandboxed — read-only and org-scoped. Use only when no metric tool fits.",
        _period_param(
            sql={"type": "string", "description": "single SELECT statement referencing accounts/vouchers/voucher_lines/bills/organizations/users"},
            description={"type": "string"},
        ),
        metrics_service.h_sql_query,
    ),
]

TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }
    for tool in TOOLS
]

BY_NAME = {tool.name: tool for tool in TOOLS}


def run_tool(name: str, args: dict, *, conn, org_id, today) -> MetricResult:
    tool = BY_NAME.get(name)
    if tool is None:
        raise KeyError(f"unknown tool: {name}")
    return tool.handler(conn, org_id, today, **args)