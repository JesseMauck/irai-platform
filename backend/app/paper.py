"""Paper trading engine for IRAI AlgoTrader bots.

Bots trade simulated money only. Each bot owns a sleeve of capital in every paper account it feeds; orders
fill at the latest market price plus slippage and commission. Strategy bots evaluate their Strategy Lab rule
on daily closes (near the close, or at the open for bots that close out daily); webhook bots act on signals
sent to their private URL (TradingView-style alerts). Per-bot risk controls (position cap, stop-loss,
take-profit, daily auto-close) are enforced on every pass. Nothing here can reach a real broker.
"""
from __future__ import annotations

import datetime as dt
import logging
import secrets
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .algo import emulator
from .algo import tearsheet
from .algo.strategies import REGISTRY, Candle
from .market import service
from .models import Bot, BotSignal, BotSleeve, PaperAccount, PaperPosition, PaperTrade, SleeveEquity

log = logging.getLogger("irai.paper")
ET = ZoneInfo("America/New_York")
COMMISSION_BPS = 1.0
SLIPPAGE_BPS = 2.0
REBALANCE_BAND = 0.05  # don't trade if the position is within 5% of its target value
MAX_ACCOUNT_CASH = 10_000_000


class PaperError(ValueError):
    pass


def now_et() -> dt.datetime:
    return dt.datetime.now(ET)


def market_open(t: dt.datetime | None = None) -> bool:
    """US regular session, Mon-Fri 09:30-16:00 ET (exchange holidays are not modelled)."""
    t = (t or now_et()).astimezone(ET)
    return t.weekday() < 5 and dt.time(9, 30) <= t.time() < dt.time(16, 0)


def new_token() -> str:
    return secrets.token_urlsafe(24)


# ── prices and fills ─────────────────────────────────────────────────────────────────────────────
def price(symbol: str) -> tuple[float, str]:
    q = service.quote(symbol)
    if not q.get("price"):
        raise PaperError(f"No price for {symbol}")
    return float(q["price"]), q.get("source") or "LIVE"


def sleeve_equity(sl: BotSleeve, prices: dict[str, float] | None = None) -> float:
    total = sl.cash
    for p in sl.positions:
        px = (prices or {}).get(p.symbol)
        if px is None:
            try:
                px = price(p.symbol)[0]
            except Exception:  # noqa: BLE001
                px = p.avg_cost
        total += p.quantity * px
    return total


def _position(sl: BotSleeve, symbol: str) -> PaperPosition | None:
    return next((p for p in sl.positions if p.symbol == symbol), None)


def trade(db: Session, sl: BotSleeve, symbol: str, quantity: float, reason: str, px: float | None = None, src: str | None = None) -> PaperTrade | None:
    """Signed quantity: + buys, - sells. Long-only: sells are capped at the shares held; buys at the cash available."""
    if abs(quantity) < 1e-9:
        return None
    if px is None:
        px, src = price(symbol)
    pos = _position(sl, symbol)
    if quantity > 0:
        fill = px * (1 + SLIPPAGE_BPS / 1e4)
        affordable = sl.cash / (fill * (1 + COMMISSION_BPS / 1e4))
        quantity = min(quantity, affordable)
        if quantity * fill < 1:  # less than $1: nothing to do
            return None
        commission = quantity * fill * COMMISSION_BPS / 1e4
        sl.cash -= quantity * fill + commission
        if pos:
            pos.avg_cost = (pos.avg_cost * pos.quantity + fill * quantity) / (pos.quantity + quantity)
            pos.quantity += quantity
        else:
            sl.positions.append(PaperPosition(symbol=symbol, quantity=quantity, avg_cost=fill))
        t = PaperTrade(sleeve_id=sl.id, bot_id=sl.bot_id, symbol=symbol, side="buy", quantity=quantity, price=fill,
                       commission=commission, reason=reason, price_source=src)
    else:
        if not pos:
            return None
        qty = min(-quantity, pos.quantity)
        fill = px * (1 - SLIPPAGE_BPS / 1e4)
        commission = qty * fill * COMMISSION_BPS / 1e4
        sl.cash += qty * fill - commission
        pnl = (fill - pos.avg_cost) * qty - commission
        pos.quantity -= qty
        if pos.quantity <= 1e-9:
            sl.positions.remove(pos)
        t = PaperTrade(sleeve_id=sl.id, bot_id=sl.bot_id, symbol=symbol, side="sell", quantity=qty, price=fill,
                       commission=commission, realized_pnl=pnl, reason=reason, price_source=src)
    db.add(t)
    return t


