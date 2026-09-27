"""Financial-year period resolution.

Indian financial year: 1 Apr - 31 Mar.  Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.

Periods are resolved against a reference date (TODAY, config/env). Everything
returns inclusive date strings [start, end] so callers/sql only see ranges.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.config.settings import SETTINGS

FY_START_MONTH = 4  # April


class PeriodError(ValueError):
    """Raised when a period phrase cannot be resolved — callers ask for clarification."""


@dataclass(frozen=True)
class Period:
    start: str  # YYYY-MM-DD inclusive
    end: str   # YYYY-MM-DD inclusive
    label: str  # human label, e.g. "FY 2025-26 (Q1, Apr-Jun)"


def _fy_year(day: date) -> int:
    """Financial year that `day` falls in: Apr 2025 - Mar 2026 -> 2025."""
    return day.year - 1 if day.month < FY_START_MONTH else day.year


def fy_bounds(fy_year: int) -> tuple[date, date]:
    return date(fy_year, 4, 1), date(fy_year + 1, 3, 31)


def _quarter_bounds(fy_year: int, quarter: int) -> tuple[date, date]:
    if not 1 <= quarter <= 4:
        raise PeriodError(f"unknown quarter {quarter}")
    from calendar import monthrange

    start_month = FY_START_MONTH + (quarter - 1) * 3
    end_month = start_month + 2
    return date(fy_year, start_month, 1), date(fy_year, end_month, monthrange(fy_year, end_month)[1])


def resolve_period(phrase: str, today: date | None = None) -> Period | None:
    """Resolve a relative/absolute period phrase. None = not a period phrase.

    Phrases (case-insensitive):
      fy 2024-25 | fy25 | this fiscal/financial/current year | last year / last fiscal year
      this/last/next quarter | q1..q4 | this month | last month | yyyy-mm .. yyyy-mm
      default: an open period for the current FY so far.
    """
    if today is None:
        today = date.fromisoformat(SETTINGS.today)
    label = phrase.strip() if phrase else ""
    phrase_lower = label.lower()

    # canonical labels we ourselves generate: "FY 2025-26 Q1" or "FY 2025-26"
    import re as _re

    match = _re.match(r"^fy (\d{4})-(\d{2})(?: q(\d))?$", phrase_lower)
    if match:
        fy_year = int(match.group(1))
        quarter_text = match.group(3)
        if quarter_text:
            period_start, period_end = _quarter_bounds(fy_year, int(quarter_text))
            return Period(period_start.isoformat(), period_end.isoformat(), f"FY {fy_year}-{str(fy_year + 1)[-2:]} Q{quarter_text}")
        period_start, period_end = fy_bounds(fy_year)
        return Period(period_start.isoformat(), period_end.isoformat(), f"FY {fy_year}-{str(fy_year + 1)[-2:]}")

    # absolute range "2025-04 .. 2025-06"
    if ".." in phrase_lower or " to " in phrase_lower or " - " in phrase_lower:
        separator = ".." if ".." in phrase_lower else (" to " if " to " in phrase_lower else " - ")
        parts = [part.strip() for part in phrase_lower.split(separator)]
        if len(parts) == 2:
            try:
                return Period(parts[0], parts[1], label)
            except ValueError:
                return None

    def first_day(day: date) -> str:
        return day.isoformat()

    def last_day(day: date) -> str:
        from calendar import monthrange
        return day.replace(day=monthrange(day.year, day.month)[1]).isoformat()

    # "FY 25 Q1" style
    if phrase_lower.startswith("fy"):
        rest = phrase_lower[2:].strip()
        if "q" in rest:
            qyear_text, qnum_text = rest.split("q")
            quarter_num = int(qnum_text)
            fy_year = _fy_year(today) if not qyear_text.strip() else int(qyear_text.strip())
            period_start, period_end = _quarter_bounds(fy_year, quarter_num)
            return Period(period_start.isoformat(), period_end.isoformat(), f"FY {fy_year}-{str(fy_year + 1)[-2:]} Q{quarter_num}")

    if phrase_lower in ("this fiscal year", "this financial year", "current fiscal year", "current financial year", "this year", "current year", "fy", "this fy", "this financial", "this fiscal"):
        fy_year = _fy_year(today)
        period_start, period_end = fy_bounds(fy_year)
        return Period(period_start.isoformat(), period_end.isoformat(), f"FY {fy_year}-{str(fy_year + 1)[-2:]}")

    if phrase_lower in ("last year", "last fiscal year", "last financial year", "previous year", "previous fiscal year", "last fy", "previous fy"):
        fy_year = _fy_year(today) - 1
        period_start, period_end = fy_bounds(fy_year)
        return Period(period_start.isoformat(), period_end.isoformat(), f"FY {fy_year}-{str(fy_year + 1)[-2:]}")

    if "quarter" in phrase_lower or phrase_lower.startswith("q"):
        quarter_num = None
        for token in phrase_lower.split():
            if token.startswith("q") and token[1:].isdigit():
                quarter_num = int(token[1:])
        relative = "this"  # default: the quarter containing TODAY
        if quarter_num is None:
            if "last quarter" in phrase_lower:
                relative = "last"
            elif "next quarter" in phrase_lower:
                relative = "next"
            elif "this quarter" in phrase_lower:
                relative = "this"
        fy_year = _fy_year(today)
        current_quarter = (today.month - FY_START_MONTH) // 3 + 1
        if relative == "last":
            # the quarter before the one containing TODAY (borrow into the
            # previous FY if the quarter number wraps below 1)
            quarter_num = quarter_num or current_quarter - 1
            if quarter_num < 1:
                quarter_num += 4
                fy_year -= 1
        elif relative == "next":
            quarter_num = quarter_num or current_quarter + 1
            if quarter_num > 4:
                quarter_num -= 4
                fy_year += 1
        else:
            quarter_num = quarter_num or current_quarter
        period_start, period_end = _quarter_bounds(fy_year, quarter_num)
        return Period(period_start.isoformat(), period_end.isoformat(), f"FY {fy_year}-{str(fy_year + 1)[-2:]} Q{quarter_num}")

    if phrase_lower in ("this month", "current month"):
        return Period(first_day(today), last_day(today), "this month")
    if phrase_lower in ("last month", "previous month"):
        this_month_first = today.replace(day=1)
        from datetime import timedelta
        last_month_first = (this_month_first - timedelta(days=1)).replace(day=1)
        return Period(last_month_first.isoformat(), last_day(last_month_first), "last month")

    return None


def shift_year(period: Period, years: int = -1) -> Period:
    """Shift a resolved period by whole years (for follow-ups like 'same last year').
    Relabels FY/quarter labels so downstream display & re-resolution stay accurate."""
    import re

    start = date.fromisoformat(period.start)
    end = date.fromisoformat(period.end)
    shifted_start = start.replace(year=start.year + years)
    shifted_end = end.replace(year=end.year + years)
    label = period.label
    match = re.match(r"^FY (\d{4})-(\d{2})(.*)$", label)
    if match:
        fy_year = int(match.group(1)) + years
        label = f"FY {fy_year}-{str(fy_year + 1)[-2:]}{match.group(3)}"
    return Period(shifted_start.isoformat(), shifted_end.isoformat(), label)


def today() -> date:
    return date.fromisoformat(SETTINGS.today)