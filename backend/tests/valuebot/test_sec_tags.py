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
