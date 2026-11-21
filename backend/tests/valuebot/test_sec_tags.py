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


def test_ttm_from_year_to_date_cash_flows():
    """Cash-flow items in 10-Qs are year-to-date; quarters must be differenced, Q4 taken from the 10-K."""
    from valuebot.data.sec import _quarters, _ttm_series

    def o(start, end, val, form="10-Q", filed="2026-11-01"):
        return {"start": start, "end": end, "val": val, "form": form, "filed": filed}

    obs = [
        o("2025-01-01", "2025-09-30", 27.0),                       # 9M 2025
        o("2025-01-01", "2025-12-31", 40.0, form="10-K"),          # FY 2025 → Q4 = 13
        o("2026-01-01", "2026-03-31", 10.0),                       # Q1 2026 (3M)
        o("2026-01-01", "2026-06-30", 21.0),                       # H1 → Q2 = 11
        o("2026-01-01", "2026-09-30", 33.0),                       # 9M → Q3 = 12
    ]
    q = _quarters(obs)
    assert q["2025-12-31"] == ("2025-09-30", 13.0)
    assert q["2026-06-30"] == ("2026-03-31", 11.0) and q["2026-09-30"] == ("2026-06-30", 12.0)
    facts = {"facts": {"us-gaap": {"PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": obs}}}}}
    assert _ttm_series(facts, "PaymentsToAcquirePropertyPlantAndEquipment", False) == {"2026-09-30": 13 + 10 + 11 + 12}
    # a gap (missing H1) means no four consecutive quarters → no TTM rather than a wrong one
    gap = [x for x in obs if x["end"] != "2026-06-30"]
    assert _ttm_series({"facts": {"us-gaap": {"X": {"units": {"USD": gap}}}}}, "X", False) == {}


def test_quarter_from_half_year_minus_q2_and_merge_predecessor():
    from valuebot.data.sec import _annual_series, _quarters, merge_facts

    def o(start, end, val, form="10-Q", filed="2026-11-01"):
        return {"start": start, "end": end, "val": val, "form": form, "filed": filed}

    q = _quarters([o("2026-01-01", "2026-06-30", 21.0), o("2026-04-01", "2026-06-30", 11.0)])
    assert q["2026-03-31"] == ("2026-01-01", 10.0)
    new = {"entityName": "NewCo Holdings", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [o("2026-04-01", "2026-06-30", 11.0)]}}}}}
    old = {"entityName": "OldCo", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [o("2025-01-01", "2025-12-31", 40.0, form="10-K")]}}}}}
    m = merge_facts(new, old)
    assert m["entityName"] == "NewCo Holdings"
    assert len(m["facts"]["us-gaap"]["Revenues"]["units"]["USD"]) == 2
    assert _annual_series(m, "Revenues", False) == {"2025-12-31": 40.0}
