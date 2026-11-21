"""Ask IRAI: a page-aware research assistant available on every screen, plus AI news summaries.

The assistant sees a compact snapshot of what the member is looking at (a ticker, theme, portfolio or bot they
own) and answers from it. It explains data and the platform; it does not give personalised buy/sell advice."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import research
from ..db import get_db
from ..market import service
from ..models import AnalystReport, AssistantChat, AssistantUsage, Bot, Portfolio, ResearchTheme, User
from ..security import current_user, limits

log = logging.getLogger("irai.assistant")
router = APIRouter(prefix="/api", tags=["assistant"])
SYM = re.compile(r"^[A-Z0-9.\-=^]{1,20}$")

SYSTEM = (
    "You are IRAI, the research assistant inside Irradiance.ai, an equity research platform (ValueBot DCF valuations, "
    "the Analyst Bot, ADR/ETF monitors, theme pages, portfolio analysis, the Strategy Lab, Monte Carlo and paper-trading "
    "bots). Answer the member's question clearly and briefly (under 200 words unless they ask for more), using the PAGE "
    "CONTEXT JSON when it is relevant and saying which figures came from it; say when data is DEMO or STALE. If the "
    "context lacks what is needed, say so and suggest where on the platform to find it. You may explain concepts, "
    "metrics, risks and how features work. Do not tell the member to buy, sell or hold anything, do not give "
    "personalised advice or price targets, and do not invent numbers or news. Markdown is allowed.")


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AskIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=20)
    path: str | None = Field(None, max_length=300)
    symbol: str | None = Field(None, max_length=20)
    theme: str | None = Field(None, max_length=80)
    portfolio_id: int | None = None
    bot_id: int | None = None
    chat_id: int | None = None
    save: bool = True


def _ticker_ctx(sym: str, db: Session) -> dict[str, Any]:
    c = service.chart(sym, "1y")
    q = c["quote"]
    try:
        info = service.info(sym)
    except Exception:  # noqa: BLE001
        info = {}
    keys = ("name", "sector", "industry", "market_cap", "trailing_pe", "forward_pe", "ev_ebitda", "price_to_sales", "dividend_yield",
            "operating_margin", "profit_margin", "revenue_growth", "earnings_growth", "roe", "debt_to_equity", "beta", "target_mean", "analyst_count")
    out: dict[str, Any] = {"ticker": sym, "price": q.get("price"), "change_pct": q.get("change_pct"), "currency": q.get("currency"),
                           "data_label": q.get("source"), "returns": research._returns(c["history"]), **{k: info.get(k) for k in keys}}
    try:
        rt = research.ratings(sym)
        out["quant_rating"] = {"overall": rt.get("overall_grade"), "factors": {k: v.get("grade") for k, v in (rt.get("factors") or {}).items()}}
    except Exception:  # noqa: BLE001
        pass
    try:
        out["recent_headlines"] = [{"title": h.get("title"), "source": h.get("source"), "published": h.get("published")} for h in research.headlines(sym, limit=8)]
    except Exception:  # noqa: BLE001
        pass
    r = db.scalar(select(AnalystReport).where(AnalystReport.symbol == sym, AnalystReport.status == "done").order_by(AnalystReport.finished_at.desc()))
    if r and r.result:
        a = r.result.get("analysis") or {}
        out["latest_analyst_bot_note"] = {"generated_at": r.result.get("generated_at"), "headline": a.get("headline"), "summary": a.get("summary")}
    return out


def context(body: AskIn, user: User, db: Session) -> dict[str, Any]:
    ctx: dict[str, Any] = {"page": body.path, "today": dt.date.today().isoformat(), "member_plan": user.plan}
    try:
        if body.symbol and SYM.match(body.symbol.upper()):
            ctx["ticker"] = _ticker_ctx(body.symbol.upper(), db)
        if body.theme:
            t = db.scalar(select(ResearchTheme).where(ResearchTheme.slug == body.theme))
            if t and (t.owner_id is None or t.owner_id == user.id):
                ctx["theme"] = {"name": t.name, "description": t.description, "tickers": t.tickers[:25], "drivers": [d.get("name") for d in t.drivers]}
        if body.portfolio_id:
            p = db.get(Portfolio, body.portfolio_id)
            if p and p.user_id == user.id:
                from .. import portfolio as pf
                a = pf.analyze([{"symbol": h.symbol, "quantity": h.quantity, "cost_basis": h.cost_basis} for h in p.holdings], p.cash, p.benchmark, with_grades=False)
                ctx["portfolio"] = {"summary": a["summary"], "risk": {k: v for k, v in a["risk"].items() if k != "most_correlated"}, "sectors": a["sectors"],
                                    "flags": [f["text"] for f in a["flags"]],
                                    "positions": [{k: x.get(k) for k in ("symbol", "weight", "unrealized_pct", "ret_12m", "sector")} for x in a["positions"][:25]]}
        if body.bot_id:
            b = db.get(Bot, body.bot_id)
            if b and b.user_id == user.id:
                ctx["bot"] = {"name": b.name, "mode": b.mode, "strategy": b.strategy, "params": b.params, "symbols": b.symbols, "status": b.status,
                              "stop_loss_pct": b.stop_loss_pct, "take_profit_pct": b.take_profit_pct, "daily_auto_close": b.daily_auto_close,
                              "backtest": ((b.backtest or {}).get("stats") or {}), "paper_trading": True}
    except Exception as e:  # noqa: BLE001
        ctx["context_error"] = f"{type(e).__name__}"
    return ctx


def _quota(db: Session, user: User) -> tuple[int, int | None]:
    cap = limits(user).get("assistant_messages_per_day")
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    row = db.scalar(select(AssistantUsage).where(AssistantUsage.user_id == user.id, AssistantUsage.day == day))
    used = row.count if row else 0
    if cap is not None and used >= cap:
        raise HTTPException(402, f"You've used today's {cap} Ask IRAI messages. Upgrade for more, or come back tomorrow.")
    if row:
        row.count += 1
    else:
        db.add(AssistantUsage(user_id=user.id, day=day, count=1))
    db.commit()
    return used + 1, cap


@router.post("/assistant")
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from valuebot.config import settings as vb

    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be from the user")
    used, cap = _quota(db, user)
    ctx = context(body, user, db)
    if not vb.llm_enabled:
        t = ctx.get("ticker")
        hint = (f"{t['ticker']} trades at {t.get('price')} ({t.get('data_label')}); quant rating {(t.get('quant_rating') or {}).get('overall', 'n/a')}. "
                if t else "")
        reply = (hint + "The AI assistant isn't configured on this server yet, so I can't answer free-form questions. "
                 "Try the Analyst tab on a ticker, the Methodology page, or Learn.")
        return {"reply": reply, "engine": "rules", "used": used, "limit": cap, "chat_id": _save_chat(db, user, body, reply)}
    msgs = [{"role": m.role, "content": m.content} for m in body.messages[-12:]]
    msgs[-1] = {"role": "user", "content": f"PAGE CONTEXT (JSON):\n{json.dumps(ctx, default=str)[:30_000]}\n\nQUESTION:\n{msgs[-1]['content']}"}
    try:
        import anthropic

        resp = anthropic.Anthropic(api_key=vb.anthropic_api_key).messages.create(model=vb.fast_model, max_tokens=900, system=SYSTEM, messages=msgs)
        reply = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("assistant failed: %s", e)
        raise HTTPException(503, "The assistant is busy; try again in a moment.")
    chat_id = _save_chat(db, user, body, reply)
    return {"reply": reply, "engine": "claude", "used": used, "limit": cap, "chat_id": chat_id,
            "context": [k for k in ("ticker", "theme", "portfolio", "bot") if k in ctx]}


def _save_chat(db: Session, user: User, body: AskIn, reply: str) -> int | None:
    if not body.save:
        return None
    msgs = [m.model_dump() for m in body.messages] + [{"role": "assistant", "content": reply}]
    chat = db.get(AssistantChat, body.chat_id) if body.chat_id else None
    if chat and chat.user_id != user.id:
        chat = None
    now = dt.datetime.now(dt.timezone.utc)
    if chat:
        chat.messages, chat.updated_at = msgs[-40:], now
    else:
        first = body.messages[0].content.strip().replace("\n", " ")
        chat = AssistantChat(user_id=user.id, title=(first[:80] + ("…" if len(first) > 80 else "")), messages=msgs[-40:],
                             context={k: v for k, v in {"path": body.path, "symbol": body.symbol, "theme": body.theme, "bot_id": body.bot_id}.items() if v},
                             updated_at=now)
        db.add(chat)
    db.commit()
    return chat.id


@router.get("/assistant/chats")
def chats(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AssistantChat).where(AssistantChat.user_id == user.id).order_by(AssistantChat.updated_at.desc()).limit(50)).all()
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat(), "messages": len(c.messages or []), "context": c.context} for c in rows]


@router.get("/assistant/chats/{cid}")
def chat(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(AssistantChat, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Chat not found")
    return {"id": c.id, "title": c.title, "messages": c.messages, "context": c.context, "updated_at": c.updated_at.isoformat()}


@router.delete("/assistant/chats/{cid}")
def delete_chat(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(AssistantChat, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Chat not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── AI news summary ──────────────────────────────────────────────────────────────────────────────
_news_cache: dict[str, tuple[float, dict]] = {}
NEWS_TTL = 2 * 3600


@router.get("/insight/{symbol}/news-summary")
def news_summary(symbol: str):
    from valuebot.config import settings as vb

    sym = symbol.upper()
    if not SYM.match(sym):
        raise HTTPException(400, "Invalid ticker")
    hit = _news_cache.get(sym)
    if hit and time.time() - hit[0] < NEWS_TTL:
        return hit[1]
    heads = research.headlines(sym, limit=15)
    base = {"symbol": sym, "count": len(heads), "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": [{"n": i + 1, "title": h.get("title"), "url": h.get("url"), "source": h.get("source")} for i, h in enumerate(heads)]}
    if not heads:
        return {**base, "summary": None, "engine": None}
    if not vb.llm_enabled:
        return {**base, "summary": None, "engine": "rules"}
    listing = "\n".join(f"[{i + 1}] {h.get('title')} ({h.get('source')}, {h.get('published')})" for i, h in enumerate(heads))
    try:
        import anthropic

        resp = anthropic.Anthropic(api_key=vb.anthropic_api_key).messages.create(
            model=vb.fast_model, max_tokens=500,
            system=("Summarise recent news headlines about one stock for an investor. Use only the headlines given (you have not "
                    "read the articles, so don't claim details beyond them). Output Markdown: 3-5 bullets grouping related stories, "
                    "each ending with the headline numbers in brackets like [2][5], then one line 'Overall tone: positive, mixed or "
                    "negative' with a reason. No investment advice."),
            messages=[{"role": "user", "content": f"Ticker: {sym}\nHeadlines:\n{listing}"}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        out = {**base, "summary": text, "engine": "claude"}
    except Exception as e:  # noqa: BLE001
        log.warning("news summary failed: %s", e)
        out = {**base, "summary": None, "engine": "error"}
    _news_cache[sym] = (time.time(), out)
    return out
