"""Ask Your Books — FastAPI application.

Serves:
  /api/health        service health + provider info
  /api/chat          the chat assistant (POST, JSON, X-User-Id header)
  /                  the shadcn-style web UI (static)
"""
from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.config.settings import ROOT, SETTINGS


def _ensure_db() -> None:
    """Seed books.db on first run so a bare `make app` always has sample data."""
    if SETTINGS.db_path_abs.exists():
        return
    from seed import build  # local import: only pay for it when seeding

    SETTINGS.db_path_abs.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SETTINGS.db_path_abs)
    try:
        stats = build(conn, orgs=SETTINGS.seed_orgs, months=SETTINGS.seed_months,
                      per_month=SETTINGS.seed_vouchers_per_month, seed=SETTINGS.seed_fixed_seed)
    finally:
        conn.close()
    print(f"[startup] books.db missing — seeded: {stats}", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_db()
    yield


app = FastAPI(
    title="Ask Your Books",
    description="Natural-language questions over multi-tenant accounting data — read-only, org-scoped, costed.",
    version=SETTINGS.app_version if hasattr(SETTINGS, "app_version") else "1.0.0",
    lifespan=lifespan,
)

app.include_router(router)

FRONTEND = ROOT / "frontend"


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/index.html")


if FRONTEND.exists() and (FRONTEND / "index.html").exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND, html=True), name="ui")