# Infrastructure

```
infrastructure/
├── docker/            Dockerfile (builds the image AND seeds books.db) + compose.yaml
├── postgres/          001-schema-rls.sql — canonical prod schema + Row-Level Security
│                      002-observability-views.sql — per-org usage / drift probes
└── deployment/        systemd unit (hardened, ReadOnlyDirectories) + nginx (TLS + rate limit)
```

## Running the app

- Dev: `make setup && make db && make app` → http://localhost:8000 (UI: `/ui`)
- Docker: `docker compose -f infrastructure/docker/compose.yaml up --build`

## Postgres + RLS (production path)

The demo runs SQLite for zero-friction eval, but the canonical schema is
Postgres. Apply `001-schema-rls.sql`; RLS keyed on a GUC:

```sql
SET app.current_user = '<user-uuid>';
SELECT * FROM vouchers;  -- only this user's org, enforced by the database
```

The app layer still rewrites scoping (defense in depth). `app_current_org()`
resolves the org from the **authenticated user** — never from client input.

## Observability

- `logs/` — JSONL per-request trace + guard events (off by default in tests).
- `002-observability-views.sql` — `org_usage` read-model view; under RLS it
  returns exactly one row (your org) and is the standing cross-tenant probe.
- `/api/health` reports provider, model, database, org count, log line count.

## Deployment notes

- The systemd unit runs the app as `www-data` with `NoNewPrivileges`,
  `ProtectSystem=strict` and the SQLite file chmod'd `0440` → even a
  compromised worker cannot modify the ledger.
- nginx terminates TLS, rate-limits `/api/` (per-IP burst), and sits in front
  of uvicorn on 127.0.0.1.
- Real secrets: `/etc/ask-your-books.env` (mode 600); the repo only carries
  `.env.example`.