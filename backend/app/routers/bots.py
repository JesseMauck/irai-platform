"""IRAI AlgoTrader (paper trading): paper accounts, strategy and webhook bots, risk controls, signals,
tear sheets and the live-vs-backtest track record. Simulated money only; nothing reaches a broker."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import paper
from ..algo import tearsheet
from ..algo.strategies import REGISTRY
from ..db import get_db
from ..models import Bot, BotSignal, BotSleeve, PaperAccount, PaperTrade, User
from ..security import PLAN_ORDER, require_plan

log = logging.getLogger("irai.bots")
router = APIRouter(prefix="/api", tags=["algotrader"])
pro = require_plan("pro")
SYM = re.compile(r"^[A-Z0-9.\-=^]{1,20}$")
MAX_ACCOUNTS, MAX_BOTS = 5, 20


# ── schemas ──────────────────────────────────────────────────────────────────────────────────────
class AccountIn(BaseModel):
    name: str = Field("Paper account", min_length=1, max_length=80)
    starting_cash: float = Field(100_000, ge=1_000, le=paper.MAX_ACCOUNT_CASH)


class Funding(BaseModel):
    account_id: int
    capital: float = Field(gt=0, le=paper.MAX_ACCOUNT_CASH)


class BotIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(None, max_length=2000)
    mode: str = Field("strategy", pattern="^(strategy|webhook)$")
    strategy: str | None = None
    params: dict[str, float] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list, max_length=20)
    max_position_pct: float = Field(1.0, gt=0, le=1)
    stop_loss_pct: float | None = Field(None, gt=0, le=0.9)
    take_profit_pct: float | None = Field(None, gt=0, le=10)
    daily_auto_close: bool = False
    accounts: list[Funding] = Field(default_factory=list, max_length=MAX_ACCOUNTS)


class BotPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    status: str | None = Field(None, pattern="^(running|paused)$")
    max_position_pct: float | None = Field(None, gt=0, le=1)
    stop_loss_pct: float | None = Field(None, ge=0, le=0.9)  # 0 clears
    take_profit_pct: float | None = Field(None, ge=0, le=10)
    daily_auto_close: bool | None = None
    params: dict[str, float] | None = None


class DraftIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


def _syms(xs: list[str]) -> list[str]:
    out = []
    for s in xs:
        s = s.strip().upper()
        if not SYM.match(s):
            raise HTTPException(422, f"Invalid symbol: {s}")
        if s not in out:
            out.append(s)
    return out


def _own_bot(db: Session, bid: int, user: User) -> Bot:
    b = db.get(Bot, bid)
    if not b or b.user_id != user.id:
        raise HTTPException(404, "Bot not found")
    return b


def _own_acct(db: Session, aid: int, user: User) -> PaperAccount:
    a = db.get(PaperAccount, aid)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Account not found")
    return a


# ── paper accounts ───────────────────────────────────────────────────────────────────────────────
def _acct_out(db: Session, a: PaperAccount, detail: bool = False) -> dict:
    sleeves = db.scalars(select(BotSleeve).where(BotSleeve.account_id == a.id)).all()
    sv = [(s, paper.sleeve_equity(s)) for s in sleeves]
    equity = a.cash + sum(v for _, v in sv)
    out = {"id": a.id, "name": a.name, "starting_cash": a.starting_cash, "cash": a.cash, "equity": equity,
           "return": equity / a.starting_cash - 1 if a.starting_cash else None,
           "bots": [{"bot_id": s.bot_id, "name": s.bot.name, "capital": s.capital, "equity": v} for s, v in sv]}
    if detail:
        out["positions"] = [{"bot": s.bot.name, "symbol": p.symbol, "quantity": p.quantity, "avg_cost": p.avg_cost} for s in sleeves for p in s.positions]
        ids = [s.id for s in sleeves]
        trades = db.scalars(select(PaperTrade).where(PaperTrade.sleeve_id.in_(ids)).order_by(PaperTrade.created_at.desc()).limit(100)).all() if ids else []
        out["trades"] = [_trade_out(t) for t in trades]
    return out


def _trade_out(t: PaperTrade) -> dict:
    return {"id": t.id, "bot_id": t.bot_id, "symbol": t.symbol, "side": t.side, "quantity": t.quantity, "price": t.price,
            "commission": t.commission, "realized_pnl": t.realized_pnl, "reason": t.reason, "price_source": t.price_source,
            "at": t.created_at.isoformat() if t.created_at else None}


@router.get("/paper/accounts")
def accounts(user: User = Depends(pro), db: Session = Depends(get_db)):
    return [_acct_out(db, a) for a in db.scalars(select(PaperAccount).where(PaperAccount.user_id == user.id).order_by(PaperAccount.id))]


@router.post("/paper/accounts")
def create_account(body: AccountIn, user: User = Depends(pro), db: Session = Depends(get_db)):
    if (db.scalar(select(func.count()).select_from(PaperAccount).where(PaperAccount.user_id == user.id)) or 0) >= MAX_ACCOUNTS:
        raise HTTPException(400, f"Up to {MAX_ACCOUNTS} paper accounts")
    a = PaperAccount(user_id=user.id, name=body.name.strip(), starting_cash=body.starting_cash, cash=body.starting_cash)
    db.add(a)
    db.commit()
    return _acct_out(db, a)


@router.get("/paper/accounts/{aid}")
def account(aid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    return _acct_out(db, _own_acct(db, aid, user), detail=True)


@router.delete("/paper/accounts/{aid}")
def delete_account(aid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    a = _own_acct(db, aid, user)
    db.delete(a)
    db.commit()
    return {"ok": True}


# ── bots ─────────────────────────────────────────────────────────────────────────────────────────
def _bot_summary(db: Session, b: Bot) -> dict:
    eq = sum(paper.sleeve_equity(s) for s in b.sleeves)
    cap = sum(s.capital for s in b.sleeves)
    return {"id": b.id, "name": b.name, "mode": b.mode, "strategy": b.strategy, "symbols": b.symbols, "status": b.status,
            "capital": cap, "equity": eq, "return": eq / cap - 1 if cap else None, "accounts": len(b.sleeves),
            "positions": sum(len(s.positions) for s in b.sleeves),
            "backtest_cagr": ((b.backtest or {}).get("stats") or {}).get("cagr"),
            "created_at": b.created_at.isoformat() if b.created_at else None}


@router.get("/bots")
def bots(user: User = Depends(pro), db: Session = Depends(get_db)):
    return [_bot_summary(db, b) for b in db.scalars(select(Bot).where(Bot.user_id == user.id).order_by(Bot.id))]


@router.get("/bots/strategies")
def strategy_list():
    return {"strategies": [c.schema() for c in REGISTRY.values() if c.KEY != "buy_hold"] + [REGISTRY["buy_hold"].schema()],
            "metrics": tearsheet.schema()}


@router.post("/bots")
def create_bot(body: BotIn, user: User = Depends(pro), db: Session = Depends(get_db)):
    if (db.scalar(select(func.count()).select_from(Bot).where(Bot.user_id == user.id)) or 0) >= MAX_BOTS:
        raise HTTPException(400, f"Up to {MAX_BOTS} bots")
    syms = _syms(body.symbols)
    if body.mode == "strategy":
        if body.strategy not in REGISTRY:
            raise HTTPException(422, "Choose a strategy")
        if not syms:
            raise HTTPException(422, "Add at least one symbol")
    if not body.accounts:
        raise HTTPException(422, "Fund the bot from at least one paper account")
    params = REGISTRY[body.strategy](**body.params).params if body.mode == "strategy" else {}
    b = Bot(user_id=user.id, name=body.name.strip(), description=body.description, mode=body.mode,
            strategy=body.strategy if body.mode == "strategy" else None, params=params, symbols=syms,
            max_position_pct=body.max_position_pct, stop_loss_pct=body.stop_loss_pct, take_profit_pct=body.take_profit_pct,
            daily_auto_close=body.daily_auto_close, webhook_token=paper.new_token())
    db.add(b)
    db.flush()
    try:
        for f in body.accounts:
            paper.fund_sleeve(db, b, _own_acct(db, f.account_id, user), f.capital)
    except paper.PaperError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    if b.mode == "strategy":
        b.backtest = paper.backtest(b.strategy, b.params, syms, b.max_position_pct) or None
    paper.log_signal(db, b, "manual", "created", None, "executed", f"funded {len(body.accounts)} account(s)")
    db.commit()
    return bot_detail(b.id, user, db)


@router.get("/bots/{bid}")
def bot_detail(bid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    trades = db.scalars(select(PaperTrade).where(PaperTrade.bot_id == b.id).order_by(PaperTrade.created_at.desc()).limit(200)).all()
    signals = db.scalars(select(BotSignal).where(BotSignal.bot_id == b.id).order_by(BotSignal.created_at.desc()).limit(100)).all()
    prices: dict[str, float] = {}
    positions = []
    for s in b.sleeves:
        for p in s.positions:
            if p.symbol not in prices:
                try:
                    prices[p.symbol] = paper.price(p.symbol)[0]
                except Exception:  # noqa: BLE001
                    prices[p.symbol] = p.avg_cost
            px = prices[p.symbol]
            positions.append({"account_id": s.account_id, "symbol": p.symbol, "quantity": p.quantity, "avg_cost": p.avg_cost, "price": px,
                              "value": p.quantity * px, "unrealized": (px - p.avg_cost) * p.quantity, "return": px / p.avg_cost - 1,
                              "opened_at": p.opened_at.isoformat() if p.opened_at else None})
    accts = {a.id: a.name for a in db.scalars(select(PaperAccount).where(PaperAccount.id.in_([s.account_id for s in b.sleeves])))} if b.sleeves else {}
    dates, eq = paper.live_curve(db, b)
    cur = sum(paper.sleeve_equity(s, prices) for s in b.sleeves)
    today = paper.now_et().date().isoformat()
    if not dates or dates[-1] != today:  # include today's mark-to-market point
        dates, eq = [*dates, today], [*eq, cur]
    cap = sum(s.capital for s in b.sleeves)
    if dates and len(dates) == 1:
        dates, eq = [b.created_at.date().isoformat() if b.created_at else today, *dates], [cap, *eq]
    closed = [t.realized_pnl for t in reversed(trades) if t.realized_pnl is not None]
    live = tearsheet.compute(dates, eq, closed)
    bt = (b.backtest or {}).get("stats") or {}
    return {**_bot_summary(db, b), "description": b.description, "params": b.params, "max_position_pct": b.max_position_pct,
            "stop_loss_pct": b.stop_loss_pct, "take_profit_pct": b.take_profit_pct, "daily_auto_close": b.daily_auto_close,
            "webhook_path": f"/api/bots/hook/{b.webhook_token}", "last_eval_on": b.last_eval_on,
            "strategy_schema": REGISTRY[b.strategy].schema() if b.strategy in REGISTRY else None,
            "sleeves": [{"account_id": s.account_id, "account": accts.get(s.account_id), "capital": s.capital, "cash": s.cash,
                         "equity": paper.sleeve_equity(s, prices)} for s in b.sleeves],
            "positions": positions, "trades": [_trade_out(t) for t in trades],
            "signals": [{"id": x.id, "source": x.source, "action": x.action, "symbol": x.symbol, "status": x.status, "detail": x.detail,
                         "at": x.created_at.isoformat() if x.created_at else None} for x in signals],
            "live": {"stats": live, "series": {"dates": dates, "equity": eq}, "days": len(dates)},
            "backtest": b.backtest, "comparison": tearsheet.compare(bt, live) if bt else [],
            "market_open": paper.market_open()}


@router.patch("/bots/{bid}")
def patch_bot(bid: int, body: BotPatch, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    data = body.model_dump(exclude_none=True)
    for k in ("stop_loss_pct", "take_profit_pct"):
        if k in data and data[k] == 0:
            data[k] = None
            setattr(b, k, None)
            data.pop(k)
    if "params" in data and b.strategy in REGISTRY:
        b.params = REGISTRY[b.strategy](**data.pop("params")).params
        b.backtest = paper.backtest(b.strategy, b.params, b.symbols, b.max_position_pct) or None
    for k, v in data.items():
        setattr(b, k, v)
    paper.log_signal(db, b, "manual", "settings", None, "executed", ", ".join(f"{k}={v}" for k, v in body.model_dump(exclude_none=True).items())[:400])
    db.commit()
    return bot_detail(bid, user, db)


@router.post("/bots/{bid}/run")
def run_now(bid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    if b.mode != "strategy":
        raise HTTPException(400, "Webhook bots trade on signals; send one to the bot's URL")
    out = paper.evaluate(db, b, source="manual")
    paper.risk_checks(db, b)
    db.commit()
    return {"result": out, "bot": bot_detail(bid, user, db)}


@router.post("/bots/{bid}/close")
def close_positions(bid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    n = paper.close_all(db, b, "manual")
    paper.log_signal(db, b, "manual", "close_all", None, "executed", f"{n} position(s) closed")
    db.commit()
    return bot_detail(bid, user, db)


@router.post("/bots/{bid}/accounts")
def add_account(bid: int, body: Funding, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    if any(s.account_id == body.account_id for s in b.sleeves):
        raise HTTPException(409, "This bot already trades that account")
    try:
        paper.fund_sleeve(db, b, _own_acct(db, body.account_id, user), body.capital)
    except paper.PaperError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return bot_detail(bid, user, db)


@router.delete("/bots/{bid}/accounts/{aid}")
def remove_account(bid: int, aid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    sl = next((s for s in b.sleeves if s.account_id == aid), None)
    if not sl:
        raise HTTPException(404, "Not connected")
    paper.release_sleeve(db, sl)
    b.sleeves.remove(sl)
    db.commit()
    return bot_detail(bid, user, db)


@router.post("/bots/{bid}/webhook/rotate")
def rotate(bid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    b.webhook_token = paper.new_token()
    db.commit()
    return {"webhook_path": f"/api/bots/hook/{b.webhook_token}"}


@router.delete("/bots/{bid}")
def delete_bot(bid: int, user: User = Depends(pro), db: Session = Depends(get_db)):
    b = _own_bot(db, bid, user)
    returned = sum(paper.release_sleeve(db, s) for s in list(b.sleeves))
    db.delete(b)
    db.commit()
    return {"ok": True, "returned_to_accounts": returned}


@router.post("/bots/hook/{token}")
def webhook(token: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """Public signal endpoint (the token is the secret). Accepts TradingView alert JSON."""
    b = db.scalar(select(Bot).where(Bot.webhook_token == token))
    if not b or len(token) < 20:
        raise HTTPException(404, "Unknown webhook")
    owner = db.get(User, b.user_id)
    if not owner or PLAN_ORDER.get(owner.plan, 0) < PLAN_ORDER["pro"]:  # the plan may have lapsed since setup
        raise HTTPException(402, "The bot owner's plan doesn't include AlgoTrader")
    try:
        res = paper.handle_webhook(db, b, {k: v for k, v in list(payload.items())[:20]})
    except paper.PaperError as e:
        db.commit()
        raise HTTPException(422, str(e))
    db.commit()
    return res


# ── plain English → strategy ─────────────────────────────────────────────────────────────────────
DRAFT_SYSTEM = (
    "You turn a trader's plain-English idea into a configuration for a fixed library of long-only daily strategies. "
    "Pick the single closest strategy from the catalogue, set its parameters within their ranges, choose up to 10 "
    "liquid US tickers if the user named a universe or tickers (otherwise leave symbols empty), and set risk controls only "
    "if the user mentioned them (fractions: 0.08 = 8%). Explain in two sentences what the bot will do and note any part of "
    "the idea the catalogue cannot express. Do not give investment advice or promise returns.")


def _rules_draft(prompt: str) -> dict[str, Any]:
    p = prompt.lower()
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)(?!\s*%|\d|\.)", p)]  # percentages are risk controls, not parameters
    syms = [s for s in re.findall(r"\b[A-Z]{1,5}\b", prompt) if s not in {"I", "A", "SMA", "EMA", "RSI", "MACD", "AND", "OR", "THE", "ETF"}][:10]
    if "rsi" in p or "oversold" in p:
        key = "rsi_reversion"
    elif "bollinger" in p or "band" in p:
        key = "bollinger_reversion"
    elif "macd" in p:
        key = "macd_cross"
    elif "breakout" in p or "donchian" in p or "new high" in p:
        key = "donchian_breakout"
    elif "ema" in p or "exponential" in p:
        key = "ema_cross"
    elif "hold" in p and "cross" not in p:
        key = "buy_hold"
    else:
        key = "sma_cross"
    cls = REGISTRY[key]
    params = {}
    ints = [int(n) for n in nums if n >= 2 and n == int(n)]
    for prm, n in zip(cls.PARAMS, sorted(ints)[: len(cls.PARAMS)] if key in ("sma_cross", "ema_cross") else ints):
        params[prm.key] = prm.clamp(n)
    sl = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:trailing\s+)?stop", p) or re.search(r"stop[- ]?loss(?:\s+(?:of|at))?\s*(\d+(?:\.\d+)?)\s*%", p)
    tp = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:take[- ]?profit|profit target|target)", p) or re.search(r"(?:take[- ]?profit|profit target|target)(?:\s+(?:of|at))?\s*(\d+(?:\.\d+)?)\s*%", p)
    return {"strategy": key, "params": cls(**params).params, "symbols": syms,
            "stop_loss_pct": float(sl.group(1)) / 100 if sl else None, "take_profit_pct": float(tp.group(1)) / 100 if tp else None,
            "daily_auto_close": "day trade" in p or "intraday" in p or "close every day" in p or "end of day" in p,
            "explanation": f"Matched your idea to {cls.TITLE} by keyword. Review the parameters before starting.", "engine": "rules"}


@router.post("/bots/draft")
def draft(body: DraftIn, user: User = Depends(pro)):
    from valuebot.config import settings as vb

    if not vb.llm_enabled:
        return _rules_draft(body.prompt)
    catalogue = [{"key": c.KEY, "title": c.TITLE, "description": c.DESCRIPTION, "params": [p.__dict__ for p in c.PARAMS]} for c in REGISTRY.values()]
    schema = {"type": "object", "properties": {
        "strategy": {"type": "string", "enum": list(REGISTRY)}, "params": {"type": "object", "additionalProperties": {"type": "number"}},
        "symbols": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "stop_loss_pct": {"type": ["number", "null"]}, "take_profit_pct": {"type": ["number", "null"]},
        "daily_auto_close": {"type": "boolean"}, "name": {"type": "string"}, "explanation": {"type": "string"}},
        "required": ["strategy", "params", "symbols", "explanation"]}
    try:
        import anthropic

        resp = anthropic.Anthropic(api_key=vb.anthropic_api_key).messages.create(
            model=vb.fast_model, max_tokens=800, system=DRAFT_SYSTEM,
            messages=[{"role": "user", "content": f"Catalogue: {json.dumps(catalogue)}\n\nIdea: {body.prompt}"}],
            tools=[{"name": "configure_bot", "description": "Return the bot configuration.", "input_schema": schema}],
            tool_choice={"type": "tool", "name": "configure_bot"})
        out = next(dict(b.input) for b in resp.content if b.type == "tool_use")
        cls = REGISTRY.get(out.get("strategy")) or REGISTRY["sma_cross"]
        syms = [s.upper() for s in out.get("symbols") or [] if SYM.match(str(s).upper())][:10]
        clamp = lambda v, hi: (min(max(float(v), 0.005), hi) if v else None)  # noqa: E731
        return {"strategy": cls.KEY, "params": cls(**(out.get("params") or {})).params, "symbols": syms,
                "stop_loss_pct": clamp(out.get("stop_loss_pct"), 0.9), "take_profit_pct": clamp(out.get("take_profit_pct"), 10),
                "daily_auto_close": bool(out.get("daily_auto_close")), "name": (out.get("name") or "")[:80] or None,
                "explanation": out.get("explanation", ""), "engine": "claude"}
    except Exception as e:  # noqa: BLE001
        log.warning("draft failed, using rules: %s", e)
        return _rules_draft(body.prompt)
