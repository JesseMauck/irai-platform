"""Runtime configuration, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Tiny .env loader so we don't need python-dotenv."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("VALUEBOT_MODEL", "claude-opus-5-5"))
    fast_model: str = field(default_factory=lambda: os.environ.get("VALUEBOT_FAST_MODEL", "claude-sonnet-5-5"))
    # SEC requires a descriptive User-Agent with contact info.
    sec_user_agent: str = field(
        default_factory=lambda: os.environ.get("SEC_USER_AGENT", "ValueBot research bot admin@example.com")
    )
    # Mature-market equity risk premium. Damodaran's implied ERP for 1 Jan 2026 is 4.23%
    # (8.41% expected return − 3.95% default-free rate − 0.23% US default spread). Refresh monthly
    # from pages.stern.nyu.edu/~adamodar/ -> "Implied ERP".
    equity_risk_premium: float = field(default_factory=lambda: _float("VALUEBOT_ERP", 0.0423))
    # The US is rated Aa1, so the 10y Treasury is not quite default-free: subtract the default
    # spread for Aa1 (0.23% in Jan 2026) to get the US$ risk-free rate.
    us_default_spread: float = field(default_factory=lambda: _float("VALUEBOT_US_DEFAULT_SPREAD", 0.0023))
    # Expected long-run US inflation, used to convert risk-free rates into other currencies.
    us_inflation: float = field(default_factory=lambda: _float("VALUEBOT_US_INFLATION", 0.025))
    # Fallback risk-free rate if the 10y Treasury can't be fetched.
    default_riskfree: float = field(default_factory=lambda: _float("VALUEBOT_RISKFREE", 0.0395))
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("VALUEBOT_DATA_DIR", Path(__file__).resolve().parent.parent / "runs"))
    )
    # offline=True: use bundled demo fixtures and heuristic (non-LLM) reasoning.
    offline: bool = field(default_factory=lambda: os.environ.get("VALUEBOT_OFFLINE", "").lower() in {"1", "true", "yes"})

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key) and not self.offline


settings = Settings()
