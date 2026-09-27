"""Ageing bucket + money formatting tests."""
from datetime import date

from src.core.ageing import BUCKETS, bucket_for
from src.core.money import paise_to_inr, paise_to_inr_int, fmt_abs

TODAY = date(2026, 10, 1)


def test_bucket_boundaries():
    assert bucket_for("2026-11-01", TODAY) == "not_due"      # future
    assert bucket_for("2026-10-01", TODAY) == "not_due"      # today
    assert bucket_for("2026-09-20", TODAY) == "0-30"         # 11 days
    assert bucket_for("2026-08-20", TODAY) == "31-60"        # 42 days
    assert bucket_for("2026-07-20", TODAY) == "61-90"        # 73 days
    assert bucket_for("2026-01-01", TODAY) == "90+"          # 273 days


def test_bucket_order():
    assert BUCKETS == ("not_due", "0-30", "31-60", "61-90", "90+")


def test_inr_grouping_readme_example():
    # The README example: ₹12,34,567
    assert paise_to_inr_int(paise=123456700) == "₹12,34,567"


def test_inr_with_paise():
    assert paise_to_inr(112233) == "₹1,122.33"
    assert paise_to_inr(-112233) == "-₹1,122.33"


def test_fmt_abs_always_positive():
    # -123,456,700 paise = -₹1,234,567 -> abs -> ₹12,34,567
    assert fmt_abs(-123456700) == "₹12,34,567"
    assert fmt_abs(123456700) == "₹12,34,567"


def test_small_amounts():
    assert paise_to_inr_int(9900) == "₹99"
    assert paise_to_inr(100) == "₹1.00"