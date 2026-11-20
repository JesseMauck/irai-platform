"""Strategy Lab: indicator maths, StockSharp strategy semantics, emulator fills, statistics, API gating."""
import math
import uuid

import pytest
from fastapi.testclient import TestClient

from app.algo import emulator, optimizer
from app.algo.indicators import (MACD, BollingerBands, ExponentialMovingAverage, RelativeStrengthIndex,
                                 SimpleMovingAverage)
from app.algo.strategies import REGISTRY, BuyAndHold, Candle, SmaCrossover, Strategy
from app.main import app


def candles(closes):
    return [Candle(f"2026-01-{i + 1:02d}" if i < 28 else f"d{i}", float(c)) for i, c in enumerate(closes)]


# ── indicators ────────────────────────────────────────────────────────────────────────────────────
def test_sma_forms_after_length():
    sma = SimpleMovingAverage(3)
    assert [sma.process(x) for x in [1, 2, 3, 4]] == [None, None, 2.0, 3.0]


def test_ema_seeded_with_sma():
    ema = ExponentialMovingAverage(3)
    out = [ema.process(x) for x in [1, 2, 3, 6]]
    assert out[:2] == [None, None] and out[2] == 2.0 and math.isclose(out[3], 6 * 0.5 + 2 * 0.5)


def test_rsi_bounds_and_known_value():
    rsi = RelativeStrengthIndex(2)
    vals = [rsi.process(x) for x in [10, 11, 12, 11]]
    assert vals[:2] == [None, None] and vals[2] == 100.0  # only gains so far
    # gains SMMA: seed (1+1)/2=1 → (1*1+0)/2 = .5; losses: seed 0 → (0+1)/2 = .5 → RSI 50
    assert math.isclose(vals[3], 50.0)


def test_bollinger_and_macd():
    bb = BollingerBands(4, 2)
    for x in [1, 2, 3, 4]:
        m = bb.process(x)
    assert m == 2.5 and math.isclose(bb.upper - m, 2 * math.sqrt(1.25))
    macd = MACD(2, 3, 2)
    for x in range(1, 20):
        macd.process(float(x))
    assert macd.macd > 0 and macd.signal is not None


# ── strategy + emulator semantics ────────────────────────────────────────────────────────────────
def test_fills_happen_on_next_bar_no_lookahead():
    r = emulator.run(BuyAndHold(), candles([100, 110, 121]), emulator.EmulationSettings(commission_bps=0, slippage_bps=0))
    assert r.fills[0].date == "2026-01-02" and r.fills[0].price == 110  # signal on bar 1, filled on bar 2
    assert math.isclose(r.statistics["return"], 121 / 110 - 1)
    assert r.equity[0]["equity"] == 100_000 and r.equity[1]["exposure"] == 1


def test_sma_cross_reverses_like_stocksharp_sample_when_short_allowed():
    prices = [10] * 5 + [20] * 5 + [5] * 6 + [30] * 6
    s = SmaCrossover(allow_short=True, short=2, long=4)
    r = emulator.run(s, candles(prices), emulator.EmulationSettings(commission_bps=0, slippage_bps=0))
    exposures = [f.exposure_after for f in r.fills]
    assert -1.0 in exposures and 1.0 in exposures
    assert any(abs(f.exposure_after - f.exposure_before) == 2 for f in r.fills)  # reversal = volume × 2


def test_long_only_never_shorts():
    prices = [10] * 5 + [20] * 5 + [5] * 6 + [30] * 6 + [3] * 6
    for key, cls in REGISTRY.items():
        r = emulator.run(cls(allow_short=False), candles(prices), emulator.EmulationSettings())
        assert all(f.exposure_after >= 0 for f in r.fills), key
        assert r.statistics["max_short_position"] == 0


def test_params_are_clamped():
    s = SmaCrossover(short=-5, long=10_000)
    assert s.params == {"short": 2, "long": 400}


def test_statistics_drawdown_and_commission():
    class Flip(Strategy):
        KEY = "flip"

        def on_candle(self, c):
            self.target(1 if self.position == 0 else 0)

    st = emulator.EmulationSettings(commission_bps=10, slippage_bps=0)
    r = emulator.run(Flip(), candles([100, 100, 50, 50, 100, 100]), st)
    s = r.statistics
    assert s["trade_count"] == len(r.fills) and s["commission_paid"] > 0
    assert 0.5 <= s["max_relative_drawdown"] < 0.51  # 50% price drop plus commission
    assert s["roundtrip_count"] >= 1 and s["winning_trades"] + s["losing_trades"] == len(r.roundtrips)


def test_optimizer_grid_and_out_of_sample():
    import random
    rnd = random.Random(3)
    px, closes = 100.0, []
    for _ in range(600):
        px *= math.exp(rnd.gauss(0.0004, 0.015))
        closes.append(px)
    out = optimizer.optimize("sma_cross", candles(closes), {"short": [5, 10, 20], "long": [50, 100]},
                             emulator.EmulationSettings())
    assert out["combinations"] == 6 and len(out["results"]) == 6
    assert out["out_of_sample"] and "return" in out["out_of_sample"]
    with pytest.raises(ValueError):
        optimizer.optimize("sma_cross", candles(closes), {"short": list(range(2, 30)), "long": list(range(30, 60))},
                           emulator.EmulationSettings())


