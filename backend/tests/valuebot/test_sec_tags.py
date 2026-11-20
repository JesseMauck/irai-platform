from valuebot.data.sec import _first


def _obs(end, val, start=None, form="10-K", filed=None):
    o = {"end": end, "val": val, "form": form, "filed": filed or end}
    if start:
        o["start"] = start
    return o


def test_prefers_tag_with_most_recent_data_and_backfills():
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [_obs("2009-06-30", 58e9, "2008-07-01"), _obs("2010-06-30", 62.5e9, "2009-07-01")]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            _obs("2024-06-30", 245e9, "2023-07-01"), _obs("2025-06-30", 281.7e9, "2024-07-01"),
            _obs("2025-03-31", 70e9, "2025-01-01", form="10-Q")]}},
    }}}
    series, tag = _first(facts, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"], instant=False)
    assert tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert series["2025-06-30"] == 281.7e9 and "2025-03-31" not in series  # quarterly ignored
    assert series["2010-06-30"] == 62.5e9  # older periods back-filled from the retired tag


def test_ttm_from_quarters_when_no_annual_report():
    from valuebot.data.sec import _ttm_series
    q = [_obs(e, 10e9, s, form="10-Q") for s, e in [("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
                                                    ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30")]]
    q.append(_obs("2026-09-30", 30e9, "2026-01-01", form="10-Q"))  # 9-month YTD is ignored
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": q}},
                                   "Assets": {"units": {"USD": [_obs("2026-09-30", 500e9, form="10-Q")]}}}}}
    assert _ttm_series(facts, "Revenues", False) == {"2026-09-30": 40e9}
    assert _ttm_series(facts, "Assets", True) == {"2026-09-30": 500e9}
