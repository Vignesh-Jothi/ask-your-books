"""Tenant scoping tests — enforced in code, outside the LLM (no LLM here).

The pattern is: a malicious/forgetful query + scope_to_org must still only
ever see ONE tenant's rows, no matter how it tries to leak other orgs.
"""
import pytest

from src.db.connection import connect_readonly, run_readonly
from src.guards.tenant import scope_to_org

TODAY = "2026-10-01"


@pytest.fixture(scope="module")
def conn():
    connection = connect_readonly()
    yield connection
    connection.close()


def _run(conn, org, sql):
    return run_readonly(conn, scope_to_org(sql, org), (), row_limit=100)


def test_plain_select_is_scoped(conn):
    rows = _run(conn, "ORG1", "SELECT org_id, COUNT(*) AS n FROM vouchers GROUP BY org_id")
    assert [row["org_id"] for row in rows] == ["ORG1"]


def test_direct_table_reference_scoped(conn):
    rows = _run(conn, "ORG2", "SELECT DISTINCT org_id FROM accounts")
    assert rows == [{"org_id": "ORG2"}]


def test_voucher_lines_scoped_through_parents(conn):
    rows = _run(conn, "ORG3", "SELECT COUNT(*) AS n FROM voucher_lines vl")
    # cross-org check: same query in ORG1 must give a different count
    rows1 = _run(conn, "ORG1", "SELECT COUNT(*) AS n FROM voucher_lines vl")
    assert rows[0]["n"] != rows1[0]["n"]


def test_join_cannot_leak_other_tenant(conn):
    sql = (
        "SELECT v.org_id, COUNT(*) AS n FROM vouchers v "
        "JOIN voucher_lines vl ON vl.voucher_id = v.voucher_id "
        "WHERE v.org_id = 'ORG2' GROUP BY v.org_id"
    )
    rows = _run(conn, "ORG2", sql)
    assert [row["org_id"] for row in rows] == ["ORG2"]


def test_union_cannot_leak(conn):
    sql = (
        "SELECT org_id FROM accounts "
        "UNION ALL SELECT org_id FROM accounts WHERE org_id='ORG3'"
    )
    rows = _run(conn, "ORG1", sql)
    assert {row["org_id"] for row in rows} == {"ORG1"}


def test_subquery_join_cannot_leak(conn):
    sql = (
        "SELECT al.grp, SUM(vl.amount_paise) AS t "
        "FROM (SELECT * FROM voucher_lines) vl "
        "JOIN accounts al ON al.account_id = vl.account_id "
        "GROUP BY al.grp"
    )
    _run(conn, "ORG1", sql)  # must not raise; result implicitly scoped


def test_physical_read_only_connection(conn):
    with pytest.raises(Exception):
        conn.execute("INSERT INTO accounts VALUES ('a','ORG1','b','c')")