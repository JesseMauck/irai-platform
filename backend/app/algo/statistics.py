"""Backtest statistics. The first block mirrors StockSharp's StatisticManager parameters
(Algo/Statistics: NetProfit, Return, MaxDrawdown, MaxRelativeDrawdown, RecoveryFactor, MaxProfit,
TradeCount, RoundtripCount, WinningTrades, LossingTrades, AverageTrade, AverageWinTrade,
AverageLossTrade, MaxLongPosition, MaxShortPosition); the second adds risk-adjusted measures."""
from __future__ import annotations

import math
import statistics as st
from typing import Any


def compute_statistics(res, capital: float, candles, max_long: float, max_short: float) -> dict[str, Any]:
    eq = [e["equity"] for e in res.equity]
    peak, max_dd, max_rdd, max_profit = eq[0], 0.0, 0.0, 0.0
    for v in eq:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)
        max_rdd = max(max_rdd, (peak - v) / peak if peak else 0)
        max_profit = max(max_profit, v - capital)
    net = eq[-1] - capital
    closed = [r for r in res.roundtrips if r.exit_date]
    pnls = [r.pnl for r in res.roundtrips]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p <= 0]
    rets = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq)) if eq[i - 1]]
    years = max(len(eq) - 1, 1) / 252
    vol = st.pstdev(rets) * math.sqrt(252) if len(rets) > 1 else 0.0
    mean = st.mean(rets) if rets else 0.0
    downside = [r for r in rets if r < 0]
    dvol = math.sqrt(sum(r * r for r in downside) / len(rets)) * math.sqrt(252) if rets else 0.0
    cagr = (eq[-1] / capital) ** (1 / years) - 1 if eq[-1] > 0 else -1.0
    bh = candles[-1].close / candles[0].close - 1
    exposure = sum(1 for e in res.equity if e["exposure"]) / len(res.equity)
    return {
        # StockSharp StatisticManager equivalents
        "net_profit": net, "return": net / capital, "max_drawdown": max_dd, "max_relative_drawdown": max_rdd,
        "recovery_factor": net / max_dd if max_dd else None, "max_profit": max_profit,
        "trade_count": len(res.fills), "roundtrip_count": len(closed), "winning_trades": len(wins),
        "losing_trades": len(losses), "average_trade": st.mean(pnls) if pnls else None,
        "average_win": st.mean(wins) if wins else None, "average_loss": st.mean(losses) if losses else None,
        "max_long_position": max_long, "max_short_position": max_short,
        # risk-adjusted extras
        "cagr": cagr, "volatility": vol, "sharpe": (mean * 252) / vol if vol else None,
        "sortino": (mean * 252) / dvol if dvol else None, "calmar": cagr / max_rdd if max_rdd else None,
        "win_rate": len(wins) / len(pnls) if pnls else None,
        "profit_factor": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else None,
        "exposure": exposure, "buy_hold_return": bh, "excess_return": net / capital - bh,
        "commission_paid": sum(f.commission for f in res.fills), "bars": len(eq),
        "start": candles[0].date, "end": candles[-1].date,
    }
