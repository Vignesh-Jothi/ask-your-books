"""SQL read-only guard.

Enforced in code, outside the LLM. Pipeline (in order):

1. Strip SQL comments  (blocks naughty SQL hidden in comments)
2. Parse with sqlglot -> must be exactly ONE statement, and of type SELECT/WITH
3. Belt-and-braces: case-insensitive scan for forbidden keywords
   (INSERT/UPDATE/DELETE/DROP/ATTACH/PRAGMA/... including in identifiers)
4. Multi-statement attempts (`; select ...; drop ...`) fail at step 2.

On top of this, src/db/connection.py opens the database `mode=ro` and sets
`PRAGMA query_only=ON`, so even a guard miss physically cannot mutate the db.

                       +----------------------+
                       |  every generated SQL  |
                       |     (metric + T2S)    |
                       +----------+-----------+
                                  v
                       sql_guard.assert_read_only()
                                  v
                       tenant.scope_to_org(started from user session)
                                  v
                       connection with timeout + row limit
"""
from __future__ import annotations

import re

import sqlglot
from sqlglot import exp as glot_exp

from src.config.settings import SETTINGS

COMMENT_RE = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)
FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(kw for group in SETTINGS.forbidden_keywords for kw in group) + r")\b",
    re.IGNORECASE,
)


class SQLGuardError(ValueError):
    pass


_READ_ONLY_TYPES = (glot_exp.Select, glot_exp.With)


def strip_comments(sql: str) -> str:
    return COMMENT_RE.sub(" ", sql)


def _is_read_only_type(statement: glot_exp.Expression) -> bool:
    # UNION / INTERSECT / EXCEPT of selects is read-only; SQLite can also emit
    # SetOperation for a bare `SELECT ... UNION ALL SELECT ...`.
    if isinstance(statement, glot_exp.SetOperation):
        return all(_is_read_only_type(expr) for expr in statement.expressions)
    return isinstance(statement, _READ_ONLY_TYPES)

def assert_read_only(sql: str) -> str:
    """Return the comment-stripped SQL if safe, else raise SQLGuardError."""
    cleaned = strip_comments(sql)
    if not cleaned.strip():
        raise SQLGuardError("empty SQL")

    # Case-insensitive keyword scan (covers keywords hidden in identifiers too)
    if FORBIDDEN_RE.search(cleaned):
        hit = FORBIDDEN_RE.search(cleaned).group(0)
        raise SQLGuardError(f"forbidden keyword: {hit}")

    try:
        statements = sqlglot.parse(cleaned, read="sqlite")
    except Exception as exc:  # noqa: BLE001 — any parse failure is a refusal
        raise SQLGuardError(f"unparseable SQL: {exc}") from exc

    if len(statements) != 1:
        raise SQLGuardError("multiple statements are not allowed")

    stmt = statements[0]
    if not _is_read_only_type(stmt):
        raise SQLGuardError(
            f"only SELECT is allowed, got: {type(stmt).__name__.upper()}"
        )
    return cleaned


def _tables_referenced(statement) -> set[str]:
    return {table.name.lower() for table in statement.find_all(glot_exp.Table) if not table.catalog}


def is_tenant_table(table: str) -> bool:
    return table.lower() in {tenant_table.lower() for tenant_table in SETTINGS.tenant_tables}


def assert_only_allowed_tables(statement) -> None:
    """Every bare (non-subquery-internal) table reference must be a known entity."""
    allowed = {
        *(tenant_table.lower() for tenant_table in SETTINGS.tenant_tables),
        "organizations", "users",
    }
    cte_names = {cte.alias.lower() for cte in statement.find_all(glot_exp.CTE)}
    for table in statement.find_all(glot_exp.Table):
        if not table.catalog and table.name.lower() not in allowed and table.name.lower() not in cte_names:
            raise SQLGuardError(f"unknown table: {table.name}")


def has_org_filter(statement, org_id: str) -> bool:
    """Best-effort check that the org predicate is present somewhere."""
    needle = f"ORG{org_id.upper().replace('-', '')}" if org_id.upper().startswith("ORG") else org_id.lower()
    for literal in statement.find_all(glot_exp.Literal):
        if str(literal.this).lower() in {org_id.lower(), org_id.upper()}:
            return True
    return False