# ── API ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c, plan=None):
    h = "lab" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h,
                                             "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def test_api_catalog_and_backtest(client):
    cat = client.get("/api/lab/strategies").json()
    assert {s["key"] for s in cat} >= {"sma_cross", "rsi_reversion", "buy_hold"}
    assert client.post("/api/lab/backtest", json={"symbol": "AAPL", "strategy": "sma_cross"}).status_code == 401
    h = _user(client)
    r = client.post("/api/lab/backtest", json={"symbol": "AAPL", "strategy": "sma_cross", "params": {"short": 10, "long": 30},
                                               "range": "2y"}, headers=h).json()
    assert r["params"] == {"short": 10, "long": 30} and r["data_source"] in ("LIVE", "DEMO", "STALE")
    s, ser = r["statistics"], r["series"]
    assert len(ser["dates"]) == len(ser["equity"]) == len(ser["benchmark"]) and ser["equity"][0] == 100_000
    assert s["bars"] > 400 and "sharpe" in s and "recovery_factor" in s
    assert client.get("/api/lab/runs", headers=h).json()[0]["symbol"] == "AAPL"
    assert client.post("/api/lab/backtest", json={"symbol": "AAPL", "strategy": "nope"}, headers=h).status_code == 404
    assert client.post("/api/lab/backtest", json={"symbol": "A$PL", "strategy": "sma_cross"}, headers=h).status_code == 422


def test_api_daily_quota_and_optimize_gating(client):
    h = _user(client)
    for _ in range(5):
        assert client.post("/api/lab/backtest", json={"symbol": "MSFT", "strategy": "buy_hold", "range": "1y"}, headers=h).status_code == 200
    assert client.post("/api/lab/backtest", json={"symbol": "MSFT", "strategy": "buy_hold", "range": "1y"}, headers=h).status_code == 402
    body = {"symbol": "MSFT", "strategy": "sma_cross", "grid": {"short": [5, 15, 5], "long": [40, 80, 20]}}
    assert client.post("/api/lab/optimize", json=body, headers=_user(client, "essential")).status_code == 402
    out = client.post("/api/lab/optimize", json=body, headers=_user(client, "pro")).json()
    assert out["combinations"] == 9 and out["best"]["params"]["short"] in (5, 10, 15)
    bad = {**body, "grid": {"short": [5, 15]}}
    assert client.post("/api/lab/optimize", json=bad, headers=_user(client, "pro")).status_code == 422


def test_montecarlo_engine_math():
    import numpy as np
    from app.algo.montecarlo import simulate
    rng = np.random.default_rng(1)
    r = rng.normal(0.0004, 0.01, size=(1000, 1))
    out = simulate(r, np.array([1.0]), start_value=100, horizon=252, paths=4000, method="gbm", target=130, stop=80)
    # median terminal ≈ 100·exp((mu - σ²/2)·252) for log-drift estimated from data
    # GBM: log price is normal with mean 252·E[log r], so the median terminal is S0·exp(252·E[log r]).
    lr = np.log1p(r[:, 0])
    assert abs(out["terminal"]["50"] / (100 * np.exp(252 * lr.mean())) - 1) < 0.03
    # zero drift = zero arithmetic expected return: the mean terminal value stays at S0
    z0 = simulate(r, np.array([1.0]), start_value=100, horizon=252, paths=20000, method="gbm", drift="zero")
    assert abs(z0["expected_terminal"] / 100 - 1) < 0.02
    assert out["fan"]["5"][-1] < out["fan"]["50"][-1] < out["fan"]["95"][-1]
    assert 0 <= out["prob_touch_target"] <= 1 and out["prob_touch_stop"] >= 0 and out["var_95"] > 0
    assert out["cvar_95"] >= out["var_95"]
    vol = out["ann_vol_hist"]
    assert abs(vol - 0.01 * np.sqrt(252)) < 0.02
    boot = simulate(np.hstack([r, r * 0.5]), np.array([0.5, 0.5]), start_value=1e4, horizon=21, paths=500, method="bootstrap")
    assert len(boot["fan"]["50"]) == 21 and boot["start_value"] == 1e4


def test_montecarlo_api(client):
    assert client.post("/api/lab/montecarlo", json={"holdings": [{"symbol": "AAPL"}]}).status_code == 401
    h = _user(client, "pro")
    r = client.post("/api/lab/montecarlo", json={"holdings": [{"symbol": "AAPL"}], "horizon_days": 63, "paths": 500,
                                                 "target": 1e9, "stop": 1}, headers=h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["mode"] == "price" and b["prob_touch_target"] == 0 and len(b["fan"]["50"]) == 63
    p = client.post("/api/lab/montecarlo", json={"holdings": [{"symbol": "AAPL", "weight": 0.6}, {"symbol": "MSFT", "weight": 0.4}],
                                                 "method": "student_t", "start_value": 50000, "horizon_days": 21, "paths": 300}, headers=h).json()
    assert p["mode"] == "portfolio" and p["weights"] == [0.6, 0.4]
