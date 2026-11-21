"""Strategy tear sheet: 50 performance, risk, benchmark-relative and trade statistics from an equity curve,
optional closed-trade P&L and an optional benchmark price series. Used for backtests and for live paper
track records, so the two can be compared metric by metric."""
from __future__ import annotations

import math
import statistics as st
from typing import Any

TRADING_DAYS = 252

# key -> (label, group, format)   format: pct | ratio | num | days | money | int
METRICS: dict[str, tuple[str, str, str]] = {
    "total_return": ("Total return", "Returns", "pct"), "cagr": ("CAGR", "Returns", "pct"),
    "return_1m": ("Last month", "Returns", "pct"), "return_3m": ("Last 3 months", "Returns", "pct"),
    "return_6m": ("Last 6 months", "Returns", "pct"), "return_1y": ("Last 12 months", "Returns", "pct"),
    "ytd": ("Year to date", "Returns", "pct"), "avg_daily_return": ("Average daily return", "Returns", "pct"),
    "avg_monthly_return": ("Average monthly return", "Returns", "pct"), "best_day": ("Best day", "Returns", "pct"),
    "worst_day": ("Worst day", "Returns", "pct"), "best_month": ("Best month", "Returns", "pct"),
    "worst_month": ("Worst month", "Returns", "pct"), "positive_days": ("Positive days", "Returns", "pct"),
    "positive_months": ("Positive months", "Returns", "pct"),
    "volatility": ("Volatility (annual)", "Risk", "pct"), "downside_deviation": ("Downside deviation", "Risk", "pct"),
    "max_drawdown": ("Max drawdown", "Risk", "pct"), "max_drawdown_days": ("Longest drawdown", "Risk", "days"),
    "avg_drawdown": ("Average drawdown", "Risk", "pct"), "current_drawdown": ("Current drawdown", "Risk", "pct"),
    "ulcer_index": ("Ulcer index", "Risk", "ratio"), "var_95": ("Daily VaR (95%)", "Risk", "pct"),
    "cvar_95": ("Daily CVaR (95%)", "Risk", "pct"), "skew": ("Skew", "Risk", "ratio"), "kurtosis": ("Excess kurtosis", "Risk", "ratio"),
    "sharpe": ("Sharpe ratio", "Risk-adjusted", "ratio"), "sortino": ("Sortino ratio", "Risk-adjusted", "ratio"),
    "calmar": ("Calmar ratio", "Risk-adjusted", "ratio"), "omega": ("Omega ratio", "Risk-adjusted", "ratio"),
    "gain_pain": ("Gain/pain ratio", "Risk-adjusted", "ratio"), "tail_ratio": ("Tail ratio", "Risk-adjusted", "ratio"),
    "recovery_factor": ("Recovery factor", "Risk-adjusted", "ratio"), "kelly": ("Kelly fraction", "Risk-adjusted", "pct"),
    "benchmark_return": ("Benchmark return", "Vs benchmark", "pct"), "excess_return": ("Excess return", "Vs benchmark", "pct"),
    "alpha": ("Alpha (annual)", "Vs benchmark", "pct"), "beta": ("Beta", "Vs benchmark", "ratio"),
    "correlation": ("Correlation", "Vs benchmark", "ratio"), "r_squared": ("R-squared", "Vs benchmark", "ratio"),
    "tracking_error": ("Tracking error", "Vs benchmark", "pct"), "information_ratio": ("Information ratio", "Vs benchmark", "ratio"),
    "up_capture": ("Up capture", "Vs benchmark", "pct"), "down_capture": ("Down capture", "Vs benchmark", "pct"),
    "trades": ("Closed trades", "Trades", "int"), "win_rate": ("Win rate", "Trades", "pct"),
    "profit_factor": ("Profit factor", "Trades", "ratio"), "payoff_ratio": ("Payoff ratio", "Trades", "ratio"),
    "avg_win": ("Average win", "Trades", "money"), "avg_loss": ("Average loss", "Trades", "money"),
    "expectancy": ("Expectancy per trade", "Trades", "money"), "largest_win": ("Largest win", "Trades", "money"),
    "largest_loss": ("Largest loss", "Trades", "money"), "max_consecutive_wins": ("Max consecutive wins", "Trades", "int"),
    "max_consecutive_losses": ("Max consecutive losses", "Trades", "int"), "exposure": ("Time in market", "Trades", "pct"),
    "days": ("Trading days", "Trades", "int"),
}


