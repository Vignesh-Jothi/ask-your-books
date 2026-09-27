"""API request/response models (pydantic twins of the OKF JSON Schemas in
okf/schemas/). Validation happens once, here, at the boundary.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="User question")
    session_id: str = Field(min_length=1, max_length=64)
    reply_to: str | None = Field(default=None, max_length=200, description="clarification option id")


class ChatResponse(BaseModel):
    kind: str = "chat.response"
    status: str  # answered | clarifying | refused | error
    session_id: str
    org_id: str | None = None
    trace_id: str = ""
    text: str = ""
    assumption: str | None = None
    period: str | None = None
    clarify: list[str] | None = None
    refusal: str | None = None
    rows: list = []
    trace: list = []
    tokens: int = 0