def target_value(db: Session, sl: BotSleeve, symbol: str, value: float, reason: str) -> PaperTrade | None:
    px, src = price(symbol)
    pos = _position(sl, symbol)
    cur = (pos.quantity * px) if pos else 0.0
    if value <= 0:
        return trade(db, sl, symbol, -pos.quantity, reason, px, src) if pos else None
    if cur and abs(value - cur) <= REBALANCE_BAND * value:
        return None
    return trade(db, sl, symbol, (value - cur) / px, reason, px, src)


def log_signal(db: Session, bot: Bot, source: str, action: str, symbol: str | None, status: str, detail: str | None = None,
               payload: dict | None = None) -> BotSignal:
    s = BotSignal(bot_id=bot.id, source=source, action=action, symbol=symbol, status=status, detail=(detail or "")[:500] or None, payload=payload)
    db.add(s)
    return s


# ── strategy evaluation ──────────────────────────────────────────────────────────────────────────
def desired_exposure(bot: Bot, symbol: str) -> tuple[float, dict[str, Any]]:
    """Run the bot's Strategy Lab rule over two years of daily closes (today's latest price as the last bar)."""
    cls = REGISTRY.get(bot.strategy or "")
    if not cls:
        raise PaperError(f"Unknown strategy {bot.strategy}")
    c = service.chart(symbol, "2y")
    hist = [Candle(h["date"], h["close"]) for h in c["history"] if h.get("close")]
    q = c["quote"]
    today = now_et().date().isoformat()
    if q.get("price") and hist and hist[-1].date < today:
        hist.append(Candle(today, float(q["price"])))
    elif q.get("price") and hist:
        hist[-1] = Candle(hist[-1].date, float(q["price"]))
    s = cls(allow_short=False, **(bot.params or {}))
    for cd in hist:
        s.position += sum(s.pending)  # orders fill before the next bar, as in the emulator
        s.pending = []
        s.on_candle(cd)
    return max(0.0, min(1.0, s.position + sum(s.pending))), {k: v for k, v in s.indicators.items() if v is not None}


def per_symbol_budget(bot: Bot, equity: float) -> float:
    n = max(1, len(bot.symbols))
    return equity * min(1.0 / n, bot.max_position_pct or 1.0)


def _stopped_today(db: Session, sl: BotSleeve, symbol: str) -> bool:
    start = now_et().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc)
    return db.scalar(select(PaperTrade.id).where(PaperTrade.sleeve_id == sl.id, PaperTrade.symbol == symbol,
                                                 PaperTrade.reason.in_(("stop_loss", "take_profit")), PaperTrade.created_at >= start)) is not None


def evaluate(db: Session, bot: Bot, source: str = "schedule") -> dict[str, Any]:
    """Move every sleeve to the strategy's target exposure for each symbol."""
    out: dict[str, Any] = {}
    for sym in bot.symbols:
        try:
            exp, ind = desired_exposure(bot, sym)
        except Exception as e:  # noqa: BLE001
            log_signal(db, bot, source, "evaluate", sym, "error", str(e))
            out[sym] = {"error": str(e)}
            continue
        fills = 0
        for sl in bot.sleeves:
            if exp > 0 and _stopped_today(db, sl, sym):
                continue  # don't re-enter on the same day a risk control closed the position
            if target_value(db, sl, sym, exp * per_symbol_budget(bot, sleeve_equity(sl)), "signal"):
                fills += 1
        log_signal(db, bot, source, "long" if exp > 0 else "flat", sym, "executed" if fills else "ignored",
                   f"target exposure {exp:.0%}; {fills} fill(s)" + (f"; {', '.join(f'{k} {v:.2f}' for k, v in list(ind.items())[:3])}" if ind else ""))
        out[sym] = {"exposure": exp, "fills": fills}
    bot.last_eval_on = now_et().date().isoformat()
    return out


def risk_checks(db: Session, bot: Bot) -> int:
    """Stop-loss and take-profit against each position's average cost."""
    n = 0
    if not (bot.stop_loss_pct or bot.take_profit_pct):
        return 0
    for sl in bot.sleeves:
        for pos in list(sl.positions):
            try:
                px, src = price(pos.symbol)
            except Exception:  # noqa: BLE001
                continue
            r = px / pos.avg_cost - 1
            reason = ("stop_loss" if bot.stop_loss_pct and r <= -bot.stop_loss_pct else
                      "take_profit" if bot.take_profit_pct and r >= bot.take_profit_pct else None)
            if reason:
                trade(db, sl, pos.symbol, -pos.quantity, reason, px, src)
                log_signal(db, bot, "risk", reason, pos.symbol, "executed", f"{r:+.1%} vs average cost")
                n += 1
    bot.last_risk_at = dt.datetime.now(dt.timezone.utc)
    return n


