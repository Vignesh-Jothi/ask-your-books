"""Ask Your Books — FastAPI application.

Serves:
  /api/health        service health + provider info
  /api/chat          the chat assistant (POST, JSON, X-User-Id header)
  /                  the shadcn-style web UI (static)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.config.settings import ROOT, SETTINGS

app = FastAPI(
    title="Ask Your Books",
    description="Natural-language questions over multi-tenant accounting data — read-only, org-scoped, costed.",
    version=SETTINGS.app_version if hasattr(SETTINGS, "app_version") else "1.0.0",
)

app.include_router(router)

FRONTEND = ROOT / "frontend"


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/index.html")


if FRONTEND.exists() and (FRONTEND / "index.html").exists():
    app.mount("/ui", StaticFiles(directory=FRONTEND, html=True), name="ui")