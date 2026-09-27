"""Money helpers. Amounts are integer paise everywhere in storage/SQL.

Presentation-only conversion to Indian format:  ₹12,34,567.89  (lakh grouping).
"""
from __future__ import annotations


def _group_inr(rupees: int) -> str:
    """1234567 -> '12,34,567' (last 3 digits, then groups of 2)."""
    rupees_text = str(rupees)
    if len(rupees_text) <= 3:
        return rupees_text
    head, tail = rupees_text[:-3], rupees_text[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])  # insert each 2-digit group at the front
        head = head[:-2]
    return f"{','.join(groups)},{tail}"


def paise_to_inr(paise: int) -> str:
    """112233 -> '₹1,122.33'; -112233 -> '₹-1,122.33'."""
    sign = "-" if paise < 0 else ""
    rupees, paise_fraction = divmod(abs(paise), 100)
    return f"{sign}₹{_group_inr(rupees)}.{paise_fraction:02d}"


def paise_to_inr_int(paise: int) -> str:
    """Whole-rupee Indian format: 123456700 -> '₹1,23,45,670'."""
    sign = "-" if paise < 0 else ""
    return f"{sign}₹{_group_inr(abs(paise) // 100)}"


def fmt_abs(paise: int) -> str:
    """Positive, human-readable amount (domain rule: answers show positive INR)."""
    return paise_to_inr_int(abs(paise))