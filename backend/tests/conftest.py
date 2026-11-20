"""Test environment: isolated SQLite DB, demo market data, offline ValueBot. Set before app import."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="irai-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["IRAI_MARKET_MODE"] = "demo"
os.environ["VALUEBOT_OFFLINE"] = "1"
os.environ["VALUEBOT_DATA_DIR"] = f"{_tmp}/runs"
os.environ["IRAI_JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["IRAI_LEADERBOARD_MIN_TRADES"] = "2"
