"""Database layer.

The application opens the database **read-only** by design:

  * URI parameter mode=ro  -> SQLite refuses writes at the file level
  * PRAGMA query_only=ON   -> belt-and-braces at the session level

Co-existing with sql_guard (static analysis) this means a generated query can
never mutate data even if a guard bug slipped through.

Query timeouts: SQLite has no query timeout primitive, so `run_readonly`
executes in a worker thread and calls connection.interrupt() from the caller
after the timeout — aborting the running query.
"""
from __future__ import annotations

import sqlite3
import threading
import time

from src.config.settings import SETTINGS


class QueryError(RuntimeError):
    pass


class TimeoutError_(RuntimeError):
    pass


def connect_readonly(path: str | None = None) -> sqlite3.Connection:
    db = path or SETTINGS.db_path_abs.as_posix()
    conn = sqlite3.connect(
        f"file:{db}?mode=ro",
        uri=True,
        timeout=SETTINGS.sql_timeout_seconds,
        check_same_thread=False,  # queries run in worker threads (timeout support)
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def run_readonly(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    timeout: int | None = None,
    row_limit: int | None = None,
) -> list[dict]:
    """Execute a SELECT with timeout + row cap. Returns list[dict]."""
    timeout = timeout if timeout is not None else SETTINGS.sql_timeout_seconds
    row_limit = row_limit if row_limit is not None else SETTINGS.sql_row_limit

    result: dict = {}

    def _worker():
        try:
            cur = conn.execute("SELECT * FROM ({sql}) LIMIT {limit}".format(sql=sql, limit=row_limit + 1), params)
            rows = [dict(row) for row in cur.fetchall()]  # row_factory -> plain dicts
            result["rows"] = rows
            result["error"] = None
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    # run in a worker thread so the caller can interrupt() a query that exceeds the timeout
    worker_thread = threading.Thread(target=_worker, daemon=True)
    worker_thread.start()
    worker_thread.join(timeout)
    if worker_thread.is_alive():
        conn.interrupt()  # abort the running query
        worker_thread.join(1.0)
        raise TimeoutError_(f"query exceeded {timeout}s")

    if result.get("error"):
        raise QueryError(str(result["error"]))
    rows = result["rows"]
    if len(rows) > row_limit:
        raise QueryError(f"query returned more than {row_limit} rows")
    return rows


if __name__ == "__main__":  # trivial self-check
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        pass
    con = sqlite3.connect(fh.name)
    con.execute("create table t(a int)")
    con.execute("insert into t values (1)")
    con.commit()
    con.close()

    ro = connect_readonly(fh.name)
    assert run_readonly(ro, "select a from t") == [{"a": 1}]
    try:
        ro.execute("insert into t values (2)")  # must fail: file opened ro
        raise SystemExit("FAIL: write succeeded on read-only connection")
    except sqlite3.OperationalError:
        pass
    print("db self-check OK")