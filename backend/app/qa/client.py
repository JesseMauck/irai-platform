"""HTTP client for the synthetic trader: timing, redacted traces, request budget, retry with exponential backoff."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import SYNTHETIC_HEADER, QaSettings

RETRY_STATUSES = {429, 502, 503, 504}
REDACT = {"authorization", "cookie", "x-api-key", "set-cookie"}


class BudgetExhausted(RuntimeError):
    pass


class TargetUnhealthy(RuntimeError):
    """The target keeps failing (down or erroring): abort the run instead of filing noise."""


class Throttled(RuntimeError):
    """The target asked us to wait longer than we're willing to (429 + long Retry-After): end the run politely."""


@dataclass
class Call:
    method: str
    path: str
    status: int  # 0 = transport error
    ms: float
    body: Any = None
    text: str = ""
    error: str | None = None
    attempts: int = 1
    request: Any = None
    retry_after: float | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def trace(self) -> dict[str, Any]:
        snippet = self.text if len(self.text) <= 2000 else self.text[:2000] + "…"
        return {"method": self.method, "path": _redact_path(self.path), "status": self.status, "ms": round(self.ms, 1),
                "attempts": self.attempts, "request": self.request, "response": snippet, "error": self.error}


def _retry_after(v: str | None) -> float | None:
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _redact_path(path: str) -> str:
    # webhook tokens are bearer secrets
    if "/api/bots/hook/" in path:
        head, _, tok = path.partition("/api/bots/hook/")
        return f"{head}/api/bots/hook/{tok[:4]}…" if tok else path
    return path


@dataclass
class QaClient:
    settings: QaSettings
    http: httpx.Client
    requests: int = 0
    unhealthy_streak: int = 0
    sleep: Any = field(default=time.sleep)
    calls: list[Call] = field(default_factory=list)

    @classmethod
    def build(cls, settings: QaSettings) -> QaClient:
        if settings.inprocess:
            from fastapi.testclient import TestClient

            from ..main import app

            http: httpx.Client = TestClient(app, raise_server_exceptions=False)
        else:
            http = httpx.Client(base_url=settings.target.rstrip("/"), timeout=settings.request_timeout)
        http.headers[SYNTHETIC_HEADER] = "1"
        http.headers["User-Agent"] = "irai-synthetic-qa/1"
        return cls(settings=settings, http=http)

    def close(self) -> None:
        self.http.close()

    def call(self, method: str, path: str, token: str | None = None, json_body: Any = None, params: dict | None = None) -> Call:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        attempt = 0
        while True:
            if self.requests >= self.settings.max_requests:
                raise BudgetExhausted(f"request budget of {self.settings.max_requests} used")
            self.requests += 1
            attempt += 1
            t0 = time.perf_counter()
            try:
                r = self.http.request(method, path, headers=headers, json=json_body, params=params)
                ms = (time.perf_counter() - t0) * 1000
                try:
                    body = r.json()
                except (json.JSONDecodeError, ValueError):
                    body = None
                c = Call(method, path, r.status_code, ms, body, r.text, attempts=attempt, request=json_body,
                         retry_after=_retry_after(r.headers.get("retry-after")))
            except httpx.HTTPError as e:
                ms = (time.perf_counter() - t0) * 1000
                c = Call(method, path, 0, ms, error=f"{type(e).__name__}: {e}", attempts=attempt, request=json_body)
            retryable = c.status == 0 or c.status in RETRY_STATUSES
            if c.status == 429 and (c.retry_after or 0) > self.settings.max_retry_after:
                self.calls.append(c)
                raise Throttled(f"{path} rate-limited for {c.retry_after:.0f}s (limit {self.settings.max_retry_after}s)")
            if retryable and attempt <= self.settings.retries:
                wait = self.settings.backoff_base * (2 ** (attempt - 1))
                self.sleep(max(wait, c.retry_after or 0))
                continue
            break
        self.unhealthy_streak = self.unhealthy_streak + 1 if retryable else 0
        self.calls.append(c)
        if self.unhealthy_streak >= self.settings.abort_after_unhealthy:
            raise TargetUnhealthy(f"{self.unhealthy_streak} consecutive failed calls; last {c.status} on {c.path}")
        return c
