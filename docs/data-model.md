# Data Model

Canonical definition: `infrastructure/postgres/001-schema-rls.sql` (PostgreSQL,
with RLS). The demo runs the same logical model on SQLite
(`seed.py` → `books.db`) so the eval and the app are identical.

## Entities

| Entity | Org-scoped | Key fields | Notes |
|--------|:----------:|------------|-------|
| `organizations` | — | `org_id PK, name` | tenants |
| `users` | ✓ | `user_id PK, org_id FK, name, role` | login identity |
| `accounts` | ✓ | `account_id PK, org_id FK, name, group_name` | chart of accounts; `group_name` ∈ Sales Accounts, Purchase Accounts, Direct Expenses, Indirect Expenses, Duties & Taxes, Sundry Debtors, Sundry Creditors, Bank … |
| `vouchers` | ✓ | `voucher_id PK, org_id FK, voucher_no, voucher_type, vdate, is_cancelled` | the bookkeeping header; cancelled rows are **never** included in metrics |
| `voucher_lines` | ✓¹ | `line_id PK, org_id FK, voucher_id FK, account_id FK, amount_paise` | debit > 0, credit < 0; scoped through its **vouchers** join (¹ the physical table carries org_id for Postgres RLS, but the SQLite sandbox never trusts line-level org) |
| `bills` | ✓ | `bill_id PK, org_id FK, party_account_id FK, bill_no, bill_date, due_date, amount_paise, outstanding_paise, is_cancelled` | receivables; `outstanding_paise` shrinks as credit notes/receipts post |

## Domain rules

1. **Money is integer paise**, never floats. `112233` = ₹1,122.33.
2. **Debit positive, credit negative** in `voucher_lines`. Double-entry seed
   sums to exactly zero per voucher (asserted in tests/test_seed.py).
3. **FY = Apr–Mar**. `2025-04-01..2026-03-31` is FY 2025-26. Eval date is
   frozen at `2026-10-01` (FY 2026-27, Q2) so ageing buckets are stable.
4. **Receivable balance per party** = Σ lines on accounts in
   Sundry Debtors/Creditors (uncancelled). A negative balance → net debtor.
5. **Ageing buckets** (whole-day, inclusive of boundary):
   `not_due` = due_date ≥ today, `0-30` = 1..30 days overdue, `31-60`,
   `61-90`, `90+`.
6. **Cancelled vouchers** and **cancelled bills** are filtered everywhere.

## Tenancy

- Every table is org-scoped. The app injects `org_id` in code (SQLite
  sandbox: sqlglot rewrite) and at the database (Postgres: RLS), so no query
  path can cross tenants even if a caller "forgets".

## Demo seed (books.db)

| Measure | Value |
|---------|------:|
| Organizations | 3 |
| Users | 2 + 1 + 2 = 5 |
| Accounts | 185 |
| Vouchers | 10,194 (188 cancelled) |
| Voucher lines | 20,012 |
| Bills | 7,677 |
| Span | Apr 2025 – Sep 2026 |
| Shared party across orgs | "Global Traders" (isolation probe) |

Full entity dictionary with field docs: `okf/data/entity_catalog.json` and
`okf/README.md`.