def _pct_rank(xs: list[float], q: float) -> float:
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(math.floor(q * (len(s) - 1)))))
    return s[k]


def _monthly(dates: list[str], eq: list[float]) -> list[float]:
    last: dict[str, float] = {}
    for d, v in zip(dates, eq):
        last[d[:7]] = v
    vals = list(last.values())
    first = eq[0]
    out, prev = [], first
    for v in vals:
        out.append(v / prev - 1 if prev else 0.0)
        prev = v
    return out


def _streak(pnls: list[float], win: bool) -> int:
    best = cur = 0
    for p in pnls:
        cur = cur + 1 if ((p > 0) == win) else 0
        best = max(best, cur)
    return best


MIN_DAYS_ANNUALISED = 20
ANNUALISED = ("cagr", "volatility", "downside_deviation", "sharpe", "sortino", "calmar", "omega", "gain_pain", "recovery_factor",
              "tail_ratio", "var_95", "cvar_95", "skew", "kurtosis", "ulcer_index", "alpha", "beta", "correlation", "r_squared",
              "tracking_error", "information_ratio", "up_capture", "down_capture", "avg_monthly_return", "positive_months",
              "best_month", "worst_month")


def compute(dates: list[str], equity: list[float], trade_pnls: list[float] | None = None,
            bench: list[float] | None = None, exposure: list[bool] | None = None) -> dict[str, Any]:
    """dates/equity: aligned daily series (at least 2 points). bench: benchmark closes aligned with dates.
    With fewer than 20 daily returns, annualised and ratio statistics are withheld (None): a two-day record
    annualised is noise, not information."""
    out = _compute(dates, equity, trade_pnls, bench, exposure)
    if out.get("days") is not None and out["days"] - 1 < MIN_DAYS_ANNUALISED:
        for k in ANNUALISED:
            out[k] = None
        out["insufficient_history"] = True
    return out


