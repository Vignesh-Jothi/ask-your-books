"""Financial-year period resolution tests."""
from datetime import date

import pytest

from src.core.fy import Period, resolve_period, shift_year

TODAY = date(2026, 10, 1)  # mid FY 2026-27, in Q2


def test_this_year_is_fy_2026_27():
    period = resolve_period("this year", TODAY)
    assert period == Period("2026-04-01", "2027-03-31", "FY 2026-27")


def test_last_year_is_fy_2025_26():
    period = resolve_period("last year", TODAY)
    assert period == Period("2025-04-01", "2026-03-31", "FY 2025-26")


def test_q1_is_apr_jun():
    period = resolve_period("Q1", TODAY)
    assert period.start == "2026-04-01" and period.end == "2026-06-30"


def test_last_quarter_is_q2_of_current_fy():
    period = resolve_period("last quarter", TODAY)
    assert period == Period("2026-07-01", "2026-09-30", "FY 2026-27 Q2")


def test_same_quarter_last_year():
    # mock resolves follow-up via shift_year; here we assert resolve + shift composition
    quarter_period = resolve_period("Q1", TODAY)
    shifted = shift_year(quarter_period)
    assert shifted == Period("2025-04-01", "2025-06-30", "FY 2025-26 Q1")


def test_canonical_fy_label_parses():
    period = resolve_period("FY 2025-26 Q1", TODAY)
    assert period == Period("2025-04-01", "2025-06-30", "FY 2025-26 Q1")
    second_period = resolve_period("FY 2025-26", TODAY)
    assert second_period == Period("2025-04-01", "2026-03-31", "FY 2025-26")


def test_month_boundaries():
    period = resolve_period("this month", TODAY)
    assert period.start == "2026-10-01" and period.end == "2026-10-31"
    period = resolve_period("last month", TODAY)
    assert period.start == "2026-09-01" and period.end == "2026-09-30"


def test_edge_quarter_end_has_30_days():
    # Jul-Sep (Q2 of FY 2026-27) must end 09-30, never 09-31 (regression)
    period = resolve_period("last quarter", TODAY)
    assert period.end == "2026-09-30"


def test_this_quarter_resolves_by_today():
    period = resolve_period("this quarter", TODAY)
    assert period == Period("2026-10-01", "2026-12-31", "FY 2026-27 Q3")