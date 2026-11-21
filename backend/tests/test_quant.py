import datetime as dt
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.quant import datapipe, patterns


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(c, plan=None):
    h = "qt" + uuid.uuid4().hex[:8]
    tok = c.post("/api/auth/register", json={"email": f"{h}@test.io", "password": "pw-123456789", "handle": h, "display_name": h}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    if plan:
        c.post("/api/billing/checkout", json={"plan": plan}, headers=hdr)
    c.cookies.clear()
    return hdr


def _hist(n=300, start=100.0, seed=1):
    rng = np.random.default_rng(seed)
    d0 = dt.date(2024, 1, 1)
    out, px, d = [], start, d0
    while len(out) < n:
        if d.weekday() < 5:
            px *= 1 + rng.normal(0, 0.01)
            out.append({"date": d.isoformat(), "close": px})
        d += dt.timedelta(days=1)
    return out


def test_profile_and_clean_fix_gaps_duplicates_and_spikes():
    h = _hist(120)
    h.insert(10, dict(h[10]))  # duplicate date
    del h[50:52]  # 2-day gap, within the fill limit
    h[80] = {**h[80], "close": h[80]["close"] * 3}  # one-day spike that reverts
    prof = datapipe.profile("TEST", h)
    assert prof["quality"] < 1 and prof["issues"]
    dates, closes, actions = datapipe.clean(h)
    assert len(dates) == len(set(dates))
    assert prof["duplicates"] == 1 and actions["filled"] >= 2 and actions["spikes_fixed"] >= 1
    assert np.max(np.abs(np.diff(np.log(closes)))) < 0.2


def test_features_splits_and_psi():
    c = np.array([r["close"] for r in _hist(400)])
    f = datapipe.features(c)
    assert set(datapipe.FEATURES) <= set(f)
    assert all(len(v) == len(c) for v in f.values())
    assert np.isnan(f["ret_21d"][:21]).all() and np.isfinite(f["ret_21d"][-1])
    dates = [r["date"] for r in _hist(400)]
    s = datapipe.time_splits(dates)
    assert s["train"]["end"] < s["validation"]["start"] < s["validation"]["end"] < s["test"]["start"]
    assert datapipe.psi([0.25] * 4, [0.25] * 4) == pytest.approx(0, abs=1e-6)
    assert datapipe.psi([0.7, 0.1, 0.1, 0.1], [0.25] * 4) > 0.25


def test_run_cycle_writes_version_and_drift(client):
    with SessionLocal() as db:
        v1 = datapipe.run_cycle(db, "test")
        assert v1.rows > 0 and len(v1.universe) > 20 and v1.splits and v1.quality["mean"] > 0.5
        v2 = datapipe.run_cycle(db, "test")
        assert set(v2.drift) == set(v1.feature_stats)


def test_hmm_recovers_two_volatility_regimes():
    rng = np.random.default_rng(3)
    calm = rng.normal(0, 0.5, (300, 1))
    wild = rng.normal(0, 3.0, (300, 1))
    x = np.vstack([calm, wild, calm])
    X = np.column_stack([x[:, 0], np.abs(x[:, 0])])
    m = patterns.fit_hmm(X, K=2)
    path = m["path"]
    hi = int(np.argmax(m["mu"][:, 1]))
    assert (path[320:580] == hi).mean() > 0.8 and (path[:280] != hi).mean() > 0.8


def test_granger_detects_planted_lead():
    rng = np.random.default_rng(5)
    x = rng.normal(0, 1, 800)
    y = np.r_[0, 0.6 * x[:-1]] + rng.normal(0, 1, 800)
    F, d1, d2 = patterns._granger_f(y, x, 1)
    assert patterns._f_pvalue(F, d1, d2) < 1e-6
    F0, a, b = patterns._granger_f(x, rng.normal(0, 1, 800), 1)
    assert patterns._f_pvalue(F0, a, b) > 0.001


def test_book_metrics_and_flow():
    m = patterns.book_metrics([(99.9, 5), (99.8, 5)], [(100.1, 1), (100.2, 1)])
    assert m["spread_bps"] == pytest.approx(20, rel=0.01)
    assert m["imbalance_10bps"] > 0 and m["microprice"] > m["mid"]
    f = patterns.trade_flow([{"side": "sell", "size": "2", "price": "10"}, {"side": "buy", "size": "1", "price": "10"}])
    assert f["flow_imbalance"] == pytest.approx(1 / 3)


def test_quant_endpoints_and_gating(client):
    free, pro = _user(client), _user(client, "pro")
    r = client.get("/api/quant/regimes", headers=free).json()
    assert r["current"]["state"] in ("Calm", "Normal", "Stressed") and len(r["states"]) == 3
    assert client.get("/api/quant/regimes?symbol=QQQ", headers=free).status_code == 402
    assert client.get("/api/quant/regimes?symbol=QQQ", headers=pro).status_code == 200
    ll = client.get("/api/quant/leadlag", headers=pro).json()
    assert ll["pairs"] and len(ll["correlation"]) == len(ll["symbols"])
    assert client.get("/api/quant/leadlag", headers=free).json()["locked"] is True
    s = client.get("/api/quant/states", headers=pro).json()
    assert 0 <= s["current_state"] < len(s["states"]) and len(s["analogs"]) >= 3
    assert len(client.get("/api/quant/states", headers=free).json()["analogs"]) <= 2
    assert client.get("/api/quant/micro?pair=AAPL", headers=pro).json()["available"] is False
    assert client.get("/api/quant/regimes").status_code == 401


# ── five-step pattern engine ────────────────────────────────────────────────────────────────────
from app.quant import engine  # noqa: E402


def _bars(n=2500, seed=0, plant=False):
    rng = np.random.default_rng(seed)
    px, out, t0 = 100.0, [], dt.datetime(2015, 1, 1, tzinfo=dt.timezone.utc)
    rebound = 0
    for i in range(n):
        o = px
        r = rng.normal(0, 0.01)
        if plant and rng.random() < 0.01:
            r = -0.045  # a shock...
            rebound = 4
        elif plant and rebound:
            r = abs(r) + 0.012  # ...that reliably reverses (the planted edge)
            rebound -= 1
        c = o * np.exp(r)
        out.append({"t": (t0 + dt.timedelta(days=i)).isoformat(), "o": o, "h": max(o, c) * 1.002, "l": min(o, c) * 0.998, "c": c, "v": 1e6 * rng.lognormal(0, 0.3)})
        px = c
    return out


def test_features_are_scale_invariant():
    a = _bars(600, seed=3)
    b = [{**x, "o": x["o"] * 37, "h": x["h"] * 37, "l": x["l"] * 37, "c": x["c"] * 37, "v": x["v"] * 9} for x in a]
    fa, fb = engine.normalise(a), engine.normalise(b)
    for k in ("z_ret", "dist_50", "squeeze_pct", "vol_z", "rsi_3"):
        assert np.allclose(np.nan_to_num(fa[k]), np.nan_to_num(fb[k]), atol=1e-9), k


def test_labels_are_point_in_time_and_non_overlapping():
    f = engine.normalise(_bars(800, seed=4))
    mask = np.zeros(800, bool)
    mask[[300, 302, 305, 330]] = True
    ev = engine.events(mask, horizon=10)
    assert ev.tolist() == [300, 330]  # 302 and 305 fall inside 300's outcome window
    lab = engine.label(f, ev, 1, 10, (1.0, 1.0))
    assert np.all(lab["end"] > ev) and np.all(lab["end"] <= ev + 10)
    # changing data before the signal bar's close cannot change bars after it, and vice versa: features at t ignore t+1..
    f2 = engine.normalise(_bars(800, seed=4)[:301])
    assert np.isclose(f["z_ret"][300], f2["z_ret"][300]) and np.isclose(f["squeeze_pct"][300], f2["squeeze_pct"][300])


def test_bh_and_hurdle():
    q = engine.bh_qvalues([0.001, 0.01, 0.03, 0.5])
    assert q[0] <= q[1] <= q[2] <= q[3] <= 1 and q[0] == pytest.approx(0.004)
    assert engine.deflated_hurdle(100) > engine.deflated_hurdle(10) > 2


def test_engine_finds_planted_edge_and_rejects_noise(monkeypatch):
    def fake(symbol, timeframe="1d"):
        return {"bars": _bars(2500, seed=sum(map(ord, symbol)) * 7, plant=symbol.startswith("EDGE")), "source": "DEMO"}

    monkeypatch.setattr(engine.service, "bars", fake)
    res = engine.run_study(asset_classes=["etfs"], timeframes=["1d"], patterns=["shock_reversal"], symbols=["EDGE1", "EDGE2", "EDGE3"])
    o = res["results"][0]
    assert o["verdict"] == "Robust", o["reasons"]
    assert o["edge_vs_random"] > 0.3 and o["holdout"]["mean_r"] > 0 and o["permutation"]["p_value"] < 0.01
    noise = engine.run_study(asset_classes=["etfs"], timeframes=["1d"], symbols=["N1", "N2", "N3"])
    assert not any(x.get("verdict") == "Robust" for x in noise["results"])
    assert res["source"] == "DEMO"


def test_pattern_endpoints(client):
    free, pro = _user(client), _user(client, "pro")
    cat = client.get("/api/quant/patterns", headers=free).json()
    assert len(cat["catalog"]["patterns"]) >= 6 and set(cat["catalog"]["method"]) == {"1", "2", "3", "4", "5"}
    assert client.post("/api/quant/patterns/test", headers=free, json={"pattern": "shock_reversal", "asset_class": "crypto", "timeframe": "1d"}).status_code == 402
    r = client.post("/api/quant/patterns/test", headers=pro, json={"pattern": "squeeze_breakout", "asset_class": "fx", "timeframe": "1wk"}).json()
    assert r["results"][0]["asset_class"] == "fx" and r["source"] == "DEMO"
    assert client.post("/api/quant/patterns/test", headers=pro, json={"pattern": "nope", "asset_class": "fx", "timeframe": "1d"}).status_code == 422
