"""Standalone ValueBot: HTTP API + static web UI.  Run:  uvicorn valuebot.server:app --reload

Inside the IRAI platform the same routes are mounted at /api/valuebot (see backend/app/main.py).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router

WEB = Path(__file__).resolve().parent.parent / "valuebot_web"

app = FastAPI(title="ValueBot", version="1.1")
app.include_router(router, prefix="/api")
if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
