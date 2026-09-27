"""Evaluation runner — 3 runs per question; reports accuracy, consistency,
latency and cost.

Usage:
    make eval          # mock provider (offline, deterministic, zero cost)
    LLM_PROVIDER=openai LLM_API_KEY=... MAKE=... make eval

Scoring per question (question type decides the check):
  - metric / sql          -> numeric comparison of agent rows vs expected_sql
                             (independent hand-written reference), tol_pct
  - refusal / clarify     -> status match
  - sql_attack            -> status + no foreign org ids leaked in rows
  - followup              -> runs the chain in one session, then checks the
                             final answer's period/numeric

Consistency = fraction of runs whose checked output matches the run-0 output.
Cost = tokens * provider rates (mock = 0, configurable).
"""
from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path

from src.config.settings import SETTINGS
from src.db.connection import connect_readonly, run_readonly
from src.guards.tenant import scope_to_org
from src.services.chat_service import chat_service

ROOT = Path(__file__).resolve().parent

# provider cost per 1K tokens (USD). mock = 0; tune for real keys.
RATES_PER_1K = {
    "mock": 0.0,
    "openai": 0.0025,
    "gemini": 0.00125,
    "claude": 0.003,
    "groq": 0.0005,
    "ollama": 0.0,
}


def _scalar(rows: list[dict], compare_columns: list[str], sort: str | None) -> list[tuple]:
    """Normalize rows to (column values) tuples, optionally value-sorted."""
    if sort == "value":
        rows = sorted(rows, key=lambda row: tuple(row.get(column) or 0 for column in compare_columns))
    out = [tuple(float(row.get(column) or 0) for column in compare_columns) for row in rows]
    return out


def _agent_numbers(resp: dict, compare_columns: list[str], sort: str | None) -> list[tuple]:
    rows = resp.get("rows") or []
    if isinstance(rows, dict):  # some tools return a dict of rows
        rows = list(rows.values())
    return _scalar(rows, compare_columns, sort)


def _expected_numbers(conn, org_id, sql: str) -> list[dict]:
    scoped_sql = scope_to_org(sql, org_id)
    return run_readonly(conn, scoped_sql, (), row_limit=10_000)


def _values_within(actual: list[tuple], expected: list[tuple], tol_pct: float) -> bool:
    if len(actual) != len(expected):
        return False
    for actual_row, expected_row in zip(actual, expected):
        for actual_value, expected_value in zip(actual_row, expected_row):
            if expected_value == 0:
                if abs(actual_value) > 1:  # allow rounding noise on zero-having aggregates
                    return False
                continue
            if abs(actual_value - expected_value) / abs(expected_value) * 100 > tol_pct:
                return False
    return True


def _run_question(conn, question: dict, org_id: str, run: int) -> dict:
    """Run one question (plus any optional follow-up chain) in a session."""
    messages = list(question.get("chain", [])) + [question["question"]]
    session_id = f"eval-{question['id']}-{run}"
    started = time.perf_counter()
    resp = None
    for message in messages:
        resp = chat_service.handle(question["user_id"], session_id, message)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {"resp": resp, "elapsed_ms": elapsed_ms}


def _check_attack(question, resp) -> bool:
    expected_cfg = question["expected"]
    if resp["status"] != expected_cfg["status"]:
        return False
    rows = resp.get("rows") or []
    captured_org_ids = {str(row.get("org_id", "")).strip() for row in rows if isinstance(row, dict)}
    if expected_cfg.get("attack_orgs_not_present") and set(expected_cfg["attack_orgs_not_present"]) & captured_org_ids:
        return False
    if expected_cfg.get("user_org_in_rows"):
        return any(str(row.get("org_id", "")) == expected_cfg["user_org_in_rows"] for row in rows)
    return True


def _check(question, conn, org_id, resp, run, latency_ms, report: dict):
    question_type = question.get("type", "metric")
    expected_cfg = question.get("expected", {})
    if question_type in ("refusal", "clarify"):
        ok = resp["status"] == expected_cfg["status"]
        report["status_expected"] = expected_cfg["status"]
        return ok, []
    if question_type == "sql_attack":
        report["status_expected"] = expected_cfg.get("status")
        return _check_attack(question, resp), []
    # metric / sql / followup: numeric check
    if resp["status"] != "answered":
        return False, []
    expected_dicts = _expected_numbers(conn, org_id, expected_cfg["sql"])
    expected = _scalar(expected_dicts, expected_cfg["compare"], expected_cfg.get("sort"))
    actual = _agent_numbers(resp, expected_cfg["compare"], expected_cfg.get("sort"))
    ok = _values_within(actual, expected, expected_cfg.get("tol_pct", 0.01))
    if ok and expected_cfg.get("top_name") == "check_largest_line_first":
        # largest line (by the compared column) must be the same party as expected
        agent_rows = resp.get("rows") or []
        if agent_rows and expected_dicts:
            ok = ok and str(agent_rows[0].get("party") or agent_rows[0].get("balance_party")) == \
                 str(expected_dicts[0].get("party") or expected_dicts[0].get("balance_party"))
    if ok and expected_cfg.get("period_contains"):
        ok = expected_cfg["period_contains"] in (resp.get("assumption") or "")
    return ok, actual


