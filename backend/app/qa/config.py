"""QA agent settings (IRAI_QA_* environment variables) and the production guard."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

SYNTHETIC_DOMAIN = "qa.irai.invalid"  # RFC 2606 reserved: mail to these addresses can never be delivered
SYNTHETIC_HEADER = "X-IRAI-Synthetic-QA"
PRODUCTION_HOSTS_DEFAULT = "irradiance.ai,api.irradiance.ai,api-production-33269b52.up.railway.app"


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


def _default_env() -> str:
    # A Postgres DATABASE_URL means we are on a deployed database; assume production unless told otherwise.
    return "production" if os.environ.get("DATABASE_URL", "").startswith("postgres") else "local"


@dataclass(frozen=True)
class QaSettings:
    # "inprocess" drives the FastAPI app directly (tests, CI); otherwise the API base URL.
    target: str = field(default_factory=lambda: os.environ.get("IRAI_QA_TARGET", "inprocess"))
    env: str = field(default_factory=lambda: os.environ.get("IRAI_QA_ENV", _default_env()).lower())
    allow_production: bool = field(default_factory=lambda: os.environ.get("IRAI_QA_ALLOW_PRODUCTION") == "1")
    production_hosts: tuple[str, ...] = field(default_factory=lambda: tuple(
        h.strip().lower() for h in os.environ.get("IRAI_QA_PRODUCTION_HOSTS", PRODUCTION_HOSTS_DEFAULT).split(",") if h.strip()))
    # batch + budgets (per run)
    batch_size: int = field(default_factory=lambda: _int("IRAI_QA_BATCH", 8))
    max_requests: int = field(default_factory=lambda: _int("IRAI_QA_MAX_REQUESTS", 400))
    max_seconds: int = field(default_factory=lambda: _int("IRAI_QA_MAX_SECONDS", 480))
    starting_cash: float = field(default_factory=lambda: _float("IRAI_QA_STARTING_CASH", 100_000))
    # latency budgets (ms) — slower responses become latency findings
    latency_ms: int = field(default_factory=lambda: _int("IRAI_QA_LATENCY_MS", 2500))
    latency_slow_ms: int = field(default_factory=lambda: _int("IRAI_QA_LATENCY_SLOW_MS", 8000))  # report/profile endpoints
    request_timeout: float = field(default_factory=lambda: _float("IRAI_QA_REQUEST_TIMEOUT", 30))
    # retry/backoff on 429/5xx/transport errors
    retries: int = field(default_factory=lambda: _int("IRAI_QA_RETRIES", 2))
    backoff_base: float = field(default_factory=lambda: _float("IRAI_QA_BACKOFF_BASE", 1.0))
    max_retry_after: float = field(default_factory=lambda: _float("IRAI_QA_MAX_RETRY_AFTER", 30))
    abort_after_unhealthy: int = field(default_factory=lambda: _int("IRAI_QA_ABORT_AFTER", 6))
    # orchestration loop
    interval: int = field(default_factory=lambda: _int("IRAI_QA_INTERVAL", 900))
    run_timeout: int = field(default_factory=lambda: _int("IRAI_QA_RUN_TIMEOUT", 900))
    lease_stale_after: int = field(default_factory=lambda: _int("IRAI_QA_LEASE_STALE", 1200))
    alert_after_failures: int = field(default_factory=lambda: _int("IRAI_QA_ALERT_AFTER", 3))
    # triage
    triage_max: int = field(default_factory=lambda: _int("IRAI_QA_TRIAGE_MAX", 10))
    triage_min_occurrences: int = field(default_factory=lambda: _int("IRAI_QA_TRIAGE_MIN_OCCURRENCES", 2))
    triage_model: str = field(default_factory=lambda: os.environ.get("IRAI_QA_TRIAGE_MODEL", ""))  # default: ValueBot main model
    triage_max_tokens: int = field(default_factory=lambda: _int("IRAI_QA_TRIAGE_MAX_TOKENS", 1500))

    @property
    def inprocess(self) -> bool:
        return self.target == "inprocess"

    def is_production(self) -> bool:
        if self.env == "production":
            return True
        if self.inprocess:
            return False
        host = (urlparse(self.target).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in self.production_hosts)

    def guard(self) -> None:
        """Refuse to trade against production unless explicitly allowed (paper money, but real users' database)."""
        if self.is_production() and not self.allow_production:
            raise RuntimeError(
                f"QA target {self.target!r} (env {self.env}) looks like production. Point IRAI_QA_TARGET at staging or a "
                "local API and set IRAI_QA_ENV=staging, or set IRAI_QA_ALLOW_PRODUCTION=1 to override deliberately.")


def load() -> QaSettings:
    return QaSettings()
