import datetime as dt

import pytest

from app import calibration
from app.db import SessionLocal
from app.models import CalibrationRun


@pytest.fixture(autouse=True, scope="module")
def _tables():
    from app.db import init_db
    init_db()


def test_classify_flags():
    assert calibration.classify(1.0, 100, 105) == []
    assert calibration.classify(0.2, None, 10) == ["far below price"]
    assert calibration.classify(3.0, None, 10) == ["far above price"]
    assert calibration.classify(1.0, 100, 150) == ["moved +50% since last run"]
    assert calibration.classify(None, None, None) == ["no value"]


def test_due_window():
    with SessionLocal() as db:
        db.query(CalibrationRun).delete()
        db.commit()
        morning = dt.datetime(2026, 11, 21, 8, tzinfo=dt.timezone.utc)
        assert calibration.due(db, morning)
        assert not calibration.due(db, morning.replace(hour=5))
        db.add(CalibrationRun(started_at=morning - dt.timedelta(hours=2), status="done", results=[]))
        db.commit()
        assert not calibration.due(db, morning)
        assert calibration.due(db, morning + dt.timedelta(days=1))


def test_run_demo_ticker_without_llm():
    rid = calibration.run("manual", tickers=["DEMO"])
    with SessionLocal() as db:
        r = db.get(CalibrationRun, rid)
        assert r.status == "done" and r.summary["tickers"] == 1
        res = r.results[0]
        assert res["ok"], res
        assert res["ratio"] and res["ratio"] > 0 and isinstance(res["flags"], list)


def test_llm_disabled_is_scoped():
    import threading

    from valuebot.config import Settings, llm_disabled
    settings = Settings(anthropic_api_key="test-key", offline=False)
    assert settings.llm_enabled
    seen = {}
    with llm_disabled():
        assert not settings.llm_enabled
        t = threading.Thread(target=lambda: seen.setdefault("other", settings.llm_enabled))  # other threads unaffected
        t.start(); t.join()
    assert seen["other"] is True and settings.llm_enabled
