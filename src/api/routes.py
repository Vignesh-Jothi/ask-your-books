"""HTTP API routes.

Tenant identity: the `X-User-Id` header decides who is asking; the org is
resolved server-side and injected by the guard. No org/tenant parameter is
accepted from the client — that is the whole point.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

from src.api.models import ChatRequest
from src.config.settings import SETTINGS
from src.services import chat_service as cs
from src.services import org_service
from src.services.log_service import count_lines

router = APIRouter(prefix="/api")


def _user_id(x_user_id: str | None) -> str:
    return (x_user_id or SETTINGS.default_user_id).strip()


@router.get("/health")
def health():
    db_ok = Path(SETTINGS.db_path_abs).exists()
    conn = org_service._get_conn()
    try:
        org_count = conn.execute("SELECT COUNT(*) AS n FROM organizations").fetchone()["n"]
    except sqlite3.Error:
        org_count = 0
    return {
        "ok": db_ok,
        "provider": SETTINGS.provider,
        "model": SETTINGS.model or "mock",
        "today": SETTINGS.today,
        "database": SETTINGS.db_path,
        "organizations": org_count,
        "tool_calls_logged": count_lines(),
    }


@router.post("/chat")
def chat(req: ChatRequest, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    user = _user_id(x_user_id)
    return cs.chat_service.handle(user, req.session_id, req.message, req.reply_to)