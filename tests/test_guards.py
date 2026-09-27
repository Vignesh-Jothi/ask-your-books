"""SQL read-only guard tests (no LLM)."""
import pytest

from src.guards.sql_guard import SQLGuardError, assert_read_only, strip_comments

# every one of these MUST be refused
ATTACKS = [
    "SELECT 1; INSERT INTO accounts VALUES ('x')",
    "INSERT INTO accounts (account_id) VALUES ('x')",
    "UPDATE vouchers SET vdate = '2026-01-01'",
    "DELETE FROM bills",
    "DROP TABLE vouchers",
    "ALTER TABLE accounts ADD COLUMN x TEXT",
    "CREATE TABLE evil (x TEXT)",
    "ATTACH DATABASE 'secret.db' AS s",
    "DETACH DATABASE s",
    "PRAGMA query_only=OFF",
    "VACUUM",
    "SELECT * FROM accounts WHERE org_id='ORG1' ; UPDATE users SET name='x'",
    "WITH t AS (SELECT 1) SELECT * FROM t; DROP TABLE users",
    "INSERT INTO accounts (account_id) VALUES " + "-- hidden\n" + "('x')",
]

# comment-hidden DDL is neutralized: what remains is a benign SELECT
COMMENT_NEUTRALIZED = [
    "SELECT * FROM accounts -- then DROP TABLE vouchers",
    "SELECT * FROM accounts /* ; DELETE FROM vouchers */",
]

GOOD = [
    "SELECT * FROM accounts WHERE org_id = 'ORG1'",
    "SELECT grp, SUM(amount_paise) AS t FROM voucher_lines vl JOIN vouchers v ON vl.voucher_id = v.voucher_id JOIN accounts al ON al.account_id = vl.account_id WHERE v.vdate BETWEEN '2026-04-01' AND '2026-06-30' AND v.is_cancelled = 0 GROUP BY al.grp",
    "SELECT v.vtype, COUNT(*) FROM vouchers v WHERE v.org_id = 'ORG1' GROUP BY v.vtype",
    "WITH recent AS (SELECT * FROM vouchers WHERE org_id = 'ORG1') SELECT COUNT(*) FROM recent",
    "SELECT * FROM accounts",
    "SELECT a.* FROM accounts a",
]


def test_every_attack_is_refused():
    for sql in ATTACKS:
        with pytest.raises(SQLGuardError):
            assert_read_only(sql), f"should have refused: {sql}"


def test_comment_hidden_ddl_is_neutralized():
    for sql in COMMENT_NEUTRALIZED:
        cleaned = assert_read_only(sql)  # must NOT raise
        assert "drop" not in cleaned.lower() and "delete" not in cleaned.lower()


def test_good_queries_pass():
    for sql in GOOD:
        assert assert_read_only(sql), f"should have passed: {sql}"


def test_unknown_table_is_refused_at_tool_layer():
    import sqlglot

    from src.guards.sql_guard import assert_only_allowed_tables, SQLGuardError

    stmt = sqlglot.parse_one("SELECT * FROM evil_table", read="sqlite")
    with pytest.raises(SQLGuardError):
        assert_only_allowed_tables(stmt)


def test_comments_are_stripped():
    assert "DROP" not in strip_comments("SELECT 1 -- DROP TABLE users").upper()


def test_multiple_statements_detected_even_with_only_selects():
    with pytest.raises(SQLGuardError):
        assert_read_only("SELECT 1; SELECT 2")