"""Metric tools — hand-written, parameterized SQL for the recurring accounting
questions. This is the *correct-numbers* core: the LLM never computes figures,
it only picks a tool + arguments; every number comes from these queries
(guarded + org-scoped before execution).

Each handler: fn(conn, org_id, today, **args) -> MetricResult
MetricResult: dataclass(rows: list[dict], sql: str, period_label: str|None)
"""
from __future__ import annotations

from dataclasses import dataclass

from src.core.ageing import BUCKETS, bucket_for
from src.core.fy import Period, resolve_period
from src.db import queries
from src.guards.sql_guard import SQLGuardError, assert_only_allowed_tables, assert_read_only, strip_comments
from src.guards.tenant import scope_to_org
from src.db.connection import QueryError, run_readonly

EXPENSE_GROUPS = ("Purchase Accounts", "Direct Expenses", "Indirect Expenses", "Duties & Taxes")
INCOME_GROUPS = ("Sales Accounts",)


@dataclass
class MetricResult:
    rows: list
    sql: str
    period_label: str | None = None


def _exec(conn, sql: str, params: tuple, org_id: str, row_limit: int = 10_000) -> list[dict]:
    """Guard pipeline: read-only check -> tenant scoping -> run with limits."""
    cleaned = assert_read_only(sql)
    import sqlglot

    statement = sqlglot.parse_one(cleaned, read="sqlite")
    assert_only_allowed_tables(statement)
    scoped_sql = scope_to_org(cleaned, org_id)
    return run_readonly(conn, scoped_sql, params, row_limit=row_limit)


def _resolve(label: str | None) -> tuple[str | None, Period | None]:
    """Resolve a period phrase to (canonical label, Period) — never raises."""
    if not label:
        return None, None
    try:
        period = resolve_period(label)
        return period.label, period
    except Exception:
        return None, None


# ---------------------------------------------------------------- handlers

def h_receivables_ageing(conn, org_id, today, age: str | None = None, **_):
    """Receivables bucketed by days overdue (see src/core/ageing.py)."""
    rows = _exec(conn, queries.AGEING_QUERY, (), org_id)
    buckets = {bucket_name: {"bucket": bucket_name, "bills": 0, "total_paise": 0} for bucket_name in BUCKETS}
    for row in rows:
        bucket_name = bucket_for(row["due_date"], today)
        buckets[bucket_name]["bills"] += 1
        buckets[bucket_name]["total_paise"] += abs(row["outstanding_paise"])
    result_rows = [buckets[bucket_name] for bucket_name in BUCKETS]
    if age == "overdue":
        result_rows = [row for row in result_rows if row["bucket"] != "not_due"]
    return MetricResult(result_rows, queries.AGEING_QUERY, "as of " + today.isoformat())


def h_expense_by_group(conn, org_id, today, period: str | None = None, filter_groups: list | None = None, **_):
    """Net spending per expense ledger group over a period (always shown positive)."""
    label, period_obj = _resolve(period)
    if period_obj is None:
        period_obj = resolve_period("this year")
        label = period_obj.label
    rows = _exec(conn, queries.NET_BY_GROUP, (period_obj.start, period_obj.end), org_id)
    groups = tuple(group for group in EXPENSE_GROUPS if group in (filter_groups or EXPENSE_GROUPS))
    result_rows = [
        {"grp": group, "total_paise": next((abs(row["total_paise"]) for row in rows if row["grp"] == group), 0)}
        for group in groups
    ]
    result_rows = [row for row in result_rows if row["total_paise"] > 0]
    return MetricResult(result_rows, queries.NET_BY_GROUP, label)


def h_income_by_group(conn, org_id, today, period: str | None = None, **_):
    """Net income per sales ledger group over a period (always shown positive)."""
    label, period_obj = _resolve(period)
    if period_obj is None:
        period_obj = resolve_period("this year")
        label = period_obj.label
    rows = _exec(conn, queries.NET_BY_GROUP, (period_obj.start, period_obj.end), org_id)
    result_rows = [
        {"grp": row["grp"], "total_paise": abs(row["total_paise"])}
        for row in rows if row["grp"] in INCOME_GROUPS and row["total_paise"] != 0
    ]
    return MetricResult(result_rows, queries.NET_BY_GROUP, label)


