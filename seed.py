#!/usr/bin/env python3
"""Deterministic seed for books.db  (fixed random seed -> reproducible).

3 organizations x ~30 ledgers x ~40 parties x 18 months of vouchers
(Apr 2025 - Sep 2026, ~175 vouchers/org/month = ~3,150/org) with seasonality,
overdue invoices, credit notes, a party name shared by two orgs.

Run:  python seed.py            (uses config: db.path, seed.*)
"""
from __future__ import annotations

import os
import random
import sqlite3
from datetime import date, timedelta

from src.config.settings import SETTINGS

# ---------------------------------------------------------------- dataset

ORGS = [
    ("ORG1", "Acme Traders Pvt Ltd"),
    ("ORG2", "Sunrise Impex LLP"),
    ("ORG3", "Kaveri Distributors"),
]

USERS = [
    ("U101", "ORG1", "Ramesh"), ("U102", "ORG1", "Priya"),
    ("U201", "ORG2", "Arun"),   ("U202", "ORG2", "Meera"),
    ("U301", "ORG3", "Divya"),  ("U302", "ORG3", "Karthik"),
]

LEDGER_GROUPS = [
    ("Bank Accounts", ["HDFC Bank", "ICICI Bank", "State Bank of India"]),
    ("Sales Accounts", ["Sales: Domestic", "Sales: Export", "Sales: Wholesale", "Sales: Retail"]),
    ("Purchase Accounts", [
        "Purchases: Raw Material", "Purchases: Domestic", "Purchases: Import",
        "Purchases: Trading", "Purchases: Packaging",
    ]),
    ("Direct Expenses", ["Freight & Forwarding", "Power & Fuel", "Repairs & Maintenance", "Commission Paid"]),
    ("Indirect Expenses", ["Salaries & Wages", "Rent & Lease", "Office & Administration", "Professional Fees", "Insurance"]),
    ("Duties & Taxes", ["GST Input Credit", "GST Output Liability"]),
    ("Sundry Debtors", []),   # parties (who owes us) — filled per org
    ("Sundry Creditors", []), # parties (we owe)    — filled per org
]

PARTY_FIRST = ["Global", "Rising", "New", "Classic", "Evergreen", "Prime", "Bright", "Sun", "Star", "Ocean",
               "Metro", "Crown", "Golden", "Royal", "United", "Heritage", "Summit", "Delta", "Orbit", "Zenith"]
PARTY_LAST = ["Traders", "Impex", "Enterprises", "Industries", "Stores", "Suppliers", "Marketing", "Logistics",
              "Distributors", "Retail", "Wholesale", "Associates", "Corporation", "Export House", "Agencies", "Merchants"]

# one party deliberately shared by two orgs (tenant-isolation test material)
SHARED_PARTY = "Global Traders"

SALES_TEMPLATE = [
    ("Sales: Domestic", 60), ("Sales: Export", 15), ("Sales: Wholesale", 15), ("Sales: Retail", 10),
]
PURCHASE_TEMPLATE = [
    ("Purchases: Raw Material", 40), ("Purchases: Domestic", 25), ("Purchases: Import", 15),
    ("Purchases: Trading", 10), ("Purchases: Packaging", 10),
]
EXPENSE_TEMPLATE = [
    ("Direct Expenses", "Freight & Forwarding", 35), ("Direct Expenses", "Power & Fuel", 20),
    ("Direct Expenses", "Commission Paid", 15), ("Indirect Expenses", "Salaries & Wages", 100),
    ("Indirect Expenses", "Rent & Lease", 60), ("Indirect Expenses", "Office & Administration", 25),
    ("Indirect Expenses", "Professional Fees", 10), ("Indirect Expenses", "Insurance", 8),
    ("Duties & Taxes", "GST Input Credit", 5),
]

# seasonal multipliers per calendar month (festive quarters heavier)
SEASONALITY = {4: 0.8, 5: 0.9, 6: 0.9, 7: 1.0, 8: 1.0, 9: 1.1, 10: 1.4, 11: 1.6, 12: 1.5, 1: 1.1, 2: 1.0, 3: 1.2}

# ---------------------------------------------------------------- helpers

