"""IRAI platform API.  Run:  uvicorn app.main:app --reload   (from backend/)"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from .config import settings

# Demo market mode implies ValueBot offline mode (fictional DEMO/DEMOB/DEMOU companies, no network),
# unless the operator set VALUEBOT_OFFLINE explicitly. Must happen before valuebot is imported.
if not settings.live:
    os.environ.setdefault("VALUEBOT_OFFLINE", "1")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .db import SessionLocal, init_db  # noqa: E402
from .routers import admin, auth, billing, community, content, lab, market, me, monitors, valuebot  # noqa: E402
from .seed import seed_reference  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_create_tables:
        init_db()
    with SessionLocal() as db:
        seed_reference(db)
    yield


app = FastAPI(title="IRAI — Irradiance Research API", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, market, monitors, content, community, me, billing, valuebot, lab, admin):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    from valuebot.config import settings as vb

    from .market import service

    return {"ok": True, "market": service.status(), "valuebot": {"llm": vb.llm_enabled, "offline": vb.offline}}
