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

from sqlalchemy import text  # noqa: E402

from .db import SessionLocal, init_db  # noqa: E402
from .middleware import RateLimit, RequestContext, configure_logging  # noqa: E402
from .routers import admin, analyst, assistant, auth, bots, portfolio, billing, community, content, insight, lab, market, me, monitors, valuebot, workspace  # noqa: E402
from .seed import seed_reference  # noqa: E402


configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_create_tables:
        init_db()
    with SessionLocal() as db:
        seed_reference(db)
    yield


app = FastAPI(title="IRAI: Irradiance Research API", version="1.0", lifespan=lifespan)
app.add_middleware(RateLimit)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"])
app.add_middleware(RequestContext)

for r in (auth, market, monitors, content, community, me, billing, valuebot, lab, admin, insight, workspace, analyst, portfolio, bots, assistant):
    app.include_router(r.router)
app.include_router(insight.buzz_router)


@app.get("/api/health")
def health():
    """Liveness + readiness: fails (503) if the database is unreachable."""
    from fastapi.responses import JSONResponse
    from valuebot.config import settings as vb

    from .market import service

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    body = {"ok": db_ok, "database": "ok" if db_ok else "unreachable", "market": service.status(),
            "valuebot": {"llm": vb.llm_enabled, "offline": vb.offline}}
    return body if db_ok else JSONResponse(body, status_code=503)


_llm_check: dict = {}


@app.get("/api/health/llm")
def health_llm():
    """Verifies the Claude API key and both configured models with a tiny request. Cached for 10 minutes so
    this public endpoint can't be used to spend tokens."""
    import time

    from valuebot.config import settings as vb

    if not vb.llm_enabled:
        return {"enabled": False, "reason": "ANTHROPIC_API_KEY not set (or VALUEBOT_OFFLINE=1)"}
    if _llm_check and time.time() - _llm_check["at"] < 600:
        return _llm_check["result"]
    import anthropic

    client = anthropic.Anthropic(api_key=vb.anthropic_api_key)
    models = {}
    for role, model in (("main", vb.model), ("fast", vb.fast_model)):
        t0 = time.time()
        try:
            r = client.messages.create(model=model, max_tokens=5, messages=[{"role": "user", "content": "Reply with OK."}])
            text_out = "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip()
            models[role] = {"model": model, "ok": True, "reply": text_out[:20], "ms": round((time.time() - t0) * 1000)}
        except Exception as e:  # noqa: BLE001
            models[role] = {"model": model, "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    result = {"enabled": True, "ok": all(m["ok"] for m in models.values()), "models": models,
              "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _llm_check.update(at=time.time(), result=result)
    return result
