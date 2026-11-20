"""Test environment: isolated database, demo market data, offline ValueBot. Set before app import.

SQLite by default. To run the suite against PostgreSQL (e.g. the same engine Supabase uses):
    IRAI_TEST_DATABASE_URL=postgresql://user@localhost:5432/irai_test pytest
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="irai-test-")
os.environ["DATABASE_URL"] = os.environ.get("IRAI_TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["IRAI_AUTO_CREATE_TABLES"] = "1"
os.environ["IRAI_MARKET_MODE"] = "demo"
os.environ["VALUEBOT_OFFLINE"] = "1"
os.environ["VALUEBOT_DATA_DIR"] = f"{_tmp}/runs"
os.environ["IRAI_JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["IRAI_LEADERBOARD_MIN_TRADES"] = "2"
os.environ["IRAI_RATE_LIMIT"] = "0"
os.environ["SMTP_HOST"] = ""

if os.environ["DATABASE_URL"].startswith("postgres"):
    from app import models  # noqa: F401,E402
    from app.db import Base, engine  # noqa: E402

    Base.metadata.drop_all(engine)  # fresh schema for every run