def _compute(dates: list[str], equity: list[float], trade_pnls: list[float] | None = None,
             bench: list[float] | None = None, exposure: list[bool] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {k: None for k in METRICS}
    n = len(equity)
    if n < 2 or not equity[0]:
        out["days"] = n
        return out
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, n) if equity[i - 1]]
    years = max(len(rets), 1) / TRADING_DAYS
    total = equity[-1] / equity[0] - 1
    out.update(total_return=total, days=n, cagr=(equity[-1] / equity[0]) ** (1 / years) - 1 if equity[-1] > 0 else -1.0)

    def back(k: int):
        return equity[-1] / equity[-1 - k] - 1 if n > k else None

    out.update(return_1m=back(21), return_3m=back(63), return_6m=back(126), return_1y=back(252))
    y = dates[-1][:4]
    prior = [v for d, v in zip(dates, equity) if d[:4] < y]
    out["ytd"] = equity[-1] / prior[-1] - 1 if prior else total
    mean = st.fmean(rets)
    vol = st.pstdev(rets) * math.sqrt(TRADING_DAYS) if len(rets) > 1 else 0.0
    down = [r for r in rets if r < 0]
    dd_dev = math.sqrt(sum(r * r for r in down) / len(rets)) * math.sqrt(TRADING_DAYS)
    out.update(avg_daily_return=mean, best_day=max(rets), worst_day=min(rets), positive_days=sum(r > 0 for r in rets) / len(rets),
               volatility=vol, downside_deviation=dd_dev)
    months = _monthly(dates, equity)
    if months:
        out.update(avg_monthly_return=st.fmean(months), best_month=max(months), worst_month=min(months),
                   positive_months=sum(m > 0 for m in months) / len(months))
    # drawdowns
    peak, dds, longest, cur_len, sq = equity[0], [], 0, 0, 0.0
    for v in equity:
        peak = max(peak, v)
        d = v / peak - 1 if peak else 0.0
        dds.append(d)
        sq += (d * 100) ** 2
        cur_len = cur_len + 1 if d < 0 else 0
        longest = max(longest, cur_len)
    mdd = min(dds)
    under = [d for d in dds if d < 0]
    out.update(max_drawdown=mdd, max_drawdown_days=longest, avg_drawdown=st.fmean(under) if under else 0.0,
               current_drawdown=dds[-1], ulcer_index=math.sqrt(sq / n))
    if len(rets) >= 20:
        var = _pct_rank(rets, 0.05)
        tail = [r for r in rets if r <= var]
        out.update(var_95=var, cvar_95=st.fmean(tail) if tail else var)
        p95, p5 = _pct_rank(rets, 0.95), _pct_rank(rets, 0.05)
        out["tail_ratio"] = abs(p95 / p5) if p5 else None
    if len(rets) > 2 and st.pstdev(rets):
        sd = st.pstdev(rets)
        out["skew"] = sum((r - mean) ** 3 for r in rets) / len(rets) / sd ** 3
        out["kurtosis"] = sum((r - mean) ** 4 for r in rets) / len(rets) / sd ** 4 - 3
    out["sharpe"] = mean * TRADING_DAYS / vol if vol else None
    out["sortino"] = mean * TRADING_DAYS / dd_dev if dd_dev else None
    out["calmar"] = out["cagr"] / abs(mdd) if mdd else None
    gains, losses = sum(r for r in rets if r > 0), -sum(r for r in rets if r < 0)
    out["omega"] = gains / losses if losses else None
    out["gain_pain"] = (sum(rets) / losses) if losses else None
    out["recovery_factor"] = total / abs(mdd) if mdd else None
    # vs benchmark
    if bench and len(bench) == n and bench[0]:
        b = [bench[i] / bench[i - 1] - 1 for i in range(1, n) if bench[i - 1]]
        m = min(len(b), len(rets))
        r_, b_ = rets[-m:], b[-m:]
        out["benchmark_return"] = bench[-1] / bench[0] - 1
        out["excess_return"] = total - out["benchmark_return"]
        if m > 20 and st.pvariance(b_):
            mb, mr = st.fmean(b_), st.fmean(r_)
            cov = sum((x - mb) * (y - mr) for x, y in zip(b_, r_)) / m
            beta = cov / st.pvariance(b_)
            corr = cov / (st.pstdev(b_) * st.pstdev(r_)) if st.pstdev(r_) else None
            diff = [y - x for x, y in zip(b_, r_)]
            te = st.pstdev(diff) * math.sqrt(TRADING_DAYS)
            ups = [(x, y) for x, y in zip(b_, r_) if x > 0]
            dns = [(x, y) for x, y in zip(b_, r_) if x < 0]
            out.update(beta=beta, correlation=corr, r_squared=corr * corr if corr is not None else None,
                       alpha=(mr - beta * mb) * TRADING_DAYS, tracking_error=te,
                       information_ratio=st.fmean(diff) * TRADING_DAYS / te if te else None,
                       up_capture=(st.fmean(y for _, y in ups) / st.fmean(x for x, _ in ups)) if ups else None,
                       down_capture=(st.fmean(y for _, y in dns) / st.fmean(x for x, _ in dns)) if dns else None)
    # trades
    pnls = list(trade_pnls or [])
    out["trades"] = len(pnls)
    if pnls:
        wins, loss = [p for p in pnls if p > 0], [p for p in pnls if p <= 0]
        wr = len(wins) / len(pnls)
        aw, al = (st.fmean(wins) if wins else None), (st.fmean(loss) if loss else None)
        out.update(win_rate=wr, avg_win=aw, avg_loss=al, expectancy=st.fmean(pnls), largest_win=max(pnls), largest_loss=min(pnls),
                   profit_factor=(sum(wins) / -sum(loss)) if loss and sum(loss) < 0 else None,
                   payoff_ratio=(aw / -al) if aw is not None and al else None,
                   max_consecutive_wins=_streak(pnls, True), max_consecutive_losses=_streak(pnls, False))
        if out["payoff_ratio"]:
            out["kelly"] = wr - (1 - wr) / out["payoff_ratio"]
    if exposure:
        out["exposure"] = sum(1 for e in exposure if e) / len(exposure)
    return out


def compare(backtest: dict[str, Any], live: dict[str, Any]) -> list[dict[str, Any]]:
    """Side-by-side rows for the live-vs-backtest track record."""
    rows = []
    for k in ("cagr", "total_return", "volatility", "sharpe", "sortino", "max_drawdown", "win_rate", "profit_factor",
              "avg_daily_return", "beta", "correlation", "exposure"):
        bt, lv = backtest.get(k), live.get(k)
        rows.append({"key": k, "label": METRICS[k][0], "format": METRICS[k][2], "backtest": bt, "live": lv,
                     "difference": (lv - bt) if isinstance(bt, (int, float)) and isinstance(lv, (int, float)) else None})
    return rows


def schema() -> list[dict[str, str]]:
    return [{"key": k, "label": v[0], "group": v[1], "format": v[2]} for k, v in METRICS.items()]