def close_all(db: Session, bot: Bot, reason: str) -> int:
    n = 0
    for sl in bot.sleeves:
        for pos in list(sl.positions):
            try:
                trade(db, sl, pos.symbol, -pos.quantity, reason)
                n += 1
            except PaperError as e:
                log_signal(db, bot, "risk", reason, pos.symbol, "error", str(e))
    return n


# ── webhook signals ──────────────────────────────────────────────────────────────────────────────
ACTIONS = {"buy": "buy", "long": "buy", "enter": "buy", "sell": "sell", "exit": "sell", "close": "sell", "flat": "sell"}


def handle_webhook(db: Session, bot: Bot, payload: dict[str, Any]) -> dict[str, Any]:
    """TradingView/TradersPost-style JSON: {"ticker": "AAPL", "action": "buy"|"sell"|"exit", "quantity"?: shares,
    "percent"?: 0-100 of the sleeve}. Applied to every account the bot feeds."""
    sym = str(payload.get("ticker") or payload.get("symbol") or "").upper().strip()
    act = ACTIONS.get(str(payload.get("action") or payload.get("sentiment") or "").lower().strip())
    if not sym or not act:
        log_signal(db, bot, "webhook", str(payload.get("action"))[:12], sym or None, "error", "Need ticker and action (buy, sell or exit)", payload)
        raise PaperError("Need ticker and action (buy, sell or exit)")
    if bot.status != "running":
        log_signal(db, bot, "webhook", act, sym, "ignored", "Bot is paused", payload)
        return {"status": "ignored", "reason": "paused"}
    if bot.symbols and sym not in bot.symbols:
        log_signal(db, bot, "webhook", act, sym, "ignored", f"{sym} is not in this bot's symbols", payload)
        return {"status": "ignored", "reason": "symbol not allowed"}
    fills = 0
    for sl in bot.sleeves:
        if act == "sell":
            pos = _position(sl, sym)
            if pos:
                qty = float(payload["quantity"]) if payload.get("quantity") else pos.quantity
                fills += bool(trade(db, sl, sym, -min(qty, pos.quantity), "webhook"))
        else:
            px, src = price(sym)
            eq = sleeve_equity(sl)
            if payload.get("quantity"):
                qty = float(payload["quantity"])
            elif payload.get("percent"):
                qty = eq * min(float(payload["percent"]), 100) / 100 / px
            else:
                qty = per_symbol_budget(bot, eq) / px
            cap_qty = per_symbol_budget(bot, eq) / px - ((_position(sl, sym).quantity) if _position(sl, sym) else 0)
            fills += bool(trade(db, sl, sym, max(0.0, min(qty, cap_qty)), "webhook", px, src))
    detail = f"{fills} fill(s) across {len(bot.sleeves)} account(s)" + ("" if market_open() else "; market closed, filled at the last price")
    log_signal(db, bot, "webhook", act, sym, "executed" if fills else "ignored", detail, payload)
    return {"status": "executed" if fills else "ignored", "fills": fills, "detail": detail}


# ── sleeves, snapshots, backtests ────────────────────────────────────────────────────────────────
def fund_sleeve(db: Session, bot: Bot, acct: PaperAccount, capital: float) -> BotSleeve:
    if capital <= 0 or capital > acct.cash + 1e-6:
        raise PaperError(f"{acct.name} has ${acct.cash:,.0f} unallocated; allocate up to that amount")
    acct.cash -= capital
    sl = BotSleeve(bot=bot, account_id=acct.id, capital=capital, cash=capital)
    db.add(sl)
    return sl


def release_sleeve(db: Session, sl: BotSleeve) -> float:
    """Sell everything in a sleeve and return its cash to the account."""
    for pos in list(sl.positions):
        try:
            trade(db, sl, pos.symbol, -pos.quantity, "close_bot")
        except PaperError:
            sl.cash += pos.quantity * pos.avg_cost  # no price: return at cost rather than lose it
            sl.positions.remove(pos)
    acct = db.get(PaperAccount, sl.account_id)
    if acct:
        acct.cash += sl.cash
    returned, sl.cash = sl.cash, 0.0
    return returned


def snapshot(db: Session, bot: Bot, day: str | None = None) -> None:
    day = day or now_et().date().isoformat()
    for sl in bot.sleeves:
        v = sleeve_equity(sl)
        row = db.scalar(select(SleeveEquity).where(SleeveEquity.sleeve_id == sl.id, SleeveEquity.date == day))
        if row:
            row.equity = v
        else:
            db.add(SleeveEquity(sleeve_id=sl.id, bot_id=bot.id, date=day, equity=v))


