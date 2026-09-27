"""Organization service — resolves the authenticated user to their tenant.

THE trust anchor: every request carries a user identity; org_id is derived
here (from the DB, never from the LLM or the request body) and injected by
the guard into every generated query.
"""
from __future__ import annotations

from src.db.connection import run_readonly, connect_readonly

_conn = None
_cache: dict[str, str] = {}


def _get_conn():
    global _conn
    if _conn is None:
        _conn = connect_readonly()
    return _conn


def resolve_org(user_id: str) -> str:
    if user_id in _cache:
        return _cache[user_id]
    rows = run_readonly(
        _get_conn(),
        "SELECT org_id FROM users WHERE user_id = ?",
        (user_id,),
        row_limit=2,
    )
    if not rows:
        raise LookupError(f"unknown user: {user_id}")
    org = rows[0]["org_id"]
    _cache[user_id] = org
    return org


def org_name(org_id: str) -> str:
    rows = run_readonly(
        _get_conn(),
        "SELECT name FROM organizations WHERE org_id = ?",
        (org_id,),
        row_limit=2,
    )
    return rows[0]["name"] if rows else org_id