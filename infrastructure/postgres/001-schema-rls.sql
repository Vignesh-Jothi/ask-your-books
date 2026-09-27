-- Ask Your Books — production schema (PostgreSQL 15+) with Row-Level Security.
--
-- The SQLite demo intentionally mirrors this logical model (see docs/data-model.md);
-- this file is the canonical definition for real deployments.
-- Tenancy model: users belong to organizations; every accounting row carries
-- org_id. RLS policies make cross-org reads return zero rows (defense in depth
-- behind the application-level sqlglot scoping).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- tenants & users
-- ---------------------------------------------------------------------------
CREATE TABLE organizations (
    org_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    user_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'member',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- chart of accounts
-- ---------------------------------------------------------------------------
CREATE TABLE accounts (
    account_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    group_name  TEXT NOT NULL,          -- Sales Accounts | Purchase Accounts | Sundry Debtors | ...
    kind        TEXT NOT NULL           -- asset | liability | income | expense
);

-- ---------------------------------------------------------------------------
-- vouchers
-- ---------------------------------------------------------------------------
CREATE TABLE vouchers (
    voucher_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    voucher_no  TEXT NOT NULL,
    voucher_type TEXT NOT NULL,         -- Sales | Purchase | Receipt | Payment | Journal | Credit Note
    vdate       DATE NOT NULL,
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    notes       TEXT
);

CREATE TABLE voucher_lines (
    line_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    voucher_id  UUID NOT NULL REFERENCES vouchers(voucher_id) ON DELETE CASCADE,
    account_id  UUID NOT NULL REFERENCES accounts(account_id),
    amount_paise BIGINT NOT NULL,       -- debit positive, credit negative
    CHECK (amount_paise <> 0)
);

-- ---------------------------------------------------------------------------
-- receivables
-- ---------------------------------------------------------------------------
CREATE TABLE bills (
    bill_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    party_account_id   UUID NOT NULL REFERENCES accounts(account_id),
    bill_no            TEXT NOT NULL,
    bill_date          DATE NOT NULL,
    due_date           DATE NOT NULL,
    amount_paise       BIGINT NOT NULL,
    outstanding_paise  BIGINT NOT NULL,          -- reduced by credit notes / receipts
    is_cancelled       BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (outstanding_paise >= 0)
);

-- ---------------------------------------------------------------------------
-- row-level security
-- ---------------------------------------------------------------------------
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE vouchers        ENABLE ROW LEVEL SECURITY;
ALTER TABLE voucher_lines   ENABLE ROW LEVEL SECURITY;
ALTER TABLE bills           ENABLE ROW LEVEL SECURITY;

-- Caller identity flows in via a session GUC set by the connection pooler:
--   SET app.current_user = '<uuid>';
-- app_current_org() resolves the org from the user, never from client input.
CREATE FUNCTION app_current_user() RETURNS UUID IMMUTABLE LANGUAGE SQL AS
  'SELECT NULLIF(current_setting(''app.current_user''), '''')::uuid';
CREATE FUNCTION app_current_org() RETURNS UUID IMMUTABLE LANGUAGE SQL AS
  'SELECT org_id FROM users WHERE user_id = app_current_user()';

-- Every tenant table gets the same policy shape: rows visible only when the
-- resolved org matches the row's org_id. (organizations/users additionally
-- scope by membership so list endpoints are safe.)
CREATE POLICY tenant_org ON organizations FOR ALL
  USING (org_id = app_current_org());
CREATE POLICY tenant_org ON users FOR ALL
  USING (org_id = app_current_org());
CREATE POLICY tenant_org ON accounts FOR ALL
  USING (org_id = app_current_org());
CREATE POLICY tenant_org ON vouchers FOR ALL
  USING (org_id = app_current_org());
CREATE POLICY tenant_org ON voucher_lines FOR ALL
  USING (org_id = app_current_org());
CREATE POLICY tenant_org ON bills FOR ALL
  USING (org_id = app_current_org());

-- ---------------------------------------------------------------------------
-- indexes
-- ---------------------------------------------------------------------------
CREATE INDEX idx_vouchers_org_date     ON vouchers (org_id, vdate);
CREATE INDEX idx_voucher_lines_voucher ON voucher_lines (voucher_id);
CREATE INDEX idx_accounts_org_group    ON accounts (org_id, group_name);
CREATE INDEX idx_bills_org_due         ON bills (org_id, due_date) WHERE NOT is_cancelled;