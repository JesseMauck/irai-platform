"""Streaming indicators with StockSharp semantics: process(value) -> current value; `is_formed` once the
window is full (S# LengthIndicator.IsFormed). Values before formation are None."""
from __future__ import annotations

import math
from collections import deque


class Indicator:
    length: int = 1

    def __init__(self) -> None:
        self.count = 0
        self.value: float | None = None

    @property
    def is_formed(self) -> bool:
        return self.count >= self.length

    def process(self, x: float) -> float | None:
        self.count += 1
        self.value = self._process(x)
        return self.value if self.is_formed else None

    def _process(self, x: float) -> float | None:  # pragma: no cover
        raise NotImplementedError


class SimpleMovingAverage(Indicator):
    def __init__(self, length: int = 32):
        super().__init__()
        self.length, self.buf = length, deque(maxlen=length)

    def _process(self, x):
        self.buf.append(x)
        return sum(self.buf) / self.length  # S# divides by Length (value only used once formed)


class ExponentialMovingAverage(Indicator):
    """S# EMA: seeded with the SMA of the first `length` values, then k = 2 / (length + 1)."""

    def __init__(self, length: int = 32):
        super().__init__()
        self.length, self._seed, self._ema = length, [], None

    def _process(self, x):
        if self._ema is None:
            self._seed.append(x)
            if len(self._seed) == self.length:
                self._ema = sum(self._seed) / self.length
            return self._ema
        k = 2 / (self.length + 1)
        self._ema = x * k + self._ema * (1 - k)
        return self._ema


class SmoothedMovingAverage(Indicator):
    """Wilder smoothing (S# SmoothedMovingAverage): seed with SMA, then (prev*(n-1) + x) / n."""

    def __init__(self, length: int = 32):
        super().__init__()
        self.length, self._seed, self._v = length, [], None

    def _process(self, x):
        if self._v is None:
            self._seed.append(x)
            if len(self._seed) == self.length:
                self._v = sum(self._seed) / self.length
            return self._v
        self._v = (self._v * (self.length - 1) + x) / self.length
        return self._v


class RelativeStrengthIndex(Indicator):
    """S# RSI: SMMA of gains and losses over `length`; formed after length+1 inputs."""

    def __init__(self, length: int = 14):
        super().__init__()
        self.length = length + 1
        self._n = length
        self._gain, self._loss, self._prev = SmoothedMovingAverage(length), SmoothedMovingAverage(length), None

    def _process(self, x):
        if self._prev is None:
            self._prev = x
            return None
        d, self._prev = x - self._prev, x
        g, lo = self._gain.process(max(d, 0.0)), self._loss.process(max(-d, 0.0))
        if g is None or lo is None:
            return None
        if lo == 0:
            return 100.0
        return 100 - 100 / (1 + g / lo)


class BollingerBands(Indicator):
    def __init__(self, length: int = 20, width: float = 2.0):
        super().__init__()
        self.length, self.width, self.buf = length, width, deque(maxlen=length)
        self.upper = self.lower = self.middle = None

    def _process(self, x):
        self.buf.append(x)
        m = sum(self.buf) / len(self.buf)
        sd = math.sqrt(sum((v - m) ** 2 for v in self.buf) / len(self.buf))
        self.middle, self.upper, self.lower = m, m + self.width * sd, m - self.width * sd
        return m


class MACD(Indicator):
    """MACD line = EMA(short) − EMA(long); signal = EMA(signal) of the line."""

    def __init__(self, short: int = 12, long: int = 26, signal: int = 9):
        super().__init__()
        self.length = long + signal - 1
        self._s, self._l, self._sig = ExponentialMovingAverage(short), ExponentialMovingAverage(long), ExponentialMovingAverage(signal)
        self.macd = self.signal = None

    def _process(self, x):
        s, lo = self._s.process(x), self._l.process(x)
        if s is None or lo is None:
            return None
        self.macd = s - lo
        self.signal = self._sig.process(self.macd)
        return self.macd


class Highest(Indicator):
    def __init__(self, length: int = 20):
        super().__init__()
        self.length, self.buf = length, deque(maxlen=length)

    def _process(self, x):
        self.buf.append(x)
        return max(self.buf)


class Lowest(Highest):
    def _process(self, x):
        self.buf.append(x)
        return min(self.buf)


class RateOfChange(Indicator):
    def __init__(self, length: int = 12):
        super().__init__()
        self.length, self.buf = length + 1, deque(maxlen=length + 1)

    def _process(self, x):
        self.buf.append(x)
        return (x / self.buf[0] - 1) * 100 if self.buf[0] else None