def h_fy_comparison(conn, org_id, today, metric: str = "expense", period: str | None = None, **_):
    """Same period this FY vs previous FY (Q1 vs Q1, etc.) — or full FY vs FY."""
    label, period_obj = _resolve(period)
    if period_obj is None:
        period_obj = resolve_period("this year")
        label = period_obj.label

    def total(for_period: Period) -> int:
        rows = _exec(conn, queries.NET_BY_GROUP, (for_period.start, for_period.end), org_id)
        groups = EXPENSE_GROUPS if metric == "expense" else INCOME_GROUPS
        return sum(abs(row["total_paise"]) for row in rows if row["grp"] in groups)

    from src.core.fy import shift_year

    this_period_total, prior_year_total = total(period_obj), total(shift_year(period_obj))
    change_pct = round((this_period_total - prior_year_total) / prior_year_total * 100, 1) if prior_year_total else None
    result_rows = [{"metric": metric, "this_period": this_period_total, "prior_year": prior_year_total, "change_pct": change_pct}]
    return MetricResult(result_rows, queries.NET_BY_GROUP, label)


def h_top_parties(conn, org_id, today, metric: str = "receivable", period: str | None = None, limit: int = 10, **_):
    """Rank parties by receivable (who owes us) or payable (who we owe)."""
    label, period_obj = _resolve(period)
    if period_obj is None:
        period_obj = resolve_period("this year")
        label = period_obj.label
    rows = _exec(conn, queries.PARTY_TOTALS, (period_obj.start, period_obj.end), org_id)
    rows = [row for row in rows if row["party"]]
    if metric in ("receivable", "debtor", "owes"):
        rows.sort(key=lambda row: -row["total_paise"])
        rows = [row for row in rows if row["total_paise"] > 0][:limit]
        result_rows = [{"party": row["party"], "balance_paise": row["total_paise"]} for row in rows]
    elif metric in ("payable", "creditor"):
        rows.sort(key=lambda row: row["total_paise"])
        rows = [row for row in rows if row["total_paise"] < 0][:limit]
        result_rows = [{"party": row["party"], "balance_paise": abs(row["total_paise"])} for row in rows]
    else:
        result_rows = []
    return MetricResult(result_rows, queries.PARTY_TOTALS, label)


def h_outstanding_bills(conn, org_id, today, party: str | None = None, limit: int = 20, **_):
    """Bill-wise outstanding, optionally filtered to one party, due-date ordered."""
    rows = _exec(conn, queries.OUTSTANDING_BILLS, (), org_id)
    if party:
        rows = [row for row in rows if party.lower() in row["party"].lower()]
    rows = sorted(rows, key=lambda row: row["due_date"])
    result_rows = [
        {"party": row["party"], "bill_id": row["bill_id"], "due_date": row["due_date"],
         "amount_paise": row["amount_paise"], "outstanding_paise": row["outstanding_paise"]}
        for row in rows[:limit]
    ]
    return MetricResult(result_rows, queries.OUTSTANDING_BILLS, "current outstanding")


def h_sql_query(conn, org_id, today, sql: str = "", description: str = "", **_):
    """Sandboxed text-to-SQL escape hatch. Guarded read-only + org-scoped here."""
    if not sql or not sql.strip().lower().startswith("select"):
        raise SQLGuardError("only SELECT statements are allowed")
    cleaned = assert_read_only(sql)
    import sqlglot

    statement = sqlglot.parse_one(cleaned, read="sqlite")
    assert_only_allowed_tables(statement)
    scoped_sql = scope_to_org(cleaned, org_id)
    try:
        rows = run_readonly(conn, scoped_sql, (), row_limit=500)
    except QueryError as exc:
        # a sandbox/runtime failure (unknown column in a rewritten join, bad
        # expression, ...) is a REFUSAL, not a crash — the user query never
        # touched anything outside its tenant
        raise SQLGuardError(f"query could not run safely: {exc}") from exc
    return MetricResult(rows, scoped_sql, description or "custom query")