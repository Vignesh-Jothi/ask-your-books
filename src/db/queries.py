"""Shared SQL for metric tools (hand-written, parameterized, org-scoped by the guard).

Convention: every metric query references tenant tables **without** org filters
here — the guard's scope_to_org() injects them per session. Two exceptions are
documented inline (bills/vouchers patterns rely on join-scoping which the
guard handles transparently).

Placeholders are sqlite `?`.
"""
from __future__ import annotations

VOUCHER_LINES_IN_PERIOD = """
SELECT al.account_id, al.grp, SUM(vl.amount_paise) AS total_paise
FROM voucher_lines vl
JOIN vouchers v ON v.voucher_id = vl.voucher_id
JOIN accounts al ON al.account_id = vl.account_id
WHERE v.is_cancelled = 0
  AND v.vdate BETWEEN ? AND ?
GROUP BY al.account_id, al.grp
"""

NET_BY_GROUP = """
SELECT al.grp, SUM(vl.amount_paise) AS total_paise
FROM voucher_lines vl
JOIN vouchers v ON v.voucher_id = vl.voucher_id
JOIN accounts al ON al.account_id = vl.account_id
WHERE v.is_cancelled = 0
  AND v.vdate BETWEEN ? AND ?
GROUP BY al.grp
"""

PARTY_TOTALS = """
SELECT al.name AS party, SUM(vl.amount_paise) AS total_paise
FROM voucher_lines vl
JOIN vouchers v ON v.voucher_id = vl.voucher_id
JOIN accounts al ON al.account_id = vl.account_id
WHERE v.is_cancelled = 0
  AND al.grp IN ('Sundry Debtors', 'Sundry Creditors')
  AND v.vdate BETWEEN ? AND ?
GROUP BY al.name
"""

AGEING_QUERY = """
SELECT b.party_account_id, al.name AS party,
       b.due_date, b.outstanding_paise
FROM bills b
JOIN accounts al ON al.account_id = b.party_account_id
WHERE b.outstanding_paise > 0
"""

OUTSTANDING_BY_PARTY = """
SELECT al.name AS party,
       SUM(b.outstanding_paise) AS outstanding_paise,
       COUNT(b.bill_id) AS bills
FROM bills b
JOIN accounts al ON al.account_id = b.party_account_id
WHERE b.outstanding_paise > 0
GROUP BY al.name
"""

OUTSTANDING_BILLS = """
SELECT al.name AS party, b.bill_id, b.bill_date, b.due_date,
       b.amount_paise, b.outstanding_paise
FROM bills b
JOIN accounts al ON al.account_id = b.party_account_id
WHERE b.outstanding_paise <> 0
"""