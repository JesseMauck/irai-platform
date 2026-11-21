"""Market screener: a curated universe of liquid US stocks and ETFs with the metrics traders filter on.

A snapshot is computed from daily OHLCV (price, change, gaps, returns over 1W..1Y and YTD, distance to 20/50/200-day
averages, RSI, ATR %, realised volatility, relative volume, dollar volume, 52-week position, relative strength vs SPY,
beta) merged with fundamentals and fund data (market cap or AUM, P/E, margins, growth, yield, expense ratio, category),
plus IRAI Buzz scores. The worker refreshes it every 30 minutes in US trading hours and hourly otherwise.

Presets are plain filter definitions grouped by theme; the Daily Spotlight ranks presets by how much is happening in
them today. Research and education only: a screen surfaces things to look at, it is not a recommendation.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from .market import service

log = logging.getLogger("irai.screener")
SECTOR_MAP = {"Financial Services": "Financials", "Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples",
              "Basic Materials": "Materials", "Information Technology": "Technology", "Health Care": "Healthcare"}
UNIVERSE: list[dict[str, Any]] = json.loads((Path(__file__).parent / "seed_data" / "screener_universe.json").read_text())
META = {u["symbol"]: u for u in UNIVERSE}

# ── fields ──────────────────────────────────────────────────────────────────────────────────────
# key: (label, group, unit)   unit: pct (fraction), x (multiple), num, usd, int, text
FIELDS: dict[str, tuple[str, str, str]] = {
    "price": ("Price", "Price & performance", "num"), "change_pct": ("Change today", "Price & performance", "pct"), "gap_pct": ("Gap at open", "Price & performance", "pct"),
    "ret_1w": ("1-week return", "Price & performance", "pct"), "ret_1m": ("1-month return", "Price & performance", "pct"), "ret_3m": ("3-month return", "Price & performance", "pct"),
    "ret_6m": ("6-month return", "Price & performance", "pct"), "ret_ytd": ("YTD return", "Price & performance", "pct"), "ret_1y": ("1-year return", "Price & performance", "pct"),
    "rs_3m": ("Relative strength vs SPY (3M)", "Price & performance", "pct"),
    "vs_sma20": ("vs 20-day average", "Technical", "pct"), "vs_sma50": ("vs 50-day average", "Technical", "pct"), "vs_sma200": ("vs 200-day average", "Technical", "pct"),
    "rsi14": ("RSI (14)", "Technical", "num"), "from_high_52w": ("From 52-week high", "Technical", "pct"), "from_low_52w": ("From 52-week low", "Technical", "pct"),
    "range_pos_52w": ("Position in 52-week range", "Technical", "pct"), "golden": ("50-day above 200-day", "Technical", "bool"), "new_high_20d": ("20-day high today", "Technical", "bool"),
    "atr_pct": ("ATR % of price", "Risk", "pct"), "vol_20d": ("20-day volatility (ann.)", "Risk", "pct"), "beta": ("Beta (1Y vs SPY)", "Risk", "num"),
    "max_dd_1y": ("Max drawdown (1Y)", "Risk", "pct"),
    "volume": ("Volume today", "Liquidity", "int"), "avg_volume_20d": ("Avg volume (20 days)", "Liquidity", "int"), "rel_volume": ("Relative volume", "Liquidity", "x"),
    "dollar_volume": ("Avg dollar volume (20 days)", "Liquidity", "usd"),
    "market_cap": ("Market cap", "Fundamental", "usd"), "forward_pe": ("Forward P/E", "Fundamental", "x"), "trailing_pe": ("Trailing P/E", "Fundamental", "x"),
    "ev_ebitda": ("EV/EBITDA", "Fundamental", "x"), "price_to_sales": ("Price/sales", "Fundamental", "x"), "peg_ratio": ("PEG", "Fundamental", "x"),
    "revenue_growth": ("Revenue growth", "Fundamental", "pct"), "earnings_growth": ("Earnings growth", "Fundamental", "pct"), "operating_margin": ("Operating margin", "Fundamental", "pct"),
    "roe": ("Return on equity", "Fundamental", "pct"), "debt_to_equity": ("Debt/equity", "Fundamental", "num"), "short_percent_float": ("Short interest (% float)", "Fundamental", "pct"),
    "dividend_yield": ("Dividend yield", "Income", "pct"),
    "aum": ("Fund assets (AUM)", "Fund", "usd"), "expense_ratio": ("Expense ratio", "Cost", "pct"), "leverage": ("Leverage", "Fund", "num"),
    "buzz": ("Buzz (attention 0-100)", "Sentiment", "num"),
}
TEXT_FIELDS = {"kind", "sector", "category", "region", "theme", "asset_class", "underlying", "symbol", "name"}

# ── presets ─────────────────────────────────────────────────────────────────────────────────────
# filter: (field, op, value)  ops: >=, <=, ==, in, contains, true, false
GROUPS = [("market_mover", "Market movers"), ("sector_rotation", "Sector rotation"), ("trending", "Trending"), ("regional", "Regional"),
          ("fundamental", "Fundamental"), ("technical", "Technical"), ("income", "Income"), ("cost", "Cost"), ("risk", "Risk"),
          ("liquidity_momentum", "Liquidity & momentum")]
P = dict  # readability


def _p(id_, group, title, desc, filters, sort, desc_sort=True, kind=None, limit=50, cols=None):
    return P(id=id_, group=group, title=title, description=desc, filters=filters, sort=sort, desc=desc_sort, kind=kind, limit=limit, columns=cols or [])


PRESETS: list[dict[str, Any]] = [
    _p("top_gainers", "market_mover", "Top gainers", "Biggest percentage gains today among liquid stocks and ETFs.", [("dollar_volume", ">=", 5e6)], "change_pct", cols=["change_pct", "rel_volume", "gap_pct"]),
    _p("top_losers", "market_mover", "Top losers", "Biggest percentage declines today among liquid stocks and ETFs.", [("dollar_volume", ">=", 5e6)], "change_pct", False, cols=["change_pct", "rel_volume", "gap_pct"]),
    _p("most_traded", "market_mover", "Most traded", "Highest dollar volume: where the market's liquidity is concentrated.", [], "dollar_volume", cols=["dollar_volume", "rel_volume", "change_pct"]),
    _p("unusual_volume", "market_mover", "Unusual volume", "Trading at least twice its 20-day average volume today.", [("rel_volume", ">=", 2.0), ("dollar_volume", ">=", 2e6)], "rel_volume", cols=["rel_volume", "change_pct", "atr_pct"]),
    _p("gap_up", "market_mover", "Gap ups", "Opened at least 2% above yesterday's close.", [("gap_pct", ">=", 0.02)], "gap_pct", cols=["gap_pct", "change_pct", "rel_volume"]),
    _p("gap_down", "market_mover", "Gap downs", "Opened at least 2% below yesterday's close.", [("gap_pct", "<=", -0.02)], "gap_pct", False, cols=["gap_pct", "change_pct", "rel_volume"]),
    _p("best_1w", "market_mover", "Best performers (1 week)", "Highest one-week returns.", [("dollar_volume", ">=", 2e6)], "ret_1w", cols=["ret_1w", "ret_1m", "rsi14"]),
    _p("best_ytd", "market_mover", "Year-to-date leaders", "Highest returns since January 1.", [("dollar_volume", ">=", 2e6)], "ret_ytd", cols=["ret_ytd", "ret_1y", "vs_sma200"]),
    _p("largest_aum", "market_mover", "Largest ETFs", "ETFs ranked by assets under management.", [], "aum", kind="etf", cols=["aum", "expense_ratio", "ret_ytd"]),
    _p("inverse_leveraged", "market_mover", "Inverse & leveraged", "Daily-reset funds with -3x to +3x exposure. They are built for one-day moves and decay over time.", [("category", "==", "Leveraged & inverse")], "change_pct", kind="etf", cols=["leverage", "change_pct", "ret_1m", "vol_20d"]),
    *[_p(f"sector_{s.lower().replace(' ', '_')}", "sector_rotation", f"{s}", f"{s} ETFs and stocks, ranked by 3-month momentum.", [("sector", "==", s)], "ret_3m", cols=["ret_3m", "rs_3m", "rel_volume", "vs_sma50"])
      for s in ("Technology", "Energy", "Healthcare", "Financials", "Real Estate", "Industrials", "Consumer Discretionary", "Consumer Staples", "Utilities", "Materials", "Communication Services")],
    _p("sector_leaders", "sector_rotation", "Sector ETF leaderboard", "The 11 sector ETFs ranked by relative strength vs SPY over three months.", [("category", "==", "Sector"), ("symbol", "in", ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLRE", "XLB", "XLC"])], "rs_3m", kind="etf", cols=["rs_3m", "ret_1m", "ret_3m", "vs_sma50"]),
    _p("sector_volume", "sector_rotation", "Sector funds on heavy volume", "Unleveraged sector ETFs trading 1.5x their normal volume: possible rotation flows.", [("category", "==", "Sector"), ("rel_volume", ">=", 1.5)], "rel_volume", kind="etf", cols=["rel_volume", "change_pct", "ret_1w"]),
    _p("buzz_leaders", "trending", "Most talked about", "Highest IRAI Buzz scores: news volume, filings and unusual activity.", [("buzz", ">=", 1)], "buzz", cols=["buzz", "change_pct", "rel_volume"]),
    _p("ai_robotics", "trending", "AI & semiconductors", "Semiconductor, AI and robotics funds and the chip stocks behind them.", [("theme", "in", ["Semiconductors", "AI & robotics"])], "ret_3m", cols=["ret_3m", "change_pct", "vs_sma50"]),
    _p("clean_energy", "trending", "Clean energy & nuclear", "Solar, clean energy and uranium funds.", [("theme", "in", ["Clean energy", "Nuclear"])], "ret_3m", cols=["ret_3m", "change_pct", "vol_20d"]),
    _p("crypto_etfs", "trending", "Crypto ETFs", "Spot bitcoin and ether ETFs and crypto-linked funds.", [("asset_class", "==", "Crypto")], "change_pct", cols=["change_pct", "ret_1m", "aum", "expense_ratio"]),
    _p("defense", "trending", "Defense & aerospace", "Aerospace and defense funds.", [("theme", "==", "Defense")], "ret_3m", cols=["ret_3m", "change_pct"]),
    _p("gold", "trending", "Gold & precious metals", "Physical gold and silver funds and miners.", [("theme", "in", ["Gold", "Silver"])], "ret_1m", cols=["ret_1m", "change_pct", "expense_ratio"]),
    _p("inflation_bonds", "trending", "Inflation-linked bonds", "TIPS funds with costs under 0.5%.", [("theme", "==", "Inflation-linked"), ("expense_ratio", "<=", 0.005)], "ret_3m", kind="etf", cols=["ret_3m", "dividend_yield", "expense_ratio"]),
    *[_p(f"region_{r.lower().replace(' ', '_').replace('-', '_')}", "regional", f"{r} equity", f"Equity funds with {r} exposure.", [("region", "==", r), ("asset_class", "==", "Equity")], "ret_3m", kind="etf", cols=["ret_3m", "change_pct", "expense_ratio"])
      for r in ("United States", "Japan", "United Kingdom", "Europe", "China", "India", "Brazil", "Emerging markets", "Developed ex-US", "South Korea", "Taiwan", "Canada", "Mexico")],
    _p("value_quality", "fundamental", "Quality at a reasonable price", "Forward P/E under 20, operating margin above 20% and return on equity above 15%.", [("forward_pe", "<=", 20), ("forward_pe", ">=", 1), ("operating_margin", ">=", 0.2), ("roe", ">=", 0.15)], "roe", kind="stock", cols=["forward_pe", "operating_margin", "roe", "revenue_growth"]),
    _p("growth", "fundamental", "Fast growers", "Revenue growing more than 20% a year.", [("revenue_growth", ">=", 0.2)], "revenue_growth", kind="stock", cols=["revenue_growth", "earnings_growth", "forward_pe", "operating_margin"]),
    _p("cheap_pe", "fundamental", "Low forward P/E", "Forward P/E between 1 and 12.", [("forward_pe", ">=", 1), ("forward_pe", "<=", 12)], "forward_pe", False, kind="stock", cols=["forward_pe", "ev_ebitda", "dividend_yield"]),
    _p("mega_caps", "fundamental", "Mega caps", "Companies worth more than $200 billion.", [("market_cap", ">=", 2e11)], "market_cap", kind="stock", cols=["market_cap", "forward_pe", "ret_ytd"]),
    _p("high_short", "fundamental", "Most shorted", "Short interest above 5% of float.", [("short_percent_float", ">=", 0.05)], "short_percent_float", kind="stock", cols=["short_percent_float", "change_pct", "rel_volume"]),
    _p("golden_cross", "technical", "Uptrend: 50 above 200-day", "Price above its 200-day average with the 50-day above the 200-day.", [("golden", "true", None), ("vs_sma200", ">=", 0)], "vs_sma200", cols=["vs_sma50", "vs_sma200", "rsi14"]),
    _p("new_highs", "technical", "New 20-day highs", "Closing at a 20-day high today.", [("new_high_20d", "true", None)], "rel_volume", cols=["change_pct", "rel_volume", "from_high_52w"]),
    _p("near_52w_high", "technical", "Near 52-week highs", "Within 3% of the 52-week high.", [("from_high_52w", ">=", -0.03)], "ret_3m", cols=["from_high_52w", "ret_3m", "rsi14"]),
    _p("low_52w", "technical", "At 52-week lows", "Within 3% of the 52-week low.", [("from_low_52w", "<=", 0.03)], "from_low_52w", False, cols=["from_low_52w", "change_pct", "rsi14"]),
    _p("oversold", "technical", "Oversold (RSI under 30)", "14-day RSI below 30: stretched to the downside.", [("rsi14", "<=", 30)], "rsi14", False, cols=["rsi14", "change_pct", "vs_sma50"]),
    _p("overbought", "technical", "Overbought (RSI over 70)", "14-day RSI above 70: stretched to the upside.", [("rsi14", ">=", 70)], "rsi14", cols=["rsi14", "change_pct", "vs_sma50"]),
    _p("pullback_uptrend", "technical", "Pullback in an uptrend", "Above the 200-day but at least 5% below the 20-day average.", [("vs_sma200", ">=", 0.0), ("vs_sma20", "<=", -0.05)], "vs_sma20", False, cols=["vs_sma20", "vs_sma200", "rsi14"]),
    _p("high_yield_div", "income", "High dividend yield", "Yield above 4% among stocks and equity income funds.", [("dividend_yield", ">=", 0.04), ("asset_class", "in", [None, "Equity"])], "dividend_yield", cols=["dividend_yield", "ret_1y", "vol_20d"]),
    _p("dividend_etfs", "income", "Dividend & covered-call ETFs", "Equity income funds, by yield.", [("category", "==", "Dividend & income")], "dividend_yield", kind="etf", cols=["dividend_yield", "expense_ratio", "ret_1y"]),
    _p("bond_income", "income", "Bond income", "Bond funds yielding more than 3%.", [("asset_class", "==", "Fixed income"), ("dividend_yield", ">=", 0.03)], "dividend_yield", kind="etf", cols=["dividend_yield", "expense_ratio", "ret_3m"]),
    _p("cash_like", "income", "Cash-like T-bill funds", "Ultra-short Treasury funds.", [("theme", "==", "T-bills")], "dividend_yield", kind="etf", cols=["dividend_yield", "expense_ratio", "aum"]),
    _p("lowest_cost", "cost", "Lowest-cost ETFs", "Expense ratios of 0.10% or less.", [("expense_ratio", "<=", 0.001), ("expense_ratio", ">=", 0)], "aum", kind="etf", cols=["expense_ratio", "aum", "ret_1y"]),
    _p("cheap_sector", "cost", "Low-cost sector funds", "Sector ETFs costing 0.15% or less.", [("category", "==", "Sector"), ("expense_ratio", "<=", 0.0015)], "ret_3m", kind="etf", cols=["expense_ratio", "ret_3m", "aum"]),
    _p("expensive", "cost", "Most expensive ETFs", "Highest expense ratios: check what you're paying for.", [("expense_ratio", ">=", 0.0075)], "expense_ratio", kind="etf", cols=["expense_ratio", "category", "ret_1y"]),
    _p("low_beta", "risk", "Low-beta equities", "Beta under 0.8 and 20-day volatility under 20%.", [("beta", "<=", 0.8), ("beta", ">=", 0), ("vol_20d", "<=", 0.2), ("asset_class", "in", [None, "Equity"])], "beta", False, cols=["beta", "vol_20d", "ret_1y"]),
    _p("high_vol", "risk", "Most volatile", "Highest 20-day realised volatility.", [("dollar_volume", ">=", 2e6)], "vol_20d", cols=["vol_20d", "atr_pct", "change_pct"]),
    _p("deep_drawdown", "risk", "Deep drawdowns", "At least 30% below the 52-week high.", [("from_high_52w", "<=", -0.3)], "from_high_52w", False, cols=["from_high_52w", "max_dd_1y", "rsi14"]),
    _p("defensive", "risk", "Defensive sectors", "Utilities, staples and healthcare with beta under 0.9.", [("sector", "in", ["Utilities", "Consumer Staples", "Healthcare"]), ("beta", "<=", 0.9)], "ret_3m", cols=["beta", "ret_3m", "dividend_yield"]),
    _p("momentum_liquid", "liquidity_momentum", "Liquid momentum", "Up 10%+ over three months, above the 50-day, $20M+ a day traded.", [("ret_3m", ">=", 0.1), ("vs_sma50", ">=", 0), ("dollar_volume", ">=", 2e7)], "ret_3m", cols=["ret_3m", "rs_3m", "dollar_volume"]),
    _p("rs_leaders", "liquidity_momentum", "Relative-strength leaders", "Beating SPY by 10% or more over three months.", [("rs_3m", ">=", 0.1)], "rs_3m", cols=["rs_3m", "ret_3m", "vs_sma50"]),
    _p("breakout_volume", "liquidity_momentum", "Breakouts on volume", "20-day high today on 1.5x normal volume.", [("new_high_20d", "true", None), ("rel_volume", ">=", 1.5)], "rel_volume", cols=["rel_volume", "change_pct", "ret_1m"]),
    _p("quarterly_momentum_etf", "liquidity_momentum", "Quarterly momentum ETFs", "Unleveraged ETFs up 3% to 35% over three months with 50,000+ shares a day.", [("ret_3m", ">=", 0.03), ("ret_3m", "<=", 0.35), ("avg_volume_20d", ">=", 5e4), ("leverage", "==", None)], "ret_3m", kind="etf", cols=["ret_3m", "avg_volume_20d", "expense_ratio"]),
    _p("weak_momentum", "liquidity_momentum", "Weakest momentum", "Worst three-month returns among liquid names.", [("dollar_volume", ">=", 1e7)], "ret_3m", False, cols=["ret_3m", "rs_3m", "vs_sma200"]),
]
BY_ID = {p["id"]: p for p in PRESETS}
SPOTLIGHT = ["top_gainers", "top_losers", "most_traded", "unusual_volume", "inverse_leveraged", "sector_energy", "sector_healthcare", "sector_real_estate",
             "sector_technology", "low_beta", "low_52w", "oversold", "breakout_volume", "gold", "crypto_etfs", "buzz_leaders"]


# ── snapshot ────────────────────────────────────────────────────────────────────────────────────
_snap: dict[str, Any] = {"rows": [], "at": None, "source": None}
_info: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _f(x) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _sma(x: np.ndarray, n: int) -> float | None:
    return float(x[-n:].mean()) if len(x) >= n else None


def _rsi(c: np.ndarray, n: int = 14) -> float | None:
    if len(c) <= n + 1:
        return None
    d = np.diff(c[-(n * 6):])
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ag, al = up[:n].mean(), dn[:n].mean()
    for i in range(n, len(d)):
        ag, al = (ag * (n - 1) + up[i]) / n, (al * (n - 1) + dn[i]) / n
    return 100.0 if al == 0 else float(100 - 100 / (1 + ag / al))


def metrics(sym: str, bars: list[dict[str, Any]], spy: dict[str, float] | None) -> dict[str, Any]:
    o = np.array([b["o"] for b in bars], float)
    h = np.array([b["h"] for b in bars], float)
    lo = np.array([b["l"] for b in bars], float)
    c = np.array([b["c"] for b in bars], float)
    v = np.array([b.get("v") or 0 for b in bars], float)
    dates = [b["t"][:10] for b in bars]
    n = len(c)
    r = lambda k: float(c[-1] / c[-1 - k] - 1) if n > k else None  # noqa: E731
    ytd = next((c[i - 1] for i in range(n - 1, 0, -1) if dates[i][:4] == dates[-1][:4] and dates[i - 1][:4] != dates[-1][:4]), None)
    lr = np.diff(np.log(c[-253:]))
    tr = np.maximum.reduce([h[1:] - lo[1:], np.abs(h[1:] - c[:-1]), np.abs(lo[1:] - c[:-1])])
    hi52, lo52 = float(h[-252:].max()), float(lo[-252:].min())
    s20, s50, s200 = _sma(c, 20), _sma(c, 50), _sma(c, 200)
    peak = np.maximum.accumulate(c[-252:])
    avg20 = float(v[-21:-1].mean()) if n > 21 else float(v.mean())
    out = {"price": float(c[-1]), "prev_close": float(c[-2]) if n > 1 else None, "change_pct": r(1), "gap_pct": float(o[-1] / c[-2] - 1) if n > 1 else None,
           "ret_1w": r(5), "ret_1m": r(21), "ret_3m": r(63), "ret_6m": r(126), "ret_1y": r(252), "ret_ytd": float(c[-1] / ytd - 1) if ytd else None,
           "vs_sma20": c[-1] / s20 - 1 if s20 else None, "vs_sma50": c[-1] / s50 - 1 if s50 else None, "vs_sma200": c[-1] / s200 - 1 if s200 else None,
           "golden": bool(s50 and s200 and s50 > s200), "new_high_20d": bool(n > 21 and c[-1] >= h[-21:-1].max()),
           "rsi14": _rsi(c), "from_high_52w": float(c[-1] / hi52 - 1), "from_low_52w": float(c[-1] / lo52 - 1),
           "range_pos_52w": float((c[-1] - lo52) / (hi52 - lo52)) if hi52 > lo52 else None,
           "atr_pct": float(tr[-14:].mean() / c[-1]) if len(tr) >= 14 else None, "vol_20d": float(np.std(lr[-20:], ddof=1) * math.sqrt(252)) if len(lr) > 20 else None,
           "max_dd_1y": float((c[-252:] / peak - 1).min()), "volume": float(v[-1]), "avg_volume_20d": avg20,
           "rel_volume": float(v[-1] / avg20) if avg20 else None, "dollar_volume": float((v[-20:] * c[-20:]).mean()), "as_of": dates[-1],
           "spark": [round(float(x), 4) for x in c[-60:][::2]]}
    if spy and sym != "SPY":
        ds = [d for d in dates[-253:] if d in spy]
        if len(ds) > 64:
            me = dict(zip(dates, c))
            a, b = np.array([me[d] for d in ds]), np.array([spy[d] for d in ds])
            out["rs_3m"] = float((a[-1] / a[-64]) / (b[-1] / b[-64]) - 1)
            ra, rb = np.diff(np.log(a)), np.diff(np.log(b))
            out["beta_calc"] = float(np.cov(ra, rb)[0, 1] / np.var(rb, ddof=1)) if np.var(rb) > 0 else None
    elif sym == "SPY":
        out["rs_3m"], out["beta_calc"] = 0.0, 1.0
    return out


def _info_for(sym: str) -> dict[str, Any]:
    hit = _info.get(sym)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    try:
        i = service.info(sym) or {}
    except Exception:  # noqa: BLE001
        i = hit[1] if hit else {}
    _info[sym] = (time.time(), i)
    return i


def _buzz() -> dict[str, float]:
    try:
        from sqlalchemy import func, select

        from .db import SessionLocal
        from .models import BuzzSnapshot

        with SessionLocal() as db:
            sub = select(BuzzSnapshot.symbol, func.max(BuzzSnapshot.id).label("mid")).group_by(BuzzSnapshot.symbol).subquery()
            rows = db.execute(select(BuzzSnapshot.symbol, BuzzSnapshot.score).join(sub, BuzzSnapshot.id == sub.c.mid)).all()
            return {s: float(sc) for s, sc in rows if sc is not None}
    except Exception:  # noqa: BLE001
        return {}


def build(symbols: list[str] | None = None, with_info: bool = True, live_quotes: bool = True) -> dict[str, Any]:
    t0 = time.time()
    syms = symbols or [u["symbol"] for u in UNIVERSE]
    spy_b = service.bars("SPY", "1d")
    spy = {b["t"][:10]: b["c"] for b in spy_b["bars"]}
    buzz = _buzz()

    def one(sym: str):
        try:
            b = service.bars(sym, "1d")
            if len(b["bars"]) < 30:
                return None
            m = metrics(sym, b["bars"], spy)
            if live_quotes and b["source"] != "DEMO":  # daily bars are cached for hours; overlay the latest quote for price, change and volume
                try:
                    q = service.quote(sym)
                    if q.get("price"):
                        px, prev = float(q["price"]), _f(q.get("prev_close")) or m["prev_close"]
                        for k in ("vs_sma20", "vs_sma50", "vs_sma200", "from_high_52w", "from_low_52w"):
                            if m.get(k) is not None:
                                m[k] = (1 + m[k]) * px / m["price"] - 1
                        m["price"], m["change_pct"] = px, (px / prev - 1) if prev else m["change_pct"]
                        if q.get("volume"):
                            m["volume"] = float(q["volume"])
                            m["rel_volume"] = m["volume"] / m["avg_volume_20d"] if m["avg_volume_20d"] else None
                except Exception:  # noqa: BLE001
                    pass
            meta = META.get(sym, {"symbol": sym, "kind": "stock"})
            i = _info_for(sym) if with_info else {}
            row = {"symbol": sym, "name": meta.get("name") or i.get("name") or sym, "kind": meta.get("kind", "stock"),
                   "sector": meta.get("sector") or (SECTOR_MAP.get(i.get("sector"), i.get("sector")) if meta.get("kind") != "etf" else None), "category": meta.get("category") or ("Stock" if meta.get("kind") != "etf" else i.get("category")),
                   "region": meta.get("region") or ("United States" if meta.get("kind") != "etf" and (i.get("country") in (None, "United States")) else i.get("country")),
                   "theme": meta.get("theme"), "asset_class": meta.get("asset_class") or (None if meta.get("kind") != "etf" else "Equity"), "leverage": meta.get("leverage"),
                   "underlying": meta.get("underlying"), "source": b["source"], **m,
                   "market_cap": _f(i.get("market_cap")), "aum": _f(i.get("total_assets")), "expense_ratio": _f(i.get("expense_ratio")),
                   "forward_pe": _f(i.get("forward_pe")), "trailing_pe": _f(i.get("trailing_pe")), "ev_ebitda": _f(i.get("ev_ebitda")), "price_to_sales": _f(i.get("price_to_sales")),
                   "peg_ratio": _f(i.get("peg_ratio")), "revenue_growth": _f(i.get("revenue_growth")), "earnings_growth": _f(i.get("earnings_growth")),
                   "operating_margin": _f(i.get("operating_margin")), "roe": _f(i.get("roe")), "debt_to_equity": _f(i.get("debt_to_equity")),
                   "short_percent_float": _f(i.get("short_percent_float")), "dividend_yield": _f(i.get("dividend_yield")),
                   "beta": _f(i.get("beta")) if i.get("beta") is not None else m.get("beta_calc"), "buzz": buzz.get(sym)}
            if row["expense_ratio"] and row["expense_ratio"] > 0.2:  # some feeds give percent units
                row["expense_ratio"] /= 100
            if row["dividend_yield"] and row["dividend_yield"] > 1:
                row["dividend_yield"] /= 100
            if row["kind"] == "etf":
                row["sector"] = meta.get("sector")
            return row
        except Exception as e:  # noqa: BLE001
            log.debug("screener %s: %s", sym, e)
            return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = [r for r in ex.map(one, syms) if r]
    srcs = {r["source"] for r in rows}
    out = {"rows": rows, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "source": "DEMO" if "DEMO" in srcs else "LIVE" if rows else None,
           "seconds": round(time.time() - t0, 1), "universe": len(syms)}
    log.info("screener snapshot %s", json.dumps({k: v for k, v in out.items() if k != "rows"} | {"rows": len(rows)}))
    return out


def save(snap: dict[str, Any]) -> None:
    from sqlalchemy import delete, select

    from .db import SessionLocal
    from .models import ScreenerSnapshot

    with SessionLocal() as db:
        db.add(ScreenerSnapshot(source=snap["source"], rows=snap["rows"], seconds=snap.get("seconds")))
        db.commit()
        keep = db.scalars(select(ScreenerSnapshot.id).order_by(ScreenerSnapshot.id.desc()).limit(3)).all()
        if keep:
            db.execute(delete(ScreenerSnapshot).where(ScreenerSnapshot.id.not_in(keep)))
            db.commit()


def snapshot() -> dict[str, Any]:
    """Latest snapshot: memory, refreshed from the database at most once a minute. Builds one if none exists yet."""
    if _snap.get("checked") and time.time() - _snap["checked"] < 60 and _snap["rows"]:
        return _snap
    from sqlalchemy import select

    from .db import SessionLocal
    from .models import ScreenerSnapshot

    with SessionLocal() as db:
        row = db.scalar(select(ScreenerSnapshot).order_by(ScreenerSnapshot.id.desc()))
        if row:
            _snap.update(rows=row.rows, at=row.created_at.replace(tzinfo=row.created_at.tzinfo or dt.timezone.utc).isoformat(), source=row.source, checked=time.time())
            return _snap
    with _lock:
        if not _snap["rows"]:
            snap = build()
            save(snap)
            _snap.update(snap, checked=time.time())
    return _snap


def start_background() -> bool:
    if _lock.locked():
        return False

    def go():
        with _lock:
            try:
                snap = build()
                if snap["rows"]:
                    save(snap)
                    _snap.update(snap, checked=time.time())
            except Exception:  # noqa: BLE001
                log.exception("screener refresh failed")

    threading.Thread(target=go, daemon=True, name="screener").start()
    return True


# ── filtering ───────────────────────────────────────────────────────────────────────────────────
def _ok(row: dict[str, Any], f: str, op: str, val: Any) -> bool:
    x = row.get(f)
    if op == "true":
        return bool(x)
    if op == "false":
        return not x
    if op == "in":
        return x in val
    if op == "==":
        return x == val
    if op == "contains":
        return isinstance(x, str) and str(val).lower() in x.lower()
    if x is None:
        return False
    if op == ">=":
        return x >= val
    if op == "<=":
        return x <= val
    return True


OPS = {">=", "<=", "==", "in", "contains", "true", "false"}


def validate(spec: dict[str, Any]) -> None:
    """Raise 422 for an unknown field or operator in a custom/saved market screen."""
    from fastapi import HTTPException

    fl = spec.get("filters") or []
    if not isinstance(fl, list) or len(fl) > 15:
        raise HTTPException(422, "filters must be a list of up to 15 [field, op, value] items")
    for x in fl:
        if not isinstance(x, (list, tuple)) or len(x) != 3 or x[0] not in FIELDS | {k: None for k in TEXT_FIELDS} or x[1] not in OPS:
            raise HTTPException(422, f"Bad filter {x!r}")
        if x[1] in (">=", "<=") and not isinstance(x[2], (int, float)):
            raise HTTPException(422, f"{x[0]} needs a number")
    if spec.get("sort") and spec["sort"] not in FIELDS:
        raise HTTPException(422, "Unknown sort field")
    if spec.get("kind") not in (None, "stock", "etf"):
        raise HTTPException(422, "kind must be stock or etf")


def run(filters: list[tuple[str, str, Any]], sort: str, desc: bool = True, kind: str | None = None, limit: int = 50, rows: list[dict] | None = None) -> dict[str, Any]:
    data = rows if rows is not None else snapshot()["rows"]
    if kind in ("stock", "etf"):
        data = [r for r in data if r["kind"] == kind]
    hits = [r for r in data if all(_ok(r, *f) for f in filters)]
    hits.sort(key=lambda r: (r.get(sort) is None, -(r.get(sort) or 0) if desc else (r.get(sort) or 0)))
    ch = [r["change_pct"] for r in hits if r.get("change_pct") is not None]
    top = [r["change_pct"] for r in hits[:limit] if r.get("change_pct") is not None]
    return {"matches": len(hits), "rows": hits[:limit], "avg_change": float(np.mean(top)) if top else None,
            "advancers": sum(1 for x in ch if x > 0), "decliners": sum(1 for x in ch if x < 0)}


def run_preset(pid: str, limit: int | None = None) -> dict[str, Any]:
    p = BY_ID[pid]
    return {**run(p["filters"], p["sort"], p["desc"], p["kind"], limit or p["limit"]), "preset": {k: p[k] for k in ("id", "group", "title", "description", "sort", "columns", "kind")}}


def catalog() -> dict[str, Any]:
    snap = snapshot()
    rows = snap["rows"]
    groups = []
    for gid, gl in GROUPS:
        items = []
        for p in PRESETS:
            if p["group"] != gid:
                continue
            r = run(p["filters"], p["sort"], p["desc"], p["kind"], p["limit"], rows)
            r["rows"] = r["rows"][:3]
            items.append({k: p[k] for k in ("id", "title", "description", "kind", "sort", "desc")} | {"filters": [list(f) for f in p["filters"]]} | {"matches": min(r["matches"], p["limit"]), "total_matches": r["matches"],
                                                                                     "avg_change": r["avg_change"], "top": [x["symbol"] for x in r["rows"]]})
        groups.append({"id": gid, "label": gl, "presets": items})
    flat = {i["id"]: i for g in groups for i in g["presets"]}
    spot = [flat[x] for x in SPOTLIGHT if x in flat and flat[x]["total_matches"] > 0]
    breadth = [r["change_pct"] for r in rows if r.get("change_pct") is not None]
    return {"spotlight": spot, "groups": groups, "as_of": snap["at"], "source": snap["source"], "universe": len(rows),
            "breadth": {"advancers": sum(1 for x in breadth if x > 0), "decliners": sum(1 for x in breadth if x < 0), "median_change": float(np.median(breadth)) if breadth else None},
            "fields": [{"key": k, "label": v[0], "group": v[1], "unit": v[2]} for k, v in FIELDS.items()]}


def due(now_et: dt.datetime) -> bool:
    from sqlalchemy import select

    from .db import SessionLocal
    from .models import ScreenerSnapshot

    with SessionLocal() as db:
        last = db.scalar(select(ScreenerSnapshot.created_at).order_by(ScreenerSnapshot.id.desc()))
    if not last:
        return True
    last = last if last.tzinfo else last.replace(tzinfo=dt.timezone.utc)
    age = (dt.datetime.now(dt.timezone.utc) - last).total_seconds()
    session = now_et.weekday() < 5 and dt.time(9, 30) <= now_et.time() <= dt.time(16, 15)
    return age > (1800 if session else 3600)
