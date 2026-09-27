"""Chat orchestration — the agent loop.

Flow per user message:
  1. resolve the user's org from the DB (never from the LLM / request body)
  2. agent loop (max N iterations):
       llm.chat(messages + tools) -> tool calls | final text
       every tool call -> guarded execution -> OKF tool.call log line -> append
  3. assemble a chat.response: status (answered|clarifying|refused|error),
     text, assumption/period, rows (paise), trace (show-your-work).

Follow-ups work because the session keeps the full message history and the
resolved context of previous tool calls.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field

from src.config.settings import SETTINGS
from src.core.fy import today as ref_today
from src.core.money import fmt_abs
from src.db.connection import connect_readonly
from src.guards.sql_guard import SQLGuardError
from src.llm import prompts
from src.llm.client import get_client
from src.services import billing_service, log_service, org_service
from src.services.metrics_service import MetricResult
from src.tools import registry as tools
from src.okf import envelope as okf


@dataclass
class ChatSession:
    user_id: str
    org_id: str
    messages: list = field(default_factory=list)
    last_result: MetricResult | None = None
    last_period_label: str | None = None


class SessionStore:
    def __init__(self, max_sessions: int = 200):
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()
        self._max = max_sessions

    def get(self, session_id: str, user_id: str, org_id: str) -> ChatSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                if len(self._sessions) >= self._max:
                    self._sessions.pop(next(iter(self._sessions)))  # evict the oldest session
                session = self._sessions[session_id] = ChatSession(user_id=user_id, org_id=org_id)
            elif session.user_id != user_id:  # a session belongs to its creator
                session = self._sessions[session_id] = ChatSession(user_id=user_id, org_id=org_id)
            return session

    def clear(self):
        with self._lock:
            self._sessions.clear()


sessions = SessionStore()
_today = ref_today()


def _synthesize_answer(res: MetricResult, org_name: str) -> str:
    """Deterministic fallback text (mock provider / no model text). Numbers come
    straight from the metric rows — never computed by an LLM."""
    rows = res.rows
    if not rows:
        return "I couldn't find data for that. Try rephrasing or pick one of the suggested options."
    period = f" ({res.period_label})" if res.period_label else ""

    def money(amount):
        return f"₹{abs(amount) // 100:,}" if isinstance(amount, int) else str(amount)

    if "bucket" in rows[0] and "grp" not in rows[0] and "party" not in rows[0]:
        lines = "\n".join(f"  • {row['bucket']}: {row['bills']} bills totalling {money(row['total_paise'])}" for row in rows)
        return f"Receivables ageing{period}:\n{lines}"
    if "grp" in rows[0]:
        lines = "\n".join(f"  • {row['grp']}: {money(row['total_paise'])}" for row in rows)
        return f"Amount by ledger group{period}:\n{lines}"
    if "this_period" in rows[0]:
        row = rows[0]
        delta = f" ({row['change_pct']:+.1f}% vs prior year)" if row["change_pct"] is not None else ""
        return f"{row['metric'].title()} for {res.period_label}: {money(row['this_period'])}{delta} (prior year: {money(row['prior_year'])}). Answer shows positive INR."
    if "bill_id" in rows[0]:
        lines = "\n".join(f"  • {row['party']} {row['bill_id']} due {row['due_date']}: {money(row['outstanding_paise'])}" for row in rows[:6])
        return f"Outstanding bills{period}:\n{lines}" + (f"\n  … and {len(rows)-6} more" if len(rows) > 6 else "")
    if "party" in rows[0]:
        lines = "\n".join(f"  • {row['party']}: {money(row['balance_paise'] if 'balance_paise' in row else row['outstanding_paise'])}" for row in rows[:10])
        return f"Top parties{period}:\n{lines}" + (f"\n  … and {len(rows)-10} more" if len(rows) > 10 else "")
    return f"Result ({res.period_label or 'as of today'}): {rows[:5]}"


class ChatService:
    def __init__(self, client=None):
        self.client = client or get_client()
        self.conn = connect_readonly()

    def handle(self, user_id: str, session_id: str, message: str, reply_to: str | None = None) -> dict:
        trace_id = okf.new_trace_id()
        try:
            org_id = org_service.resolve_org(user_id)
        except LookupError as exc:
            return self._error_result(session_id, str(exc), trace_id, 401)

        if reply_to:
            message = f"{message.strip()} (choice: {reply_to})"

        session = sessions.get(session_id, user_id, org_id)
        history = session.messages[-SETTINGS.chat_history_size * 2:]

        messages = [{"role": "system", "content": prompts.build_system_prompt(
            org_service.org_name(org_id), _today.isoformat())}]
        messages += history
        messages.append({"role": "user", "content": message})
        session.messages.append({"role": "user", "content": message})

        trace = []
        tokens = 0
        last_result = None
        status = "answered"

        for _ in range(SETTINGS.agent_max_iterations):
            t0 = time.perf_counter()
            result = self.client.chat(messages, prompts.tool_schemas())
            tokens += billing_service.usage_tokens(result.usage, result.text)

            if not result.tool_calls:
                last_result = session.last_result
                final_text = result.text.strip() or \
                    (_synthesize_answer(last_result, org_id) if last_result else "")
                if final_text:
                    session.messages.append({"role": "assistant", "content": final_text})
                    return self._response(session_id, org_id, trace, tokens, trace_id,
                                          status="answered", text=final_text, result=last_result)
                return self._clarify_result(
                    session_id, org_id, trace, tokens, trace_id,
                    question="I need a bit more detail — what would you like to look at?",
                    options=["How much did we sell this quarter?",
                             "Who owes us the most right now?",
                             "How are our receivables ageing?"],
                )

            # tool call(s) from the model
            for call in result.tool_calls:
                gate = self._run_tool_call(session, call, trace, trace_id, user_id, session_id)
                # clarify / refuse / errored tools return a final response dict
                if "_msg" not in gate:
                    return gate
                messages += [gate["_msg"], gate["_tool_msg"]]
                session.messages += [gate["_msg"], gate["_tool_msg"]]
                last_result = session.last_result
            status = "answered"

        return self._response(session_id, org_id, trace, tokens, trace_id, status="error",
                              text="I couldn't finish within the allowed number of tool steps. Please rephrase.", result=last_result)

    # ------------------------------------------------------------ internals

    def _run_tool_call(self, session, call, trace, trace_id, user_id, session_id):
        t0 = time.perf_counter()
        args = dict(call.arguments or {})

        # agent-native tools (clarify / refuse) are handled before the registry
        if call.name == "ask_clarification":
            return self._clarify_result(session_id, session.org_id, trace, 0, trace_id,
                                        options=args.get("options", []), question="What would you like to look at?")
        if call.name == "refuse_answer":
            return self._response(session_id, session.org_id, trace, 0, trace_id, status="refused",
                                  text="", refusal=args.get("reason", "This question can't be answered from accounting data."))

        try:
            res = tools.run_tool(call.name, args, conn=self.conn, org_id=session.org_id, today=_today)
            session.last_result = res
            if res.period_label:
                session.last_period_label = res.period_label
            status, error, row_count = "ok", None, len(res.rows)
        except SQLGuardError as exc:
            res = None
            status, error, row_count = "refused", str(exc), 0
        except Exception as exc:  # noqa: BLE001
            res = None
            status, error, row_count = "error", str(exc), 0

        latency_ms = (time.perf_counter() - t0) * 1000
        log_service.log_tool_call(
            trace_id=trace_id, org_id=session.org_id, user_id=user_id, session_id=session_id,
            tool=call.name, arguments=args, generated_sql=(res.sql if res else None),
            row_count=row_count, status=status, error=error, latency_ms=latency_ms, tokens=0,
        )
        trace.append({
            "tool": call.name, "args": args, "sql": res.sql if res else None,
            "rows": row_count, "status": status, "error": error, "latency_ms": round(latency_ms, 1),
        })

        if status == "error":
            return self._error_result(session_id, f"tool {call.name} failed: {error}", trace_id, 422)
        if status == "refused":
            # guard decision (unsafe SQL, forbidden keyword, blocked table) — a
            # deliberate answer, not a crash
            return self._response(session_id, session.org_id, trace, 0, trace_id, status="refused",
                                  text=error, refusal=error)

        # Standard wire messages so both the OpenAI-compatible client and the
        # mock provider can consume the same history.
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(args)},
            }],
            "meta": {"name": call.name, "arguments": args},
        }
        tool_payload = {"rows": res.rows if res else [], "period": res.period_label if res else None}
        tool_msg = {"role": "tool", "tool_call_id": call_id, "content": json.dumps(tool_payload, default=str)}
        return {"_msg": assistant_msg, "_tool_msg": tool_msg}

    # ------------------------------------------------------------------ responses

    def _response(self, session_id, org_id, trace, tokens, trace_id, *, status, text, result=None, refusal=None, clarify=None, question=None):
        return {
            "kind": "chat.response",
            "status": status,
            "session_id": session_id,
            "org_id": org_id,
            "trace_id": trace_id,
            "text": text.strip() if text else "",
            "assumption": (result.period_label if result else None),
            "period": (result.period_label if result else None),
            "clarify": clarify,
            "refusal": refusal,
            "question": question,
            "rows": (result.rows if result else []),
            "trace": trace,
            "tokens": tokens,
        }

    def _clarify_result(self, session_id, org_id, trace, tokens, trace_id, *, options=None, question=None):
        return self._response(session_id, org_id, trace, tokens, trace_id, status="clarifying",
                              text=question or "Could you be more specific?",
                              clarify=options or [
                                  "How much did we sell this quarter?",
                                  "Who owes us the most right now?",
                                  "How do our receivables age?",
                              ])

    def _error_result(self, session_id, message, trace_id, code):
        return {"kind": "chat.response", "status": "error", "session_id": session_id,
                "trace_id": trace_id, "text": message, "clarify": None, "rows": [], "trace": [], "tokens": 0}


chat_service = ChatService()