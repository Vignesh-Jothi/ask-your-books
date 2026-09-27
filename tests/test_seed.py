"""Seed sanity + guard-rule tests that hit the seeded DB (no LLM)."""

import sqlite3

import pytest

from src.config.settings import SETTINGS


@pytest.fixture(scope="module")
def conn():
    db = str(SETTINGS.db_path_abs)
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def test_three_organizations(conn):
    count = conn.execute("SELECT COUNT(*) count FROM organizations").fetchone()["count"]
    assert count == 3


def test_two_users_per_org(conn):
    for row in conn.execute("SELECT org_id, COUNT(*) count FROM users GROUP BY org_id"):
        assert row["count"] == 2


def test_accounts_and_parties_present(conn):
    count = conn.execute("SELECT COUNT(*) count FROM accounts").fetchone()["count"]
    assert count >= 150  # organisations x (~23 ledgers + 40 parties)
    group_count = conn.execute("SELECT COUNT(DISTINCT grp) count FROM accounts").fetchone()["count"]
    assert group_count >= 7


def test_vouchers_span_18_months(conn):
    lo, hi = conn.execute("SELECT MIN(vdate), MAX(vdate) FROM vouchers").fetchone()
    assert lo == "2025-04-01" or lo >= "2025-04-01"
    assert "2026-09" in hi


def test_double_entry_lines_sum_to_zero(conn):
    bad = conn.execute(
        """SELECT v.voucher_id, SUM(vl.amount_paise) s
           FROM vouchers v JOIN voucher_lines vl ON vl.voucher_id = v.voucher_id
           WHERE v.is_cancelled = 0
           GROUP BY v.voucher_id HAVING s <> 0 LIMIT 3"""
    ).fetchall()
    assert bad == []


def test_cancelled_vouchers_exist(conn):
    count = conn.execute("SELECT COUNT(*) count FROM vouchers WHERE is_cancelled = 1").fetchone()["count"]
    assert count > 0


def test_shared_party_in_two_orgs(conn):
    rows = conn.execute(
        "SELECT org_id, COUNT(*) count FROM accounts WHERE name = 'Global Traders' GROUP BY org_id"
    ).fetchall()
    assert {row["org_id"] for row in rows} == {"ORG1", "ORG2"}


def test_overdue_and_not_due_bills_exist(conn):
    today = SETTINGS.today
    overdue_count = conn.execute(
        "SELECT COUNT(*) count FROM bills WHERE outstanding_paise > 0 AND due_date < ?", (today,)
    ).fetchone()["count"]
    not_due_count = conn.execute(
        "SELECT COUNT(*) count FROM bills WHERE outstanding_paise > 0 AND due_date >= ?", (today,)
    ).fetchone()["count"]
    assert overdue_count > 0 and not_due_count > 0


def test_credit_notes_exist(conn):
    count = conn.execute("SELECT COUNT(*) count FROM vouchers WHERE vtype = 'Credit Note'").fetchone()["count"]
    assert count > 0