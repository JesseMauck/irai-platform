import time

import httpx
import pytest

from app.market.opendata import OpenDataSource, fx_from_ecb, parse_ecb_csv, parse_treasury_csv

ECB = """KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-11-18,1.0500
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-11-19,1.0600
EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2026-11-18,0.8400
EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,SP00,A,2026-11-19,0.8480
EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2026-11-18,157.50
EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2026-11-19,159.00
"""

TSY = """Date,"1 Mo","10 Yr","30 Yr"
11/19/2026,4.30,4.41,4.60
11/18/2026,4.31,4.38,4.58
"""


def test_ecb_cross_rates():
    rates = parse_ecb_csv(ECB)
    gbp = fx_from_ecb("GBPUSD=X", rates)
    assert gbp[-1] == ("2026-11-19", pytest.approx(1.06 / 0.848))
    eur = fx_from_ecb("EURUSD=X", rates)
    assert eur[-1][1] == pytest.approx(1.06)
    jpy = fx_from_ecb("JPY=X", rates)
    assert jpy[-1][1] == pytest.approx(159.0 / 1.06)
    assert fx_from_ecb("TWDUSD=X", rates) is None


def test_treasury_parse():
    s = parse_treasury_csv(TSY)
    assert s == [("2026-11-18", 4.38), ("2026-11-19", 4.41)]


def test_open_source_quotes_are_labelled():
    def handler(req: httpx.Request):
        u = str(req.url)
        if "ecb.europa.eu" in u:
            return httpx.Response(200, text=ECB)
        if "treasury.gov" in u:
            return httpx.Response(200, text=TSY)
        if u.endswith("/ticker"):
            return httpx.Response(200, json={"price": "97000.5"})
        if "/candles" in u:
            day = 86400 * (int(time.time()) // 86400)
            # Coinbase returns newest first; the newest candle is today's (partial) one.
            return httpx.Response(200, json=[[day, 1, 2, 1, 96500.0, 10], [day - 86400, 1, 2, 1, 96000.0, 10]])
        return httpx.Response(404)

    src = OpenDataSource(client=httpx.Client(transport=httpx.MockTransport(handler)))
    fx = src.chart("GBPUSD=X")
    assert fx["quote"]["source"] == "EOD" and fx["quote"]["provider"] == "ECB reference rate"
    assert fx["quote"]["price"] == pytest.approx(1.06 / 0.848) and len(fx["history"]) == 2
    assert src.chart("^TNX")["quote"]["price"] == 4.41
    btc = src.chart("BTC-USD")["quote"]
    assert btc["source"] == "LIVE" and btc["price"] == 97000.5 and btc["prev_close"] == 96000.0
    assert OpenDataSource.supports("JPY=X") and not OpenDataSource.supports("AAPL")
