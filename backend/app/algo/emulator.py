"""History emulation (port of the S# HistoryEmulationConnector + MarketEmulator idea, on daily closes).

Orders registered while processing candle t are filled at candle t+1's close, adjusted for slippage, and
charged commission on traded notional. Exposure is rebalanced in shares sized from current equity, so P&L
compounds like a real account.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .statistics import compute_statistics
from .strategies import Candle, Strategy


@dataclass
class EmulationSettings:
    initial_capital: float = 100_000.0
    commission_bps: float = 1.0   # per side, on notional
    slippage_bps: float = 2.0     # adverse, per fill
    allow_short: bool = False


@dataclass
class Fill:
    date: str
    side: str
    exposure_before: float
    exposure_after: float
    price: float
    shares: float
    commission: float


@dataclass
class Roundtrip:
    direction: str
    entry_date: str
    entry_price: float
    exit_date: str | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    return_pct: float | None = None
    bars: int = 0


@dataclass
class EmulationResult:
    equity: list[dict[str, Any]] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    roundtrips: list[Roundtrip] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)
    indicators: list[dict[str, Any]] = field(default_factory=list)


def run(strategy: Strategy, candles: list[Candle], settings: EmulationSettings) -> EmulationResult:
    if len(candles) < 2:
        raise ValueError("Need at least two candles")
    cash, shares = settings.initial_capital, 0.0
    res = EmulationResult()
    open_rt: Roundtrip | None = None
    rt_entry_equity = 0.0
    max_long = max_short = 0.0

    for i, c in enumerate(candles):
        # 1) fill orders registered on the previous candle at this candle's price
        if strategy.pending:
            delta_units = sum(strategy.pending)
            strategy.pending.clear()
            before = strategy.position
            after = before + delta_units
            if abs(delta_units) > 1e-12:
                side = "buy" if delta_units > 0 else "sell"
                px = c.close * (1 + (settings.slippage_bps / 1e4) * (1 if side == "buy" else -1))
                equity = cash + shares * c.close
                target_shares = after * equity / px if after else 0.0
                traded = target_shares - shares
                commission = abs(traded) * px * settings.commission_bps / 1e4
                cash -= traded * px + commission
                shares = target_shares
                strategy.position = after
                res.fills.append(Fill(c.date, side, before, after, px, traded, commission))
                max_long, max_short = max(max_long, after), min(max_short, after)
                eq_now = cash + shares * c.close
                # round-trip bookkeeping: close on flat or sign flip, open on new exposure
                if open_rt and (after == 0 or (after > 0) != (before > 0)):
                    open_rt.exit_date, open_rt.exit_price = c.date, px
                    open_rt.pnl = eq_now - rt_entry_equity
                    open_rt.return_pct = open_rt.pnl / rt_entry_equity if rt_entry_equity else None
                    res.roundtrips.append(open_rt)
                    open_rt = None
                if after != 0 and open_rt is None:
                    open_rt = Roundtrip("long" if after > 0 else "short", c.date, px)
                    rt_entry_equity = eq_now
        if open_rt:
            open_rt.bars += 1
        # 2) mark to market, then let the strategy see the finished candle
        equity = cash + shares * c.close
        res.equity.append({"date": c.date, "equity": equity, "close": c.close, "exposure": strategy.position})
        strategy.on_candle(c)
        res.indicators.append({"date": c.date, **strategy.indicators})

    if open_rt:  # mark the open position at the last close
        last = candles[-1]
        eq = res.equity[-1]["equity"]
        open_rt.pnl = eq - rt_entry_equity
        open_rt.return_pct = open_rt.pnl / rt_entry_equity if rt_entry_equity else None
        res.roundtrips.append(open_rt)
        open_rt.exit_price = None
        _ = last
    res.statistics = compute_statistics(res, settings.initial_capital, candles, max_long, max_short)
    return res