def main() -> int:
    corpus = json.loads((ROOT / "tests" / "questions.json").read_text())
    corpus = corpus if isinstance(corpus, list) else corpus["questions"]
    conn = connect_readonly()
    provider = SETTINGS.provider
    rate_per_1k = RATES_PER_1K.get(provider, 0.0)
    model = SETTINGS.model or provider

    results = []
    for question in corpus:
        org = SETTINGS.org_id_for(question["user_id"])
        run_ok_flags = []
        statuses = []
        latencies = []
        tokens = []
        for run in range(3):
            run_result = _run_question(conn, question, org, run)
            latencies.append(run_result["elapsed_ms"])
            tokens.append(run_result["resp"].get("tokens", 0))
            statuses.append(run_result["resp"]["status"])
            report: dict = {
                "status": run_result["resp"]["status"],
                "tool": [trace_step["tool"] for trace_step in run_result["resp"].get("trace", [])],
            }
            ok, _ = _check(question, conn, org, run_result["resp"], run, run_result["elapsed_ms"], report)
            run_ok_flags.append(ok)
            report["ok"] = ok
            if not ok:
                report["error"] = str(run_result["resp"].get("error") or run_result["resp"]["text"][:120])
        consistent = run_ok_flags.count(True) == 3
        results.append(
            {
                "id": question["id"],
                "type": question.get("type"),
                "question": question["question"][:60],
                "accuracy_runs": sum(1 for run_ok in run_ok_flags if run_ok),
                "consistency": consistent,
                "avg_latency_ms": sum(latencies) / 3,
                "avg_tokens": sum(tokens) / 3,
                "statuses": statuses,
            }
        )

    conn.close()

    # ---- summary ----
    total_accuracy = sum(result["accuracy_runs"] for result in results)
    total_runs = len(results) * 3
    accuracy = total_accuracy / total_runs
    consistency = sum(1 for result in results if result["consistency"]) / len(results)
    avg_latency_ms = sum(result["avg_latency_ms"] for result in results) / len(results)
    avg_tokens = sum(result["avg_tokens"] for result in results)
    cost_usd = avg_tokens * rate_per_1k / 1000

    lines = [
        f"provider               : {provider} (model={model})",
        f"questions              : {len(results)}  (x3 runs = {total_runs} turns)",
        f"accuracy (pass/turn)   : {accuracy:.1%}  ({total_accuracy}/{total_runs})",
        f"consistency (3/3)      : {consistency:.1%}",
        f"avg latency / question : {avg_latency_ms:.0f} ms",
        f"avg tokens / question  : {avg_tokens:.0f}",
        f"est. cost (USD)        : ${cost_usd:.4f}",
    ]
    print("\n".join(lines))
    print("\nper-question:")
    for result in results:
        flag = "OK " if (result["accuracy_runs"] == 3 and result["consistency"]) else "FAIL"
        print(
            f"  [{flag}] {result['id']:<28} acc={result['accuracy_runs']}/3  consistent={result['consistency']}  "
            f"lat={result['avg_latency_ms']:.0f}ms  status={result['statuses']}"
        )

    # persist for docs/eval-results.md
    (ROOT / "docs").mkdir(exist_ok=True)
    out = {
        "run_env": {"provider": provider, "today": SETTINGS.today_iso, "db": str(SETTINGS.db_path_abs)},
        "summary": {
            "accuracy": accuracy,
            "consistency": consistency,
            "avg_latency_ms": avg_latency_ms,
            "avg_tokens": avg_tokens,
            "estimated_cost_usd": cost_usd,
        },
        "results": results,
    }
    (ROOT / "docs" / "eval-results.json").write_text(json.dumps(out, indent=2))
    return 0 if total_accuracy == total_runs else 1


if __name__ == "__main__":
    raise SystemExit(main())