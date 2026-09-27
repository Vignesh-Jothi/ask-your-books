"""Tool-call logging — one OKF `tool.call` envelope per execution (JSONL).

Every log line carries the envelope + generated SQL + row count + status +
latency + tokens so answer quality and safety can be audited afterwards
(see infrastructure/monitoring/log_schema.md).
"""
from __future__ import annotations

import time
from pathlib import Path

from src.config.settings import SETTINGS
from src.okf import envelope as okf


def log_tool_call(*, trace_id: str, org_id: str, user_id: str, session_id: str,
                  tool: str, arguments: dict, generated_sql: str | None,
                  row_count: int, status: str, error: str | None,
                  latency_ms: float, tokens: int) -> None:
    path = Path(SETTINGS.tool_calls_file_abs)
    path.parent.mkdir(parents=True, exist_ok=True)
    env = okf.pack(
        "tool.call",
        {
            "trace_id": trace_id,
            "org_id": org_id,
            "user_id": user_id,
            "session_id": session_id,
            "tool": tool,
            "arguments": arguments,
            "generated_sql": generated_sql,
            "row_count": row_count,
            "status": status,
            "error": error,
            "latency_ms": round(latency_ms, 1),
            "tokens": tokens,
        },
        org_id=org_id,
        trace_id=trace_id,
    )
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(__import__("json").dumps(env) + "\n")


def count_lines() -> int:
    path = Path(SETTINGS.tool_calls_file_abs)
    if not path.exists():
        return 0
    return sum(1 for _ in path.open(encoding="utf-8"))