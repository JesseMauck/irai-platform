"""IRAI database schema.

Domains
  accounts      users, subscriptions, usage counters
  coverage      instruments, adr_pairs, etf_funds, peer_groups (+ members)
  market cache  quotes (latest quote + history per symbol, refreshed from the live source)
  research      articles, article_views (for the free-tier monthly quota)
  personal      watchlists, watchlist_items, alerts, alert_events
  community     communities, threads, posts, votes, trade_posts (immutable once published)
  valuebot      valuation_runs (one row per ValueBot job, linked to the user who ran it)
  platform      email_outbox (transactional email queue), password_resets, api_keys, saved_screens
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
                        func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())


# ── accounts ──────────────────────────────────────────────────────────────────────────────────────
class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    handle: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free | essential | pro
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_trader: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_customer_id: Mapped[str | None] = mapped_column(String(64))  # Square customer id
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Sessions issued before this moment are rejected (set on password reset / "sign out everywhere").
    tokens_valid_after: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user", cascade="all, delete-orphan")
    watchlists: Mapped[list[Watchlist]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))
    interval: Mapped[str] = mapped_column(String(10), default="monthly")  # monthly | annual
    status: Mapped[str] = mapped_column(String(20), default="trialing")  # pending|trialing|active|past_due|canceled
    trial_ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(12), default="internal", server_default="internal")  # internal | square
    provider_subscription_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    provider_ref: Mapped[str | None] = mapped_column(String(64), index=True)  # e.g. Square payment link order id
    trial_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    user: Mapped[User] = relationship(back_populates="subscriptions")


# ── coverage ──────────────────────────────────────────────────────────────────────────────────────
class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(12), default="equity")  # equity | etf | index | fx | rate
    exchange: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(60))
    sector: Mapped[str | None] = mapped_column(String(60))
    industry: Mapped[str | None] = mapped_column(String(80))
    in_ticker_bar: Mapped[bool] = mapped_column(Boolean, default=False)
    ticker_bar_label: Mapped[str | None] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class AdrPair(TimestampMixin, Base):
    __tablename__ = "adr_pairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    adr_symbol: Mapped[str] = mapped_column(String(20), unique=True)
    local_symbol: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str] = mapped_column(String(60))
    local_currency: Mapped[str] = mapped_column(String(8))
    # Local ordinary shares represented by ONE ADR (e.g. 10 for Toyota, 0.5 for AstraZeneca).
    ratio: Mapped[float] = mapped_column(Float)
    shortable_local: Mapped[bool] = mapped_column(Boolean, default=True)
    round_trip_cost_bps: Mapped[float] = mapped_column(Float, default=35.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class EtfFund(TimestampMixin, Base):
    __tablename__ = "etf_funds"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PeerGroup(TimestampMixin, Base):
    __tablename__ = "peer_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    sector: Mapped[str] = mapped_column(String(60))
    members: Mapped[list[PeerMember]] = relationship(back_populates="group", cascade="all, delete-orphan")


class PeerMember(Base):
    __tablename__ = "peer_members"
    __table_args__ = (UniqueConstraint("group_id", "symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("peer_groups.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(160))
    group: Mapped[PeerGroup] = relationship(back_populates="members")


class GradeSnapshot(Base):
    """Point-in-time Relative Value grades: written once per computation, never restated."""
    __tablename__ = "grade_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    peer_group: Mapped[str] = mapped_column(String(80))
    as_of: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    grade: Mapped[str] = mapped_column(String(3))
    rv_percentile: Mapped[float] = mapped_column(Float)
    quality_percentile: Mapped[float] = mapped_column(Float)
    multiple: Mapped[float | None] = mapped_column(Float)
    multiple_name: Mapped[str] = mapped_column(String(20))
    residual: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(10))


# ── market cache ──────────────────────────────────────────────────────────────────────────────────
class QuoteCache(Base):
    __tablename__ = "quotes"
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── research ──────────────────────────────────────────────────────────────────────────────────────
class Article(TimestampMixin, Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), index=True)  # ADR | ETF | Fundamental | Methodology
    tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    body_md: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(80))
    published_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    read_minutes: Mapped[int] = mapped_column(Integer, default=5)
    premium: Mapped[bool] = mapped_column(Boolean, default=False)


class ArticleView(Base):
    __tablename__ = "article_views"
    __table_args__ = (UniqueConstraint("user_id", "article_id", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7))  # YYYY-MM


# ── personal ──────────────────────────────────────────────────────────────────────────────────────
class Watchlist(TimestampMixin, Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    user: Mapped[User] = relationship(back_populates="watchlists")
    items: Mapped[list[WatchlistItem]] = relationship(back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(TimestampMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    # price_above | price_below | change_pct_abs | adr_z_abs
    kind: Mapped[str] = mapped_column(String(20))
    threshold: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String(10), default="email")  # email | webhook | push
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    triggered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    value: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(String(300))


# ── community ─────────────────────────────────────────────────────────────────────────────────────
class Community(TimestampMixin, Base):
    __tablename__ = "communities"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300))
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    pro_only: Mapped[bool] = mapped_column(Boolean, default=False)


class Thread(TimestampMixin, Base):
    __tablename__ = "threads"
    id: Mapped[int] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body_md: Mapped[str] = mapped_column(Text)
    tickers: Mapped[list[str]] = mapped_column(JSON, default=list)
    # discussion | analysis (long-form, Seeking Alpha style) | strategy (shares a Lab backtest)
    kind: Mapped[str] = mapped_column(String(12), default="discussion", server_default="discussion", index=True)
    outlook: Mapped[str | None] = mapped_column(String(10))  # bullish | neutral | bearish (analysis only)
    primary_ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    backtest_run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id", ondelete="SET NULL"), index=True)
    valuation_job_id: Mapped[str | None] = mapped_column(String(40))
    score: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    community: Mapped[Community] = relationship()
    author: Mapped[User] = relationship()


class Post(TimestampMixin, Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body_md: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    author: Mapped[User] = relationship()


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[str] = mapped_column(String(10))  # thread | trade
    target_id: Mapped[int] = mapped_column(Integer)
    value: Mapped[int] = mapped_column(Integer)  # +1 / -1


class TradePost(TimestampMixin, Base):
    """A structured trade idea. Entry price is captured from market data at posting time and the
    thesis/entry can never be edited; only closing is allowed (exit price also captured)."""
    __tablename__ = "trade_posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    long_symbol: Mapped[str] = mapped_column(String(20))
    short_symbol: Mapped[str | None] = mapped_column(String(20))
    thesis: Mapped[str] = mapped_column(Text)
    entry_long: Mapped[float] = mapped_column(Float)
    entry_short: Mapped[float | None] = mapped_column(Float)
    entry_source: Mapped[str] = mapped_column(String(10))  # LIVE | DEMO | USER
    verification: Mapped[str] = mapped_column(String(24))  # timestamp-verified | broker-verified | self-reported
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | closed
    exit_long: Mapped[float | None] = mapped_column(Float)
    exit_short: Mapped[float | None] = mapped_column(Float)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    return_pct: Mapped[float | None] = mapped_column(Float)
    score: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    author: Mapped[User] = relationship()


class ModerationLog(Base):
    """Every moderation action is logged (community rule: actions are logged and can be appealed)."""
    __tablename__ = "moderation_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    target_type: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))  # hide | unhide
    reason: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── valuebot ──────────────────────────────────────────────────────────────────────────────────────
class ValuationRun(TimestampMixin, Base):
    __tablename__ = "valuation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    stance: Mapped[str] = mapped_column(String(10), default="neutral")
    status: Mapped[str] = mapped_column(String(10), default="queued")
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    value_per_share: Mapped[float | None] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    upside: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(60))
    prob_undervalued: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(String(500))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    month: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM, for plan quotas
    # Report library: the member's own title, notes (markdown) and organisation.
    title: Mapped[str | None] = mapped_column(String(200))
    notes_md: Mapped[str | None] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notes_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Saved what-if scenarios: [{"name", "assumptions": {...}, "value_per_share", "upside", "saved_at"}]
    scenarios: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, server_default="[]")


# ── platform ──────────────────────────────────────────────────────────────────────────────────────
class EmailOutbox(Base):
    """Transactional email queue (outbox pattern): requests write a row, the worker sends it. A failed send
    is retried with backoff; a row is never sent twice once marked sent."""
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    to_addr: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(200))
    body_text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))  # welcome | password_reset | alert | valuebot_done
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    next_attempt_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 of the emailed token
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    """Read-only API keys for Pro members. Only a SHA-256 hash is stored; the key is shown once."""
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(12))  # first characters, for display
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SavedScreen(TimestampMixin, Base):
    __tablename__ = "saved_screens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    universe: Mapped[str] = mapped_column(String(12))  # fundamental | adr | etf
    filters: Mapped[dict[str, Any]] = mapped_column(JSON)
    alert_on_new: Mapped[bool] = mapped_column(Boolean, default=False)
    last_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)


class BacktestRun(Base):
    """One Strategy Lab backtest (or optimisation) — stored so members can revisit and share results."""
    __tablename__ = "backtest_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="backtest")  # backtest | optimize
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    strategy: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON)
    range: Mapped[str] = mapped_column(String(4))
    statistics: Mapped[dict[str, Any]] = mapped_column(JSON)
    data_source: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
