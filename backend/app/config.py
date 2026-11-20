"""IRAI platform settings (environment variables, see backend/.env.example)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = BACKEND_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def normalise_db_url(url: str) -> str:
    """Accept the plain URLs Supabase/Railway/Heroku hand out and select the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: normalise_db_url(os.environ.get(
        "DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'irai.db'}")))
    # Create tables on startup (handy for SQLite dev). Production Postgres uses `alembic upgrade head`.
    auto_create_tables: bool = field(default_factory=lambda: os.environ.get(
        "IRAI_AUTO_CREATE_TABLES", "1" if not os.environ.get("DATABASE_URL", "sqlite").startswith("postgres") else "0") == "1")
    # JWT signing key. MUST be set in production; a random per-process key is used otherwise
    # (which logs everyone out on restart).
    jwt_secret: str = field(default_factory=lambda: os.environ.get("IRAI_JWT_SECRET") or secrets.token_urlsafe(48))
    jwt_ttl_hours: int = field(default_factory=lambda: int(os.environ.get("IRAI_JWT_TTL_HOURS", "72")))
    cors_origins: list[str] = field(default_factory=lambda: _list("IRAI_CORS_ORIGINS", "http://localhost:3000"))
    # live = Yahoo Finance (+ SEC via ValueBot); demo = deterministic fictional data, no network.
    market_mode: str = field(default_factory=lambda: os.environ.get("IRAI_MARKET_MODE", "live").lower())
    # When a live fetch fails, fall back to demo data (clearly labelled DEMO) instead of erroring.
    demo_fallback: bool = field(default_factory=lambda: os.environ.get("IRAI_DEMO_FALLBACK", "1") not in {"0", "false", "no"})
    quote_ttl: int = field(default_factory=lambda: int(os.environ.get("IRAI_QUOTE_TTL", "30")))
    history_ttl: int = field(default_factory=lambda: int(os.environ.get("IRAI_HISTORY_TTL", "3600")))
    info_ttl: int = field(default_factory=lambda: int(os.environ.get("IRAI_INFO_TTL", "21600")))
    stripe_secret_key: str = field(default_factory=lambda: os.environ.get("STRIPE_SECRET_KEY", ""))
    stripe_webhook_secret: str = field(default_factory=lambda: os.environ.get("STRIPE_WEBHOOK_SECRET", ""))
    stripe_prices: dict = field(default_factory=lambda: {
        "essential_monthly": os.environ.get("STRIPE_PRICE_ESSENTIAL_MONTHLY", ""),
        "essential_annual": os.environ.get("STRIPE_PRICE_ESSENTIAL_ANNUAL", ""),
        "pro_monthly": os.environ.get("STRIPE_PRICE_PRO_MONTHLY", ""),
        "pro_annual": os.environ.get("STRIPE_PRICE_PRO_ANNUAL", ""),
    })
    public_url: str = field(default_factory=lambda: os.environ.get("PUBLIC_URL", "http://localhost:3000"))
    leaderboard_min_trades: int = field(default_factory=lambda: int(os.environ.get("IRAI_LEADERBOARD_MIN_TRADES", "20")))

    @property
    def live(self) -> bool:
        return self.market_mode == "live"


settings = Settings()
