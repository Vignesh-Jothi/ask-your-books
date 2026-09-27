"""Deterministic mock LLM — keyword dispatch over the tool registry.

Purpose: run the whole stack offline (tests, eval, demos) without an API key.
It must be *deterministic*: same question -> same tool calls -> same numbers.

Heuristics are deliberately simple; this is not the product — the real
router is the configurable OpenAI-compatible client. For follow-ups
("and the same for last year?") it shifts the previous period by one year
using the session history passed in `messages`.
"""
from __future__ import annotations

from src.core.fy import resolve_period, shift_year, Period
from src.llm.client import ChatResult, ToolCall

_VAGUE = ("how are we doing", "how is the company", "how am i doing", "summary", "health", "status", "how's business")
_REFUSABLE = ("attrition", "employees", "salaries of people", "hr", "resign", "hiring", "bench strength")


class MockClient:
    model = "mock-dispatch"

    def _match(self, message: str):
        message_lower = message.lower()
        if any(keyword in message_lower for keyword in _REFUSABLE):
            return "refuse_answer", {"reason": "employment/HR data is not part of the accounting dataset here."}
        if any(keyword in message_lower for keyword in _VAGUE):
            return "ask_clarification", {
                "options": [
                    "How much did we sell this quarter?",
                    "Who owes us the most right now?",
                    "How do our receivables look by age?",
                ]
            }

        # period-aware metric dispatch (canonical label for the chosen tool)
        period = self._resolve_period_from(message_lower)
        # raw-SQL questions (attacks / novel queries) go to the sandboxed tool
        # NB: extract from the ORIGINAL message — lowercasing corrupts string
        # literals ('Sundry Debtors' -> 'sundry debtors' would match nothing).
        if message.strip().lower().startswith("select ") or "sql:" in message.lower():
            if "sql:" in message.lower():
                sql = message.split("sql:", 1)[1].strip()
            else:
                sql = message.strip()
            return "sql_query", {"sql": sql, "description": "user-provided SQL"}

        if "owe" in message_lower or "receivable" in message_lower or "debtor" in message_lower or "owes us" in message_lower:
            if "age" in message_lower or "ageing" in message_lower or "overdue" in message_lower or "late" in message_lower:
                return "receivables_ageing", {"age": None}
            return "top_parties", {"metric": "receivable", "period": period, "limit": 10}
        if "balance" in message_lower and " for " in message_lower:
            # party-balance long tail -> sandboxed SQL (deterministic, org-scoped)
            party = message_lower.split(" for ", 1)[1].strip().strip("?.")
            safe_party = party.replace("'", "''")  # neutralize any quote injection
            party_sql = (
                "SELECT al.name AS party, SUM(vl.amount_paise) AS balance_paise "
                "FROM voucher_lines vl JOIN vouchers v ON v.voucher_id = vl.voucher_id "
                "JOIN accounts al ON al.account_id = vl.account_id "
                "WHERE v.is_cancelled = 0 AND al.grp IN ('Sundry Debtors','Sundry Creditors') "
                f"AND al.name = '{safe_party}'"
            )
            return "sql_query", {"sql": party_sql, "description": "party balance"}
        if "compared" in message_lower or " vs " in message_lower or "versus" in message_lower:
            return "fy_comparison", {"metric": "expense", "period": period}
        if "pay" in message_lower and ("late" in message_lower or "overdue" in message_lower or "vendor" in message_lower):
            return "receivables_ageing", {"age": "overdue"}
        if "expense" in message_lower or "spend" in message_lower or "purchase" in message_lower or "freight" in message_lower or "cost" in message_lower:
            return "expense_by_group", {"period": period, "filter_groups": None}
        if "income" in message_lower or "revenue" in message_lower or "sold" in message_lower or "sales" in message_lower or "sell" in message_lower:
            return "income_by_group", {"period": period}
        if "outstanding" in message_lower or "bills" in message_lower:
            return "outstanding_bills", {"party": None, "limit": 20}
        if "ageing" in message_lower or "age" in message_lower or "overdue" in message_lower:
            return "receivables_ageing", {"age": None}
        if "attrit" in message_lower:
            return "refuse_answer", {"reason": "employment/HR data is not part of the accounting dataset here."}
        return "ask_clarification", {
            "options": [
                "How much did we sell this quarter?",
                "Who owes us the most right now?",
                "How much did we spend on expenses this quarter?",
            ]
        }

    def _resolve_period_from(self, message_lower: str) -> str | None:
        import re

        explicit_fy = re.search(r"fy ?(\d{4})-(\d{2})", message_lower)
        if explicit_fy:
            return f"FY {explicit_fy.group(1)}-{explicit_fy.group(2)}"
        # quarter-based phrasing wins over bare 'year' ("last quarter compared to
        # the same quarter last year" must not collapse to the whole last year)
        if "quarter" in message_lower:
            relative = "last" if "last quarter" in message_lower else "this"
            period = resolve_period(f"{relative} quarter")
            return period.label if period else None
        if "last fiscal" in message_lower or ("last year" in message_lower and "same" not in message_lower) or "previous year" in message_lower:
            return "last year"
        if "year" in message_lower or "fy" in message_lower:
            return "this year"
        if "q1" in message_lower:
            return "Q1"
        if "q2" in message_lower:
            return "Q2"
        if "q3" in message_lower:
            return "Q3"
        if "q4" in message_lower:
            return "Q4"
        if "month" in message_lower:
            return "last month" if "last month" in message_lower else "this month"
        return None

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        latest_user_message = next(
            (message["content"] for message in reversed(messages) if message["role"] == "user"), ""
        )

        # If a tool already ran for the latest user message, stop: the caller
        # synthesizes the final answer from that tool's result rows.
        # (Chronological scan so previous turns' tool calls are ignored.)
        user_indexes = [index for index, message in enumerate(messages) if message["role"] == "user"]
        if user_indexes and any(message.get("meta") for message in messages[user_indexes[-1] + 1:]):
            return ChatResult(text="", usage={"total_tokens": 0})

        name, args = self._match(latest_user_message)

        # follow-up: shift the previous tool's period by one year and reuse its args
        if name is None and not latest_user_message:
            return ChatResult(text="I need a question to work with.")

        previous_tool = None
        for message in reversed(messages):
            if message.get("role") == "assistant" and message.get("meta"):
                previous_tool = message["meta"]
                break
        if previous_tool and ("same" in latest_user_message.lower() or "same quarter last year" in latest_user_message.lower()):
            previous_args = dict(previous_tool["arguments"])
            period_label = previous_args.get("period")
            if period_label:
                resolved = resolve_period(period_label) or Period("", "", period_label)
                shifted = shift_year(resolved)
                previous_args["period"] = shifted.label
            name, args = previous_tool["name"], previous_args
            return ChatResult(tool_calls=[ToolCall(name=name, arguments=args)], usage={"total_tokens": 0})

        if name == "refuse_answer":
            return ChatResult(tool_calls=[ToolCall(name="refuse_answer", arguments=args)], usage={"total_tokens": 0})

        if len(latest_user_message.split()) < 3:
            return ChatResult(tool_calls=[ToolCall(name="ask_clarification", arguments=args)], usage={"total_tokens": 0})

        return ChatResult(tool_calls=[ToolCall(name=name, arguments=args)], usage={"total_tokens": 0})