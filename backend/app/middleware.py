"""Cross-cutting HTTP concerns: request IDs + structured access logs, security headers, rate limiting."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("irai.http")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname, "logger": record.name,
               "msg": record.getMessage()}
        out.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


class RequestContext(BaseHTTPMiddleware):
    """Assigns/propagates X-Request-ID, logs one structured line per request, adds security headers."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"extra_fields": {"request_id": rid, "path": request.url.path}})
            response = JSONResponse({"detail": "Internal error", "request_id": rid}, status_code=500)
        ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path != "/api/health":
            log.info("request", extra={"extra_fields": {
                "request_id": rid, "method": request.method, "path": request.url.path, "status": response.status_code,
                "ms": round(ms, 1), "ip": client_ip(request)}})
        return response


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


# (method, path prefix) -> (max requests, window seconds). In-process: with several API replicas each
# enforces its own window; put a shared limiter (Redis, or the platform firewall) in front at scale.
RULES = [
    ("POST", "/api/auth/login", 10, 60),
    ("POST", "/api/auth/register", 5, 600),
    ("POST", "/api/auth/forgot", 5, 3600),
    ("POST", "/api/auth/reset", 10, 600),
    ("POST", "/api/valuebot/jobs", 10, 600),
    ("POST", "/api/valuebot/thesis", 20, 600),
    ("POST", "/api/lab/", 30, 60),
    ("POST", "/api/workspace/compare", 20, 600),
    ("POST", "/api/analyst/", 20, 600),
    ("POST", "/api/portfolio", 40, 600),
    ("POST", "/api/community/", 30, 60),
    ("GET", "/api/", 300, 60),
]


class RateLimit(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[tuple[str, str], deque] = {}
        self.lock = threading.Lock()

    async def dispatch(self, request: Request, call_next):
        if os.environ.get("IRAI_RATE_LIMIT", "1") == "0":
            return await call_next(request)
        rule = next((r for r in RULES if request.method == r[0] and request.url.path.startswith(r[1])), None)
        if rule:
            key = (rule[1] + rule[0], request.headers.get("x-api-key", "")[:16] or client_ip(request))
            now = time.monotonic()
            with self.lock:
                q = self.hits.setdefault(key, deque())
                while q and now - q[0] > rule[3]:
                    q.popleft()
                if len(q) >= rule[2]:
                    retry = int(rule[3] - (now - q[0])) + 1
                    return JSONResponse({"detail": "Too many requests, slow down."}, status_code=429,
                                        headers={"Retry-After": str(retry)})
                q.append(now)
                if len(self.hits) > 50_000:  # bound memory
                    self.hits = {k: v for k, v in self.hits.items() if v and now - v[-1] < 3600}
        return await call_next(request)
