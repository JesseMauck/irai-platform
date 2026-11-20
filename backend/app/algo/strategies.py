"""Candle-driven strategies with StockSharp semantics.

A strategy sees one finished candle at a time (S# WhenCandlesFinished) and registers orders with
`buy(volume)` / `sell(volume)`. `position` is the current exposure in units of `volume` (1.0 = fully
invested long, −1.0 = fully short). The emulator fills orders on the *next* candle, so a strategy can
never trade on the bar that produced its signal (no look-ahead).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .indicators import (MACD, BollingerBands, ExponentialMovingAverage, Highest, Lowest, RelativeStrengthIndex,
                         SimpleMovingAverage)


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    default: float
    min: float
    max: float
    step: float = 1
    kind: str = "int"  # int | float

    def clamp(self, v: Any) -> float:
        try:
            x = float(v)
        except (TypeError, ValueError):
            x = self.default
        x = max(self.min, min(self.max, x))
        return int(round(x)) if self.kind == "int" else x


@dataclass
class Candle:
    date: str
    close: float


class Strategy:
    KEY = "base"
    TITLE = "Base"
    DESCRIPTION = ""
    PARAMS: list[Param] = []

    def __init__(self, allow_short: bool = False, volume: float = 1.0, **params: Any):
        self.allow_short = allow_short
        self.volume = volume
        self.params = {p.key: p.clamp(params.get(p.key, p.default)) for p in self.PARAMS}
        self.position = 0.0
        self.pending: list[float] = []  # signed order volumes awaiting fill
        self.indicators: dict[str, float | None] = {}
        self.setup()

    # S#-style order API ------------------------------------------------------------------------
    def buy(self, volume: float) -> None:
        if volume > 0:
            self.pending.append(volume)

    def sell(self, volume: float) -> None:
        if volume <= 0:
            return
        if not self.allow_short:
            volume = min(volume, max(self.position + sum(self.pending), 0.0))  # flatten only
        if volume > 0:
            self.pending.append(-volume)

    def target(self, exposure: float) -> None:
        """Convenience: move to a target exposure in units of volume."""
        exposure = exposure if self.allow_short else max(exposure, 0.0)
        delta = exposure * self.volume - (self.position + sum(self.pending))
        if delta > 1e-12:
            self.buy(delta)
        elif delta < -1e-12:
            self.sell(-delta)

    def setup(self) -> None:  # create indicators
        pass

    def on_candle(self, c: Candle) -> None:  # pragma: no cover
        raise NotImplementedError

    @classmethod
    def schema(cls) -> dict[str, Any]:
        return {"key": cls.KEY, "title": cls.TITLE, "description": cls.DESCRIPTION,
                "params": [p.__dict__ for p in cls.PARAMS]}


class SmaCrossover(Strategy):
    """Port of StockSharp SampleHistoryTesting/SmaStrategy.cs."""
    KEY, TITLE = "sma_cross", "SMA crossover (StockSharp sample)"
    DESCRIPTION = ("Buy when the short SMA crosses above the long SMA, sell when it crosses below. Like the S# sample, "
                   "an opposite cross reverses the position (volume × 2) when shorting is allowed.")
    PARAMS = [Param("short", "Short SMA", 20, 2, 200), Param("long", "Long SMA", 50, 5, 400)]

    def setup(self):
        self.short_ma = SimpleMovingAverage(self.params["short"])
        self.long_ma = SimpleMovingAverage(self.params["long"])
        self._short_below: bool | None = None

    def on_candle(self, c):
        s, lo = self.short_ma.process(c.close), self.long_ma.process(c.close)
        self.indicators = {"short_sma": s, "long_sma": lo}
        if s is None or lo is None:
            return
        below = s < lo
        if self._short_below is None:  # S#: store current relation when the strategy starts
            self._short_below = below
            return
        if below != self._short_below:
            pos = self.position + sum(self.pending)
            vol = self.volume if pos == 0 else min(abs(pos), self.volume) * 2  # open, or reverse
            (self.sell if below else self.buy)(vol)
            self._short_below = below


class EmaCrossover(SmaCrossover):
    KEY, TITLE = "ema_cross", "EMA crossover"
    DESCRIPTION = "Same rules as the SMA crossover with exponential moving averages, which react faster."
    PARAMS = [Param("short", "Short EMA", 12, 2, 200), Param("long", "Long EMA", 26, 5, 400)]

    def setup(self):
        self.short_ma = ExponentialMovingAverage(self.params["short"])
        self.long_ma = ExponentialMovingAverage(self.params["long"])
        self._short_below = None


class RsiReversion(Strategy):
    KEY, TITLE = "rsi_reversion", "RSI mean reversion"
    DESCRIPTION = "Go long when RSI falls below the oversold level, exit when it rises above the exit level."
    PARAMS = [Param("length", "RSI length", 14, 2, 100), Param("oversold", "Oversold", 30, 5, 50),
              Param("exit", "Exit level", 55, 40, 95)]

    def setup(self):
        self.rsi = RelativeStrengthIndex(self.params["length"])

    def on_candle(self, c):
        r = self.rsi.process(c.close)
        self.indicators = {"rsi": r}
        if r is None:
            return
        if r < self.params["oversold"]:
            self.target(1)
        elif r > self.params["exit"]:
            self.target(-1 if self.allow_short and r > 100 - self.params["oversold"] else 0)


class BollingerReversion(Strategy):
    KEY, TITLE = "bollinger_reversion", "Bollinger band reversion"
    DESCRIPTION = "Buy closes below the lower band, exit at the middle band (short above the upper band if allowed)."
    PARAMS = [Param("length", "Length", 20, 5, 200), Param("width", "Width (σ)", 2.0, 0.5, 4.0, 0.25, "float")]

    def setup(self):
        self.bb = BollingerBands(self.params["length"], self.params["width"])

    def on_candle(self, c):
        m = self.bb.process(c.close)
        self.indicators = {"bb_mid": m, "bb_upper": self.bb.upper if m else None, "bb_lower": self.bb.lower if m else None}
        if m is None:
            return
        pos = self.position + sum(self.pending)
        if c.close < self.bb.lower:
            self.target(1)
        elif c.close > self.bb.upper and self.allow_short:
            self.target(-1)
        elif (pos > 0 and c.close >= m) or (pos < 0 and c.close <= m):
            self.target(0)


class MacdCross(Strategy):
    KEY, TITLE = "macd_cross", "MACD signal cross"
    DESCRIPTION = "Long when the MACD line crosses above its signal line; flat (or short) when it crosses below."
    PARAMS = [Param("short", "Fast EMA", 12, 2, 50), Param("long", "Slow EMA", 26, 5, 200), Param("signal", "Signal EMA", 9, 2, 50)]

    def setup(self):
        self.macd = MACD(self.params["short"], self.params["long"], self.params["signal"])

    def on_candle(self, c):
        self.macd.process(c.close)
        m, s = self.macd.macd, self.macd.signal
        self.indicators = {"macd": m, "signal": s}
        if m is None or s is None:
            return
        self.target(1 if m > s else -1)


class DonchianBreakout(Strategy):
    KEY, TITLE = "donchian_breakout", "Donchian channel breakout"
    DESCRIPTION = "Trend following: buy a close above the prior N-day high, exit below the prior M-day low."
    PARAMS = [Param("entry", "Entry lookback", 55, 5, 250), Param("exit", "Exit lookback", 20, 3, 250)]

    def setup(self):
        self.hi, self.lo = Highest(self.params["entry"]), Lowest(self.params["exit"])
        self._prev_hi = self._prev_lo = None

    def on_candle(self, c):
        if self._prev_hi is not None and c.close > self._prev_hi:
            self.target(1)
        elif self._prev_lo is not None and c.close < self._prev_lo:
            self.target(-1 if self.allow_short else 0)
        self._prev_hi, self._prev_lo = self.hi.process(c.close), self.lo.process(c.close)
        self.indicators = {"upper": self._prev_hi, "lower": self._prev_lo}


class BuyAndHold(Strategy):
    KEY, TITLE = "buy_hold", "Buy and hold (benchmark)"
    DESCRIPTION = "Buys on the first candle and holds. Every backtest is compared against this."
    PARAMS: list[Param] = []

    def on_candle(self, c):
        if self.position + sum(self.pending) == 0:
            self.buy(self.volume)


REGISTRY: dict[str, type[Strategy]] = {s.KEY: s for s in
                                        (SmaCrossover, EmaCrossover, RsiReversion, BollingerReversion, MacdCross,
                                         DonchianBreakout, BuyAndHold)}
