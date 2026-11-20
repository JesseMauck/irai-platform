"""Parameter grid search (the role of S# BatchEmulation), with a walk-forward check: optimise on the
first part of history (in-sample) and report how the best set did on the rest (out-of-sample)."""
from __future__ import annotations

import itertools
from typing import Any

from . import emulator
from .strategies import REGISTRY, Candle

MAX_COMBOS = 400


def frange(lo: float, hi: float, step: float) -> list[float]:
    out, x = [], lo
    while x <= hi + 1e-9 and len(out) < 200:
        out.append(round(x, 6))
        x += step
    return out


def optimize(strategy_key: str, candles: list[Candle], grid: dict[str, list[float]], settings: emulator.EmulationSettings,
             metric: str = "sharpe", in_sample: float = 0.7, fixed: dict[str, Any] | None = None) -> dict[str, Any]:
    cls = REGISTRY[strategy_key]
    keys = [k for k in grid if any(p.key == k for p in cls.PARAMS)]
    combos = list(itertools.product(*[grid[k] for k in keys]))
    if not combos or len(combos) > MAX_COMBOS:
        raise ValueError(f"Grid must have between 1 and {MAX_COMBOS} combinations (got {len(combos)})")
    split = max(2, int(len(candles) * in_sample))
    ins, oos = candles[:split], candles[split:]
    rows = []
    for combo in combos:
        params = {**(fixed or {}), **dict(zip(keys, combo))}
        r = emulator.run(cls(allow_short=settings.allow_short, **params), ins, settings)
        s = r.statistics
        rows.append({"params": params, "return": s["return"], "sharpe": s["sharpe"], "max_relative_drawdown": s["max_relative_drawdown"],
                     "roundtrips": s["roundtrip_count"], "win_rate": s["win_rate"]})

    def score(row):
        v = row.get(metric)
        return v if v is not None else float("-inf")

    rows.sort(key=score, reverse=True)
    best = rows[0]
    oos_stats = None
    if len(oos) >= 30:
        warm = candles[max(0, split - 400):]  # warm indicators up on in-sample tail, then measure OOS only
        r = emulator.run(cls(allow_short=settings.allow_short, **best["params"]), warm, settings)
        start = len(warm) - len(oos)
        eq = [e["equity"] for e in r.equity[start - 1:]] if start > 0 else [e["equity"] for e in r.equity]
        oos_stats = {"return": eq[-1] / eq[0] - 1, "start": oos[0].date, "end": oos[-1].date,
                     "buy_hold_return": oos[-1].close / oos[0].close - 1}
    return {"metric": metric, "keys": keys, "combinations": len(combos), "in_sample": {"start": ins[0].date, "end": ins[-1].date},
            "results": rows[:100], "best": best, "out_of_sample": oos_stats,
            "warning": "The best in-sample parameters are usually worse out of sample. Judge the out-of-sample row, not the top of the table."}