def _months(start: date, end: date):
    """Yield the first day of each calendar month from start through end."""
    current = start.replace(day=1)
    while current <= end:
        yield current
        current = (current + timedelta(days=32)).replace(day=1)


def _fmt(day: date) -> str:
    return day.isoformat()


def _money(rng: random.Random, lo: int, hi: int) -> int:
    """Random amount in paise between lo..hi rupees, rounded to whole rupees."""
    return rng.randint(lo, hi) * 100


# ---------------------------------------------------------------- main

def build(conn: sqlite3.Connection, *, orgs=3, months=18, per_month=175, seed=42) -> dict:
    rng = random.Random(seed)
    cur = conn.cursor()

    cur.executescript("""
    DROP TABLE IF EXISTS bills;
    DROP TABLE IF EXISTS voucher_lines;
    DROP TABLE IF EXISTS vouchers;
    DROP TABLE IF EXISTS accounts;
    DROP TABLE IF EXISTS users;
    DROP TABLE IF EXISTS organizations;

    CREATE TABLE organizations (
      org_id TEXT PRIMARY KEY, name TEXT NOT NULL);

    CREATE TABLE users (
      user_id TEXT PRIMARY KEY,
      org_id TEXT NOT NULL REFERENCES organizations(org_id),
      name TEXT NOT NULL);

    CREATE TABLE accounts (
      account_id TEXT PRIMARY KEY,
      org_id TEXT NOT NULL REFERENCES organizations(org_id),
      name TEXT NOT NULL,
      grp TEXT NOT NULL);

    CREATE TABLE vouchers (
      voucher_id TEXT PRIMARY KEY,
      org_id TEXT NOT NULL REFERENCES organizations(org_id),
      vtype TEXT NOT NULL,
      vdate TEXT NOT NULL,
      number TEXT NOT NULL,
      is_cancelled INTEGER NOT NULL DEFAULT 0);

    CREATE TABLE voucher_lines (
      voucher_id TEXT NOT NULL REFERENCES vouchers(voucher_id),
      account_id TEXT NOT NULL REFERENCES accounts(account_id),
      amount_paise INTEGER NOT NULL);

    CREATE TABLE bills (
      bill_id TEXT PRIMARY KEY,
      org_id TEXT NOT NULL REFERENCES organizations(org_id),
      party_account_id TEXT NOT NULL REFERENCES accounts(account_id),
      voucher_id TEXT NOT NULL REFERENCES vouchers(voucher_id),
      bill_date TEXT NOT NULL,
      due_date TEXT NOT NULL,
      amount_paise INTEGER NOT NULL,
      outstanding_paise INTEGER NOT NULL);

    CREATE INDEX idx_vouchers_org_date ON vouchers(org_id, vdate);
    CREATE INDEX idx_lines_voucher ON voucher_lines(voucher_id);
    CREATE INDEX idx_lines_account ON voucher_lines(account_id);
    CREATE INDEX idx_bills_org_due ON bills(org_id, due_date);
    CREATE INDEX idx_bills_party ON bills(party_account_id);
    """)

    org_rows = ORGS[:orgs]
    cur.executemany("INSERT INTO organizations VALUES (?, ?)", org_rows)
    cur.executemany("INSERT INTO users VALUES (?, ?, ?)",
                    [user_row for user_row in USERS
                     if any(user_row[1] == org_row[0] for org_row in org_rows)])

    start = date(2025, 4, 1)
    end = start + timedelta(days=30 * months + months // 2)
    month_list = list(_months(start, end))[:months]

    n_accounts = n_vouchers = n_lines = n_bills = n_cancelled = 0
    all_bills = []  # (org, party_account_id, voucher_id, bill_date, due_date, amount_paise, outstanding)

    for org_id, org_name in org_rows:
        # ------- accounts (ledgers + parties)
        parties_debtors = set()
        parties_creditors = set()
        for party_index in range(40):
            if org_id in ("ORG1", "ORG2") and party_index == 5:
                name = SHARED_PARTY   # deliberately shared across two orgs
            else:
                name = f"{rng.choice(PARTY_FIRST)} {rng.choice(PARTY_LAST)}"
            (parties_creditors if party_index % 3 == 0 else parties_debtors).add(name)

        account_rows = []  # (account_id, org_id, name, grp)
        account_index = 0
        for group_name, seeds in LEDGER_GROUPS:
            names = list(seeds)
            if group_name == "Sundry Debtors":
                names = sorted(parties_debtors)
            elif group_name == "Sundry Creditors":
                names = sorted(parties_creditors)
            for account_name in names:
                account_index += 1
                account_rows.append((f"A_{org_id}_{account_index:04d}", org_id, account_name, group_name))

        by_name = {}
        for account_id, acc_org_id, account_name, group_name in account_rows:
            by_name.setdefault(group_name, {})[account_name] = account_id
            cur.execute("INSERT INTO accounts VALUES (?, ?, ?, ?)", (account_id, acc_org_id, account_name, group_name))
        n_accounts += len(account_rows)

        debtors = sorted(parties_debtors)
        creditors = sorted(parties_creditors)
        banks = [by_name["Bank Accounts"][account_name] for account_name in by_name["Bank Accounts"]]
        sales_accs = [by_name["Sales Accounts"][account_name] for account_name in sorted(by_name["Sales Accounts"])]
        purch_accs = [by_name["Purchase Accounts"][account_name] for account_name in sorted(by_name["Purchase Accounts"])]

        # ------- vouchers
        voucher_counter = 0

        def add_voucher(vtype: str, vdate: date, lines: list[tuple[str, int]], cancelled: bool) -> str:
            nonlocal voucher_counter, n_vouchers, n_lines, n_cancelled
            voucher_counter += 1
            vid = f"V_{org_id}_{voucher_counter:05d}"
            number = f"{vtype[:2].upper()}-{vdate.strftime('%y%m')}-{voucher_counter % 1000:03d}"
            cancelled_i = 1 if cancelled else 0
            cur.execute("INSERT INTO vouchers VALUES (?, ?, ?, ?, ?, ?)",
                        (vid, org_id, vtype, _fmt(vdate), number, cancelled_i))
            n_vouchers += 1
            n_cancelled += cancelled_i
            if not cancelled:
                for acct, amt in lines:
                    cur.execute("INSERT INTO voucher_lines VALUES (?, ?, ?)", (vid, acct, amt))
                    n_lines += 1
            return vid

        def party_credit_note(vdate: date, debtor: str, amount: int) -> str:
            """Credit note: reduces what the debtor owes (Dr sales, Cr party)."""
            return add_voucher("Credit Note", vdate, [
                (by_name["Sales Accounts"]["Sales: Domestic"], amount),
                (by_name["Sundry Debtors"][debtor], -amount),
            ], rng.random() < 0.01)

        for month_index, month in enumerate(month_list):
            season = SEASONALITY[month.month]
            for _ in range(round(per_month * season) if month_index > 0 else per_month):
                vtype_pick = rng.choices(
                    ["Sales", "Purchase", "Receipt", "Payment", "Journal", "Credit Note", "Debit Note"],
                    weights=[42, 34, 9, 9, 2, 2, 2])[0]
                vdate = month + timedelta(days=rng.randint(1, 28))
                cancelled = rng.random() < 0.02

                debtor = rng.choice(debtors)
                creditor = rng.choice(creditors)

                if vtype_pick == "Sales":
                    sale_amt = _money(rng, 20_000, 600_000)
                    cur_sales_acc = rng.choices(
                        [account for account in sales_accs],
                        [template[1] for template in SALES_TEMPLATE if template[0] in by_name["Sales Accounts"]],
                    )[0]
                    vid = add_voucher("Sales", vdate, [
                        (by_name["Sundry Debtors"][debtor], sale_amt),
                        (cur_sales_acc, -sale_amt),
                    ], cancelled)
                    # bill: receivable (positive)
                    due_date = vdate + timedelta(days=rng.randint(15, 60))
                    outstanding_paise = int(sale_amt * _paid_fraction(rng, vdate)) if not cancelled else 0
                    all_bills.append((org_id, by_name["Sundry Debtors"][debtor], vid, _fmt(vdate),
                                      _fmt(due_date), sale_amt, outstanding_paise))
                    n_bills += 1

                elif vtype_pick == "Purchase":
                    buy_amt = _money(rng, 15_000, 400_000)
                    cur_purch = rng.choices(
                        [account for account in purch_accs],
                        [template[1] for template in PURCHASE_TEMPLATE if template[0] in by_name["Purchase Accounts"]],
                    )[0]
                    vid = add_voucher("Purchase", vdate, [
                        (cur_purch, buy_amt),
                        (by_name["Sundry Creditors"][creditor], -buy_amt),
                    ], cancelled)
                    due_date = vdate + timedelta(days=rng.randint(0, 45))
                    outstanding_paise = -int(buy_amt * _paid_fraction(rng, vdate)) if not cancelled else 0
                    all_bills.append((org_id, by_name["Sundry Creditors"][creditor], vid, _fmt(vdate),
                                      _fmt(due_date), -buy_amt, outstanding_paise))
                    n_bills += 1

                elif vtype_pick in ("Receipt", "Payment"):
                    # bank movement against a party (no bill linkage needed for eval)
                    amt = _money(rng, 5_000, 200_000)
                    bank = rng.choice(banks)
                    if vtype_pick == "Receipt":
                        party = by_name["Sundry Debtors"][debtor]
                        add_voucher("Receipt", vdate, [(bank, amt), (party, -amt)], cancelled)
                    else:
                        party = by_name["Sundry Creditors"][creditor]
                        add_voucher("Payment", vdate, [(party, amt), (bank, -amt)], cancelled)

                elif vtype_pick == "Journal":
                    amt = _money(rng, 2_000, 50_000)
                    account_first, account_second = rng.sample(
                        [account for account in sales_accs + purch_accs], 2)
                    add_voucher("Journal", vdate, [(account_first, amt), (account_second, -amt)], cancelled)

                elif vtype_pick == "Credit Note":
                    amt = _money(rng, 2_000, 40_000)  # ~2% of sales value
                    vid = party_credit_note(vdate, debtor, amt)
                else:  # Debit Note
                    amt = _money(rng, 2_000, 40_000)
                    vid = add_voucher("Debit Note", vdate, [
                        (by_name["Sundry Creditors"][creditor], amt),
                        (rng.choice(purch_accs), -amt),
                    ], cancelled)

    cur.executemany(
        "INSERT INTO bills (bill_id, org_id, party_account_id, voucher_id, bill_date, due_date, amount_paise, outstanding_paise) VALUES (?,?,?,?,?,?,?,?)",
        [(f"B_{org_id}_{bill_index + 1:06d}", org_id, party, voucher_id, bill_date, due_date, amount_paise, outstanding_paise)
         for bill_index, (org_id, party, voucher_id, bill_date, due_date, amount_paise, outstanding_paise)
         in enumerate(all_bills)],
    )

    conn.commit()
    return {
        "organizations": orgs,
        "accounts": n_accounts,
        "vouchers": n_vouchers,
        "lines": n_lines,
        "bills": len(all_bills),
        "cancelled": n_cancelled,
    }


def _paid_fraction(rng: random.Random, vdate: date) -> float:
    """Older bills are more likely settled; newer ones still outstanding."""
    today = date.fromisoformat(SETTINGS.today)
    age_days = (today - vdate).days
    if age_days > 400:
        return rng.uniform(0.95, 1.0)
    if age_days > 250:
        return rng.uniform(0.7, 0.97)
    if age_days > 120:
        return rng.uniform(0.4, 0.85)
    if age_days > 30:
        return rng.uniform(0.1, 0.55)
    return rng.uniform(0.0, 0.25)


def main() -> None:
    db_path = SETTINGS.db_path_abs
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        stats = build(conn, orgs=SETTINGS.seed_orgs, months=SETTINGS.seed_months,
                      per_month=SETTINGS.seed_vouchers_per_month, seed=SETTINGS.seed_fixed_seed)
    finally:
        conn.close()
    print(f"seeded {db_path}")
    for stat_name, stat_value in stats.items():
        print(f"  {stat_name}: {stat_value}")


if __name__ == "__main__":
    main()