def backtest(strategy: str, params: dict, symbols: list[str], max_position_pct: float = 1.0, range_: str = "2y") -> dict[str, Any]:
    """Equal-weight portfolio backtest of the rule across the bot's symbols, with a tear sheet."""
    cls = REGISTRY.get(strategy)
    if not cls or not symbols:
        return {}
    curves, pnls, exposure, closes = [], [], [], []
    weight = min(1.0 / len(symbols), max_position_pct or 1.0)
    for sym in symbols:
        try:
            c = service.chart(sym, range_)
        except Exception:  # noqa: BLE001
            continue
        cands = [Candle(h["date"], h["close"]) for h in c["history"] if h.get("close")]
        if len(cands) < 60:
            continue
        r = emulator.run(cls(allow_short=False, **params), cands, emulator.EmulationSettings(initial_capital=10_000, commission_bps=COMMISSION_BPS, slippage_bps=SLIPPAGE_BPS))
        curves.append({e["date"]: e["equity"] / 10_000 for e in r.equity})
        exposure.append({e["date"]: bool(e["exposure"]) for e in r.equity})
        closes.append({e["date"]: e["close"] for e in r.equity})
        pnls += [x.pnl * weight * 10 for x in r.roundtrips if x.exit_date]  # per $100k of bot capital
    if not curves:
        return {}
    dates = sorted(set.intersection(*[set(cv) for cv in curves]))
    eq = [100_000 * ((1 - weight * len(curves)) + sum(weight * cv[d] for cv in curves)) for d in dates]
    bench = None
    try:
        b = {h["date"]: h["close"] for h in service.chart("SPY", range_)["history"] if h.get("close")}
        if all(d in b for d in dates):
            bench = [b[d] for d in dates]
    except Exception:  # noqa: BLE001
        pass
    exp = [any(ex.get(d) for ex in exposure) for d in dates]
    stats = tearsheet.compute(dates, eq, pnls, bench, exp)
    step = max(1, len(dates) // 300)
    return {"stats": stats, "start": dates[0], "end": dates[-1], "symbols": symbols,
            "series": {"dates": dates[::step], "equity": eq[::step], "bench": [bench[i] / bench[0] * 100_000 for i in range(0, len(dates), step)] if bench else None}}


def live_curve(db: Session, bot: Bot) -> tuple[list[str], list[float]]:
    rows = db.scalars(select(SleeveEquity).where(SleeveEquity.bot_id == bot.id).order_by(SleeveEquity.date)).all()
    by: dict[str, float] = {}
    for r in rows:
        by[r.date] = by.get(r.date, 0.0) + r.equity
    dates = sorted(by)
    return dates, [by[d] for d in dates]


# ── scheduler (called from the worker every tick) ───────────────────────────────────────────────
_snapped: dict[int, str] = {}  # bot id -> day of the last end-of-day snapshot (idempotent upsert anyway)

def run_schedule(db: Session, t: dt.datetime | None = None) -> dict[str, Any]:
    t = (t or now_et()).astimezone(ET)
    today = t.date().isoformat()
    out = {"evaluated": 0, "risk_exits": 0, "auto_closed": 0, "snapshots": 0}
    if t.weekday() >= 5:
        return out
    bots = db.scalars(select(Bot).where(Bot.status == "running")).all()
    for bot in bots:
        try:
            if market_open(t):
                last = bot.last_risk_at.replace(tzinfo=dt.timezone.utc) if bot.last_risk_at and bot.last_risk_at.tzinfo is None else bot.last_risk_at
                if not last or (dt.datetime.now(dt.timezone.utc) - last).total_seconds() >= 300:
                    out["risk_exits"] += risk_checks(db, bot)
                # strategy bots: once a day near the close, or at the open for bots that close out daily
                if bot.mode == "strategy" and bot.last_eval_on != today:
                    due = t.time() >= (dt.time(9, 35) if bot.daily_auto_close else dt.time(15, 45))
                    if due and not (bot.daily_auto_close and t.time() >= dt.time(15, 50)):
                        evaluate(db, bot)
                        out["evaluated"] += 1
                if bot.daily_auto_close and t.time() >= dt.time(15, 55) and bot.last_autoclose_on != today:
                    n = close_all(db, bot, "auto_close")
                    log_signal(db, bot, "risk", "auto_close", None, "executed" if n else "ignored", f"daily auto-close: {n} position(s)")
                    bot.last_autoclose_on = today
                    out["auto_closed"] += n
            if t.time() >= dt.time(16, 5) and _snapped.get(bot.id) != today:
                snapshot(db, bot, today)
                _snapped[bot.id] = today
                out["snapshots"] += 1
            db.commit()
        except Exception:  # noqa: BLE001 (one bot must not stop the others)
            db.rollback()
            log.exception("bot %s failed", bot.id)
    return out
