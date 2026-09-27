"""Tenant scoping — enforced in code, outside the LLM.

strategy: rewrite the generated SQL so every tenant table is replaced by a
derived table that hard-filters org_id, e.g.

    SELECT ... FROM accounts   ->  SELECT ... FROM
        (SELECT * FROM accounts WHERE org_id = 'ORG1') AS accounts

The org predicate is part of the *table definition*, so a crafted question
like "ignore the org filter" cannot remove it — the LLM never writes (and
never sees) the final SQL. voucher_lines has no org_id column, so it is
scoped through its parent tables (vouchers + accounts) instead.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp as glot_exp

from src.config.settings import SETTINGS

# tables that carry org_id directly
_TENANT_TABLES = {table for table in SETTINGS.tenant_tables if table != "voucher_lines"}

_ORG_TMPL = "SELECT * FROM {table} WHERE org_id = '{org_id}'"
_VL_TMPL = (
    "SELECT vl.* FROM voucher_lines AS vl "
    "JOIN (SELECT * FROM vouchers WHERE org_id = '{org_id}') AS v "
    "ON vl.voucher_id = v.voucher_id"
)


def _scope_table(node: glot_exp.Table, org_id: str) -> None:
    name = node.name.lower()
    if name not in _TENANT_TABLES or node.catalog:
        return
    alias = node.alias or name
    inner = sqlglot.parse_one(_ORG_TMPL.format(table=name, org_id=org_id))
    node.replace(inner.subquery(alias))


def _scope_voucher_lines(node: glot_exp.Table, org_id: str) -> None:
    if node.name.lower() != "voucher_lines" or node.catalog:
        return
    alias = node.alias or "voucher_lines"
    inner = sqlglot.parse_one(_VL_TMPL.format(org_id=org_id))
    node.replace(inner.subquery(alias))


def scope_to_org(sql: str, org_id: str) -> str:
    """Return SQL that physically cannot read another tenant's rows."""
    statement = sqlglot.parse_one(sql, read="sqlite")
    for table in list(statement.find_all(glot_exp.Table)):
        if not hasattr(table, "catalog") or not table.catalog:
            _scope_table(table, org_id)
            _scope_voucher_lines(table, org_id)
    return statement.sql(dialect="sqlite")