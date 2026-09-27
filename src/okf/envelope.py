"""Open Knowledge Format — app-level envelope helpers.

Every payload crossing the API / tool / log boundaries is packed as an OKF
envelope (see okf/README.md). pack()/unpack() are cheap; validation of the
`data` payload is delegated to the pydantic models defined per-layer.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone


KINDS = {
    "chat.request": "chat.request.json",
    "chat.response": "chat.response.json",
    "tool.call": "tool.call.json",
    "metric.result": "metric.result.json",
}


def new_trace_id() -> str:
    return "t_" + uuid.uuid4().hex[:12]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pack(kind: str, data: dict, org_id: str | None = None, trace_id: str | None = None) -> dict:
    """Wrap `data` in the OKF envelope."""
    assert kind in KINDS, f"unknown okf kind: {kind}"
    return {
        "okf": "1.0",
        "kind": kind,
        "schema": KINDS[kind],
        "ts": utcnow(),
        "org_id": org_id,
        "trace_id": trace_id or new_trace_id(),
        "data": data,
    }


def unpack(envelope: dict) -> dict:
    """Return the data payload; provenance fields stay on the envelope."""
    return envelope.get("data", {})


def dump_jsonl(path: str, envelope: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(envelope, default=str) + "\n")