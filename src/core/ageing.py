"""Receivables ageing buckets.

Buckets compare a bill's due_date against TODAY (config/env):
  not_due | 0-30 | 31-60 | 61-90 | 90+

All comparisons are whole-day, inclusive of the boundary i.e. 30 days overdue
lands in 0-30, 31 days in 31-60.
"""
from __future__ import annotations

from datetime import date

BUCKETS = ("not_due", "0-30", "31-60", "61-90", "90+")


def bucket_for(due_date: str, today: date) -> str:
    due = date.fromisoformat(due_date)
    days = (today - due).days
    if days <= 0:
        return "not_due"
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def bucket_index(bucket: str) -> int:
    return BUCKETS.index(bucket)